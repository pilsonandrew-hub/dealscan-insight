import os

from .govdeals import GovDealsScraper
from .govdeals_live import GovDealsLive
from .publicsurplus import PublicSurplusScraper
from .structures import PublicListing

USE_LIVE_GOVDEALS = os.getenv("USE_LIVE_GOVDEALS", "0") == "1"


def get_scrapers(cfg):
    scrapers = []
    for group, items in cfg.get("sources", {}).items():
        for spec in items:
            name = spec.get("name")
            if name == "GovDeals":
                if USE_LIVE_GOVDEALS:

                    class _LiveAdapter:
                        async def fetch(self_inner):
                            for row in GovDealsLive().iter_rows(pages=2):
                                yield PublicListing(
                                    source_site="GovDeals",
                                    listing_url=(
                                        f"https://www.govdeals.com{row['url']}"
                                        if row["url"]
                                        else "https://govdeals.com/unknown"
                                    ),
                                    auction_end=row["end"] or "",
                                    year=row["year"] or 0,
                                    make=row["make"] or "",
                                    model=row["model"] or "",
                                    trim="",
                                    mileage=0,
                                    current_bid=row["bid"] or 0.0,
                                    location="",
                                    state=row["state"] or "",
                                    vin=None,
                                    description=row["desc"] or row["title"] or "",
                                )

                    scrapers.append(_LiveAdapter())
                else:
                    scrapers.append(GovDealsScraper(spec))
            elif name == "PublicSurplus":
                scrapers.append(PublicSurplusScraper(spec))
    return scrapers
