"""Source-site normalization helpers for DealerScope ingest.

This module preserves the existing ingest.py source inference behavior while making
it independently testable before larger normalization extraction work.
"""

from __future__ import annotations

from typing import Any, Optional

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


def canonical_source_site(raw_value: Any) -> str:
    """Return the canonical source-site key for a raw source value."""
    text = str(raw_value or "").strip().lower()
    if not text or text in {"apify", "none", "null", "unknown"}:
        return ""
    if text in SOURCE_SITE_ALIASES:
        return SOURCE_SITE_ALIASES[text]
    normalized = text.replace("_", "-")
    return SOURCE_SITE_ALIASES.get(normalized, "")


def source_site_from_url(url: str) -> str:
    """Infer source-site key from known auction URL host hints."""
    lowered = (url or "").strip().lower()
    if not lowered:
        return ""
    for needle, source_site in SOURCE_SITE_URL_HINTS:
        if needle in lowered:
            return source_site
    return ""


def infer_source_site(item: dict, *, source_hint: Optional[str] = None) -> Optional[str]:
    """Infer a canonical source-site key from item fields, hint, then URL fields."""
    for candidate in (
        item.get("source_site"),
        item.get("source"),
        source_hint,
    ):
        source_site = canonical_source_site(candidate)
        if source_site:
            return source_site

    for candidate in (
        item.get("listing_url"),
        item.get("auction_url"),
        item.get("url"),
    ):
        source_site = source_site_from_url(str(candidate or ""))
        if source_site:
            return source_site

    return None
