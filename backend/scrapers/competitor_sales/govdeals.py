"""GovDeals completed-auction scraper -> competitor_sales rows.

Reuses the proven maestro API-key interception flow from
``backend.scrapers.govdeals_sold`` and normalizes lots into the competitor_sales
schema (instead of dealer_sales).
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import httpx

from backend.scrapers.competitor_sales.base import (
    build_competitor_sale_row,
    extract_vin,
    _to_float as _numeric,
)

logger = logging.getLogger(__name__)

SOURCE = "govdeals"
SEO_BASE_URL = "https://prod-seo.govdeals.com"
GOVDEALS_BASE_URL = "https://www.govdeals.com"
ASSET_PATH_RE = re.compile(r"/en/asset/(\d+)/(\d+)", re.IGNORECASE)
DEFAULT_SEO_QUERIES = (
    "f-150",
    "f-250",
    "silverado 1500",
    "silverado 2500",
    "ram 1500",
    "ram 2500",
)
SEO_ASSETS_PER_PAGE = 24
SEO_FETCH_ATTEMPTS = 3
SEO_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}
STATE_NAME_TO_CODE = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "district of columbia": "DC",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
}
SEO_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "referer": "https://www.govdeals.com/",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "upgrade-insecure-requests": "1",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
}


def _condition_notes(lot: Dict[str, Any]) -> Optional[str]:
    for key in ("assetShortDescription", "longDescription", "itemDescription", "description", "notes"):
        value = lot.get(key)
        if value:
            return str(value)[:1000]
    return None


def normalize_govdeals_lot(lot: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a GovDeals completed-auction lot into a competitor_sales row."""
    sold_price = (
        lot.get("winningBid")
        or lot.get("soldPrice")
        or lot.get("assetWinningBid")
        or lot.get("closingBid")
        or lot.get("awardAmount")
    )
    asset_id = lot.get("assetId", "")
    account_id = lot.get("accountId", "")
    listing_url = lot.get("url") or f"https://www.govdeals.com/asset/{asset_id}/{account_id}"
    city = lot.get("locationCity") or lot.get("city") or ""
    state = lot.get("locationState") or lot.get("state") or ""
    location = ", ".join(part for part in (city, state) if part) or None

    return build_competitor_sale_row(
        source=SOURCE,
        source_listing_id=str(asset_id) or None,
        listing_url=listing_url,
        vin=extract_vin(
            lot.get("vin"),
            lot.get("assetShortDescription"),
            lot.get("longDescription"),
            lot.get("itemDescription"),
            lot.get("description"),
        ),
        year=lot.get("modelYear") or lot.get("year"),
        make=lot.get("makebrand") or lot.get("make"),
        model=lot.get("model"),
        mileage=lot.get("meterCount"),
        sale_price=sold_price,
        auction_end_date=lot.get("assetAuctionEndDateUtc") or lot.get("auctionEndUtc"),
        condition_notes=_condition_notes(lot),
        location=location,
        state=state,
        raw=lot,
    )


def _arrayify(value: Any) -> List[Any]:
    return value if isinstance(value, list) else [value]


def _schema_type_matches(schema: Dict[str, Any], schema_type: str) -> bool:
    values = [str(item or "").lower() for item in _arrayify(schema.get("@type"))]
    return schema_type.lower() in values


