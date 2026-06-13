#!/usr/bin/env python3
"""Scrape competitor sold listings and write them to competitor_sales.

Runs the GovDeals, PublicSurplus, and GovPlanet sold-listing scrapers, normalizes
results into the ``competitor_sales`` schema, and upserts them via Supabase.

Environment:
  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY   Supabase target (required to write).
  COMPETITOR_SCRAPER_SOURCES                 Comma list: govdeals,publicsurplus,govplanet (default: all).
  COMPETITOR_SCRAPER_MAX_PAGES              Max pages per source (default: 10).
  COMPETITOR_SCRAPER_DRY_RUN                "true" to scrape & report without writing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scrapers.competitor_sales.base import write_competitor_sales  # noqa: E402
from backend.scrapers.competitor_sales.govdeals import scrape_govdeals_sold  # noqa: E402
from backend.scrapers.competitor_sales.govplanet import scrape_govplanet_sold  # noqa: E402
from backend.scrapers.competitor_sales.publicsurplus import scrape_publicsurplus_sold  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("competitor_sales_scraper")

SCRAPERS = {
    "govdeals": scrape_govdeals_sold,
    "publicsurplus": scrape_publicsurplus_sold,
    "govplanet": scrape_govplanet_sold,
}


def _selected_sources() -> List[str]:
    raw = os.getenv("COMPETITOR_SCRAPER_SOURCES", "").strip()
    if not raw:
        return list(SCRAPERS.keys())
    requested = [s.strip().lower() for s in raw.split(",") if s.strip()]
    return [s for s in requested if s in SCRAPERS]


def _make_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        logger.warning("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY missing — running without DB writes")
        return None
    from supabase import create_client

    return create_client(url, key)


async def _run() -> Dict[str, Any]:
    dry_run = os.getenv("COMPETITOR_SCRAPER_DRY_RUN", "false").lower() == "true"
    max_pages = int(os.getenv("COMPETITOR_SCRAPER_MAX_PAGES", "10"))
    sources = _selected_sources()
    client = None if dry_run else _make_client()

    summary: Dict[str, Any] = {
        "dry_run": dry_run,
        "sources": {},
        "total_scraped": 0,
        "total_written": 0,
        "errors": [],
    }
    if not sources:
        summary["errors"].append("no_valid_sources_selected")
        return summary
    if not dry_run and client is None:
        summary["errors"].append("supabase_client_unavailable")

    for source in sources:
        scraper = SCRAPERS[source]
        try:
            rows = await scraper(max_pages=max_pages)
        except Exception as exc:
            logger.error("[%s] scrape failed: %s", source, exc)
            summary["sources"][source] = {"scraped": 0, "written": 0, "error": str(exc)}
            summary["errors"].append(f"{source}: scrape failed: {exc}")
            continue

        written = 0
        if not dry_run and rows:
            written = write_competitor_sales(rows, client)
            if written <= 0:
                summary["errors"].append(f"{source}: scraped {len(rows)} rows but wrote 0")

        summary["sources"][source] = {"scraped": len(rows), "written": written}
        summary["total_scraped"] += len(rows)
        summary["total_written"] += written
        logger.info("[%s] scraped=%d written=%d", source, len(rows), written)

    return summary


def main() -> int:
    summary = asyncio.run(_run())
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
