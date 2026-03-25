#!/usr/bin/env python3
"""Backfill missing opportunity source_site values via the Supabase REST API."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://lbnxzvqppccajllsqaaw.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_SERVICE_ROLE_KEY:
    print(
        "Error: SUPABASE_SERVICE_ROLE_KEY environment variable is required.",
        file=sys.stderr,
    )
    raise SystemExit(1)
PAGE_SIZE = 200
TIMEOUT_SECONDS = 30

SOURCE_SITE_ALIASES = {
    "allsurplus": "allsurplus",
    "bidspotter": "bidspotter",
    "equipmentfacts": "equipmentfacts",
    "gsa auctions": "gsaauctions",
    "gsaauctions": "gsaauctions",
    "govdeals": "govdeals",
    "govdeals.com": "govdeals",
    "govdeals-sold": "govdeals-sold",
    "govdeals_sold": "govdeals-sold",
    "govplanet": "govplanet",
    "hibid": "hibid",
    "hibid-v2": "hibid",
    "ironplanet": "ironplanet",
    "jjkane": "jjkane",
    "municibid": "municibid",
    "publicsurplus": "publicsurplus",
    "publicsurplus_tx": "publicsurplus",
    "proxibid": "proxibid",
    "usgovbid": "usgovbid",
}

SOURCE_SITE_URL_HINTS = (
    ("allsurplus.com", "allsurplus"),
    ("bidspotter.com", "bidspotter"),
    ("equipmentfacts.com", "equipmentfacts"),
    ("gsaauctions.gov", "gsaauctions"),
    ("govdeals.com", "govdeals"),
    ("govplanet.com", "govplanet"),
    ("hibid.com", "hibid"),
    ("ironplanet.com", "ironplanet"),
    ("jjkane.com", "jjkane"),
    ("municibid.com", "municibid"),
    ("publicsurplus.com", "publicsurplus"),
    ("proxibid.com", "proxibid"),
    ("usgovbid.com", "usgovbid"),
)


def _canonical_source_site(raw_value: Any) -> str:
    text = str(raw_value or "").strip().lower()
    if not text or text in {"apify", "none", "null", "unknown"}:
        return ""
    if text in SOURCE_SITE_ALIASES:
        return SOURCE_SITE_ALIASES[text]
    normalized = text.replace("_", "-")
    return SOURCE_SITE_ALIASES.get(normalized, "")


def _source_site_from_url(url: str) -> str:
    lowered = (url or "").strip().lower()
    if not lowered:
        return ""
    for needle, source_site in SOURCE_SITE_URL_HINTS:
        if needle in lowered:
            return source_site
    return ""


def _row_urls(row: dict[str, Any]) -> list[str]:
    raw_data = row.get("raw_data") or {}
    urls = [
        row.get("listing_url"),
        row.get("auction_url"),
        row.get("url"),
        raw_data.get("listing_url"),
        raw_data.get("auction_url"),
        raw_data.get("url"),
    ]
    return [str(url) for url in urls if url]


def infer_source_site(row: dict[str, Any]) -> str | None:
    raw_data = row.get("raw_data") or {}
    candidates = (
        row.get("source_site"),
        row.get("source"),
        raw_data.get("source_site"),
        raw_data.get("source"),
    )
    for candidate in candidates:
        source_site = _canonical_source_site(candidate)
        if source_site:
            return source_site

    for url in _row_urls(row):
        source_site = _source_site_from_url(url)
        if source_site:
            return source_site

    return None


def _request(method: str, path: str, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None) -> Any:
    query = urllib.parse.urlencode(params or {})
    url = f"{SUPABASE_URL}{path}"
    if query:
        url = f"{url}?{query}"

    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url=url,
        data=body,
        method=method,
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        content = response.read().decode("utf-8").strip()
        if not content:
            return None
        return json.loads(content)


def _fetch_batch(offset: int) -> list[dict[str, Any]]:
    rows = _request(
        "GET",
        "/rest/v1/opportunities",
        params={
            "select": "id,source_site,source,listing_url,raw_data",
            "order": "id.asc",
            "limit": PAGE_SIZE,
            "offset": offset,
        },
    )
    return rows or []


def _patch_row(row_id: Any, source_site: str) -> None:
    _request(
        "PATCH",
        "/rest/v1/opportunities",
        params={"id": f"eq.{row_id}"},
        payload={"source_site": source_site},
    )


def main() -> int:
    updated = 0
    skipped = 0
    offset = 0

    print("Starting source_site backfill...")

    try:
        while True:
            rows = _fetch_batch(offset)
            if not rows:
                break

            for row in rows:
                row_id = row.get("id")
                current_source = str(row.get("source_site") or "").strip().lower()
                inferred_source = infer_source_site(row)
                if current_source and current_source not in {"", "unknown", "null", "none"}:
                    skipped += 1
                    continue
                if not inferred_source:
                    skipped += 1
                    continue
                _patch_row(row_id, inferred_source)
                updated += 1
                print(f"[{updated}] Updated id={row_id} source_site={inferred_source}")

            offset += len(rows)
    except urllib.error.URLError as exc:
        print(f"Backfill failed: unable to reach Supabase REST API ({exc}).")
        return 1

    print(f"Backfill complete. updated={updated} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