def _find_vehicle_schema(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    if _schema_type_matches(value, "Vehicle"):
        return value
    for key in ("@graph", "itemListElement"):
        children = value.get(key)
        if not isinstance(children, list):
            continue
        for child in children:
            found = _find_vehicle_schema(child.get("item") if isinstance(child, dict) else child)
            if found:
                return found
    return None


def _json_ld_blocks(page_html: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    pattern = re.compile(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>([\s\S]*?)</script>",
        re.IGNORECASE,
    )
    for match in pattern.finditer(page_html or ""):
        text = html.unescape(match.group(1) or "").strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            blocks.append(parsed)
    return blocks


def _extract_data_value(page_html: str, element_id: str) -> Optional[float]:
    pattern = re.compile(
        rf"<[^>]+id=[\"']{re.escape(element_id)}[\"'][^>]*data-value=[\"']([^\"']+)[\"'][^>]*>",
        re.IGNORECASE,
    )
    match = pattern.search(page_html or "")
    if match:
        return _numeric(html.unescape(match.group(1)))
    text_pattern = re.compile(
        rf"<[^>]+id=[\"']{re.escape(element_id)}[\"'][^>]*>([\s\S]*?)</[^>]+>",
        re.IGNORECASE,
    )
    text_match = text_pattern.search(page_html or "")
    if not text_match:
        return None
    return _numeric(re.sub(r"<[^>]+>", "", html.unescape(text_match.group(1))))


def _canonical_seo_asset_url(url: Any) -> Optional[str]:
    match = ASSET_PATH_RE.search(str(url or ""))
    if not match:
        return None
    return f"{SEO_BASE_URL}/en/asset/{match.group(1)}/{match.group(2)}"


def _make_from_schema(schema: Dict[str, Any]) -> str:
    brand = schema.get("brand")
    if isinstance(brand, str):
        return brand
    if isinstance(brand, dict) and brand.get("name"):
        return str(brand["name"])
    title = str(schema.get("name") or "")
    for candidate in ("Ford", "Chevrolet", "Ram"):
        if re.search(rf"\b{re.escape(candidate)}\b", title, re.IGNORECASE):
            return candidate
    return ""


def _state_from_address(address: Any) -> str:
    if not isinstance(address, dict):
        return ""
    raw = str(address.get("addressRegion") or address.get("addressState") or address.get("region") or "").strip()
    if len(raw) == 2:
        return raw.upper()
    return STATE_NAME_TO_CODE.get(raw.lower(), raw)


def extract_seo_asset_urls(page_html: str, limit: Optional[int] = None) -> List[str]:
    urls: List[str] = []
    seen = set()
    for match in ASSET_PATH_RE.finditer(page_html or ""):
        url = f"{SEO_BASE_URL}/en/asset/{match.group(1)}/{match.group(2)}"
        if url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if limit and len(urls) >= limit:
            break
    return urls


def parse_govdeals_seo_asset(page_html: str, asset_url: str) -> Optional[Dict[str, Any]]:
    """Parse a GovDeals SEO asset page into the lot shape used by normalization."""
    vehicle_schema = next(
        (schema for schema in (_find_vehicle_schema(block) for block in _json_ld_blocks(page_html)) if schema),
        None,
    )
    if not vehicle_schema:
        return None

    offers = vehicle_schema.get("offers")
    offer = offers[0] if isinstance(offers, list) and offers else offers
    if not isinstance(offer, dict):
        return None
    availability = str(offer.get("availability") or "").lower()
    if "soldout" not in availability:
        return None

    canonical_url = (
        _canonical_seo_asset_url(asset_url)
        or _canonical_seo_asset_url(offer.get("url"))
        or _canonical_seo_asset_url(vehicle_schema.get("url"))
    )
    if not canonical_url:
        return None
    asset_match = ASSET_PATH_RE.search(canonical_url)
    if not asset_match:
        return None

    seller = vehicle_schema.get("seller") if isinstance(vehicle_schema.get("seller"), dict) else {}
    address = seller.get("address") if isinstance(seller, dict) and isinstance(seller.get("address"), dict) else {}
    auction = vehicle_schema.get("subjectOf") if isinstance(vehicle_schema.get("subjectOf"), dict) else {}
    make = _make_from_schema(vehicle_schema)
    hammer_price = _numeric(offer.get("price"))
    sold_amount = _extract_data_value(page_html, "lblSoldAmount")
    total_price = _extract_data_value(page_html, "lblTotalAmount")

    return {
        "assetId": asset_match.group(1),
        "accountId": asset_match.group(2),
        "assetShortDescription": vehicle_schema.get("name") or "",
        "title": vehicle_schema.get("name") or "",
        "makebrand": make,
        "make": make,
        "model": vehicle_schema.get("model") or "",
        "modelYear": _numeric(vehicle_schema.get("vehicleModelDate")),
        "year": _numeric(vehicle_schema.get("vehicleModelDate")),
        "winningBid": hammer_price,
        "soldPrice": hammer_price,
        "assetWinningBid": hammer_price,
        "sold_price_all_in": sold_amount or total_price,
        "total_price": total_price,
        "locationCity": address.get("addressLocality") or "",
        "locationState": _state_from_address(address),
        "city": address.get("addressLocality") or "",
        "state": _state_from_address(address),
        "auctionEndUtc": auction.get("endDate"),
        "assetAuctionEndDateUtc": auction.get("endDate"),
        "url": canonical_url.replace(SEO_BASE_URL, GOVDEALS_BASE_URL),
        "listing_url": canonical_url.replace(SEO_BASE_URL, GOVDEALS_BASE_URL),
        "displaySellerName": seller.get("name") if isinstance(seller, dict) else "",
        "seller": seller.get("name") if isinstance(seller, dict) else "",
        "imageUrl": vehicle_schema.get("image") or "",
        "vin": vehicle_schema.get("vehicleIdentificationNumber"),
        "meterCount": _numeric(
            (vehicle_schema.get("mileageFromOdometer") or {}).get("value")
            if isinstance(vehicle_schema.get("mileageFromOdometer"), dict)
            else None
        ),
        "source_site": "govdeals-sold",
        "source_discovery": "govdeals-seo",
    }


def _seo_search_url(query: str) -> str:
    return f"{SEO_BASE_URL}/en/search?keyword={quote(str(query).strip())}&timing=completed"


def _explicit_seo_asset_urls() -> List[str]:
    raw = os.getenv("COMPETITOR_GOVDEALS_SEO_ASSET_URLS", "")
    urls: List[str] = []
    for chunk in re.split(r"[\n,]+", raw):
        url = _canonical_seo_asset_url(chunk.strip())
        if url and url not in urls:
            urls.append(url)
    return urls


def _seo_queries() -> List[str]:
    raw = os.getenv("COMPETITOR_GOVDEALS_SEO_QUERIES", "")
    values = [chunk.strip() for chunk in re.split(r"[\n,]+", raw) if chunk.strip()]
    return values or list(DEFAULT_SEO_QUERIES)


async def _fetch_text(client: httpx.AsyncClient, url: str) -> str:
    last_error: Optional[Exception] = None
    for attempt in range(1, SEO_FETCH_ATTEMPTS + 1):
        try:
            response = await client.get(url, headers=SEO_HEADERS)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            last_error = exc
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code not in SEO_TRANSIENT_STATUS_CODES or attempt >= SEO_FETCH_ATTEMPTS:
                raise
            logger.warning(
                "[%s] SEO fetch transient HTTP %s for %s attempt=%d/%d",
                SOURCE,
                status_code,
                url,
                attempt,
                SEO_FETCH_ATTEMPTS,
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt >= SEO_FETCH_ATTEMPTS:
                raise
            logger.warning(
                "[%s] SEO fetch transient %s for %s attempt=%d/%d",
                SOURCE,
                type(exc).__name__,
                url,
                attempt,
                SEO_FETCH_ATTEMPTS,
            )
        await asyncio.sleep(0.5 * attempt)
    if last_error:
        raise last_error
    raise RuntimeError(f"{SOURCE} SEO fetch failed for {url}")


async def _scrape_govdeals_seo(max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    page_limit = max(1, int(max_pages or 1))
    asset_limit = page_limit * SEO_ASSETS_PER_PAGE
    discovered: List[str] = []
    rows: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        explicit_urls = _explicit_seo_asset_urls()
        for asset_url in explicit_urls:
            if asset_url not in discovered:
                discovered.append(asset_url)

        if not explicit_urls:
            for query in _seo_queries():
                if len(discovered) >= asset_limit:
                    break
                search_html = await _fetch_text(client, _seo_search_url(query))
                for asset_url in extract_seo_asset_urls(search_html, limit=SEO_ASSETS_PER_PAGE):
                    if asset_url not in discovered:
                        discovered.append(asset_url)
                    if len(discovered) >= asset_limit:
                        break

        for asset_url in discovered[:asset_limit]:
            try:
                lot = parse_govdeals_seo_asset(await _fetch_text(client, asset_url), asset_url)
            except Exception as exc:
                logger.warning("[%s] SEO asset fetch failed for %s: %s: %s", SOURCE, asset_url, type(exc).__name__, exc)
                continue
            if lot is None:
                continue
            row = normalize_govdeals_lot(lot)
            if row is not None:
                rows.append(row)

    logger.info(
        "[%s] SEO fallback parsed %d sold rows from %d assets",
        SOURCE,
        len(rows),
        len(discovered[:asset_limit]),
    )
    return rows


async def _scrape_govdeals_api(max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    from playwright.async_api import async_playwright

    from backend.scrapers import govdeals_sold

    if max_pages is not None:
        govdeals_sold.MAX_PAGES = max_pages

    rows: List[Dict[str, Any]] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()
        try:
            api_key, headers = await govdeals_sold.capture_api_key(page)
            if not api_key:
                raise RuntimeError(f"{SOURCE} failed to capture completed-auction API key")
            lots = await govdeals_sold.fetch_completed_auctions(api_key, headers)
            logger.info("[%s] fetched %d completed lots", SOURCE, len(lots))
            for lot in lots:
                row = normalize_govdeals_lot(lot)
                if row is not None:
                    rows.append(row)
        finally:
            await browser.close()
    return rows


async def scrape_govdeals_sold(max_pages: Optional[int] = None) -> List[Dict[str, Any]]:
    """Scrape GovDeals completed auctions and return competitor_sales rows."""
    try:
        rows = await _scrape_govdeals_api(max_pages=max_pages)
        if rows:
            return rows
        logger.warning("[%s] API path returned zero rows; trying SEO fallback", SOURCE)
    except Exception as exc:
        logger.warning("[%s] API path failed: %s; trying SEO fallback", SOURCE, exc)
    return await _scrape_govdeals_seo(max_pages=max_pages)
