"""Orchestrates all scrapers and persists results."""
import asyncio
import csv
import json
import logging
import os

try:
    import yaml
except ImportError:  # pragma: no cover - exercised in minimal local environments
    from backend import yaml_compat as yaml

from .scrapers.registry import get_scrapers

_BACKEND_ROOT = os.path.dirname(os.path.dirname(__file__))
CONFIGS_DIR = os.path.join(_BACKEND_ROOT, "config")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(_BACKEND_ROOT, "..", "data"))


def _load_cfg():
    with open(os.path.join(CONFIGS_DIR, "sources.yml")) as f:
        return yaml.safe_load(f)


def _load_rust_states():
    with open(os.path.join(CONFIGS_DIR, "states.yml")) as f:
        return set(yaml.safe_load(f).get("whitelist_states", []))


def _csv_guard(value) -> str:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return str(value) if value is not None else ""


LISTING_FIELDS = [
    "source_site", "listing_url", "auction_end", "year", "make", "model",
    "trim", "mileage", "current_bid", "location", "state", "vin", "photo_url", "description",
]


async def run_scrapers() -> list:
    """Run all scrapers concurrently and return a flat list of PublicListing objects."""
    cfg = _load_cfg()
    scrapers = get_scrapers(cfg)

    async def _collect(scraper):
        results = []
        async for item in scraper.fetch():
            results.append(item)
        return results

    tasks = [_collect(s) for s in scrapers]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)

    listings = []
    for result in gathered:
        if isinstance(result, Exception):
            logging.error(f"Scraper failed: {result}")
        else:
            listings.extend(result)
    return listings


async def main():
    """Full scrape pipeline: fetch, filter rust states, write CSV."""
    os.makedirs(DATA_DIR, exist_ok=True)
    non_rust_states = _load_rust_states()
    listings = await run_scrapers()

    exceptions_path = os.path.join(DATA_DIR, "no_rust_exception_list.csv")
    accepted_path = os.path.join(DATA_DIR, "scraped_listings.csv")

    with open(exceptions_path, "w", newline="") as fex, \
         open(accepted_path, "w", newline="") as facc:
        wex = csv.writer(fex)
        wacc = csv.writer(facc)
        wex.writerow(LISTING_FIELDS)
        wacc.writerow(LISTING_FIELDS)

        for item in listings:
            row = [_csv_guard(getattr(item, k, "")) for k in LISTING_FIELDS]
            is_ok_state = item.state in non_rust_states
            has_rust_disclaimer = "no rust" in (item.description or "").lower()
            if not is_ok_state and not has_rust_disclaimer:
                wex.writerow(row)
            else:
                wacc.writerow(row)

    logging.info(f"Scraped {len(listings)} listings → {accepted_path}")
    return listings
