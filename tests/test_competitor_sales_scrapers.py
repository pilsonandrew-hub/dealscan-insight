import os
import sys
import time
import asyncio
import httpx

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.scrapers.competitor_sales.base import (
    RateLimiter,
    build_competitor_sale_row,
    dedup_key,
    extract_vin,
    normalize_state,
)
from backend.scrapers.competitor_sales.govdeals import normalize_govdeals_lot
from backend.scrapers.competitor_sales import govdeals
from backend.scrapers.competitor_sales.govplanet import normalize_govplanet_record
from backend.scrapers.competitor_sales.publicsurplus import normalize_publicsurplus_record


def test_build_row_requires_positive_price_and_identity():
    assert build_competitor_sale_row(source="govdeals", listing_url="u", sale_price=0, make="Ford", model="F-150") is None
    assert build_competitor_sale_row(source="govdeals", listing_url="u", sale_price=100) is None  # no identity
    row = build_competitor_sale_row(
        source="govdeals", listing_url="u", sale_price="$18,500", make="Ford", model="F-150",
        year="2022", mileage="40,000", location="Dallas, TX",
    )
    assert row["sale_price"] == 18500.0
    assert row["year"] == 2022
    assert row["mileage"] == 40000
    assert row["state"] == "TX"
    assert row["vehicle_class"] == "f-150"
    assert row["currency"] == "USD"


def test_extract_vin_and_state_helpers():
    assert extract_vin("Truck VIN 1FTFW1ET5DFC12345 clean") == "1FTFW1ET5DFC12345"
    assert extract_vin("no vin here") is None
    assert normalize_state("Phoenix, AZ") == "AZ"
    assert normalize_state(None, "ca") == "CA"
    assert normalize_state("Nowhere") is None


def test_dedup_key_prefers_listing_id():
    assert dedup_key("GovDeals", "123", "http://x") == "govdeals|123"
    assert dedup_key("GovDeals", None, "http://x") == "govdeals|http://x"


def test_normalize_govdeals_lot():
    lot = {
        "assetId": "555",
        "winningBid": 23500,
        "modelYear": 2021,
        "makebrand": "Ford",
        "model": "F-250",
        "meterCount": 60000,
        "locationCity": "Austin",
        "locationState": "TX",
        "assetAuctionEndDateUtc": "2026-04-01T00:00:00Z",
        "vin": "1FT7W2BT0MED00000",
    }
    row = normalize_govdeals_lot(lot)
    assert row["source"] == "govdeals"
    assert row["source_listing_id"] == "555"
    assert row["sale_price"] == 23500.0
    assert row["vehicle_class"] == "f-250"
    assert row["state"] == "TX"
    assert row["vin"] == "1FT7W2BT0MED00000"


def test_normalize_govdeals_lot_without_price_is_dropped():
    assert normalize_govdeals_lot({"assetId": "1", "modelYear": 2021, "make": "Ford", "model": "F-150"}) is None


SOLD_GOVDEALS_SEO_HTML = """
<html>
  <head>
    <script id="seoSchemaScript" type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Vehicle",
        "name": "3052A/ 2014 Ford F-150",
        "image": "https://webassets.lqdt1.com/assets/photos/7167/7167_17167_main.jpg",
        "model": "F-150",
        "offers": {
          "@type": "Offer",
          "priceCurrency": "USD",
          "availability": "https://schema.org/SoldOut",
          "url": "https://www.govdeals.com/en/asset/17167/7167",
          "price": 3074
        },
        "seller": {
          "@type": "Organization",
          "name": "Miami-Dade County, FL",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "Doral",
            "addressRegion": "Florida"
          }
        },
        "vehicleModelDate": "2014",
        "vehicleIdentificationNumber": "1FTEX1CM9EFB48531",
        "mileageFromOdometer": {
          "@type": "QuantitativeValue",
          "value": 143553,
          "unitText": "Miles"
        },
        "subjectOf": {
          "@type": "Auction",
          "endDate": "2026-05-16T00:08:00Z"
        },
        "brand": {"@type": "Brand", "name": "Ford"}
      }
    </script>
  </head>
  <body>
    <p id="lblSoldAmount" data-value="3458.25">USD 3,458.25</p>
    <p id="lblTotalAmount" data-value="3700.33">USD 3,700.33</p>
  </body>
</html>
"""


def test_parse_govdeals_seo_asset_normalizes_soldout_vehicle():
    lot = govdeals.parse_govdeals_seo_asset(
        SOLD_GOVDEALS_SEO_HTML,
        "https://prod-seo.govdeals.com/en/asset/17167/7167",
    )

    assert lot["assetId"] == "17167"
    assert lot["accountId"] == "7167"
    assert lot["title"] == "3052A/ 2014 Ford F-150"
    assert lot["make"] == "Ford"
    assert lot["model"] == "F-150"
    assert lot["year"] == 2014
    assert lot["winningBid"] == 3074.0
    assert lot["sold_price_all_in"] == 3458.25
    assert lot["vin"] == "1FTEX1CM9EFB48531"
    assert lot["meterCount"] == 143553
    assert lot["state"] == "FL"
    assert lot["source_discovery"] == "govdeals-seo"


def test_parse_govdeals_seo_asset_rejects_active_vehicle():
    active_html = SOLD_GOVDEALS_SEO_HTML.replace("https://schema.org/SoldOut", "https://schema.org/InStock")

    assert govdeals.parse_govdeals_seo_asset(
        active_html,
        "https://prod-seo.govdeals.com/en/asset/17167/7167",
    ) is None


def test_scrape_govdeals_sold_falls_back_to_explicit_seo_asset_url(monkeypatch):
    async def failing_api(max_pages=None):
        raise RuntimeError("api key unavailable")

    async def fake_fetch_text(client, url):
        if "/en/search" in url:
            return ""
        assert url == "https://prod-seo.govdeals.com/en/asset/17167/7167"
        return SOLD_GOVDEALS_SEO_HTML

    monkeypatch.setattr(govdeals, "_scrape_govdeals_api", failing_api)
    monkeypatch.setattr(govdeals, "_fetch_text", fake_fetch_text)
    monkeypatch.setenv("COMPETITOR_GOVDEALS_SEO_ASSET_URLS", "https://prod-seo.govdeals.com/en/asset/17167/7167")

    rows = asyncio.run(govdeals.scrape_govdeals_sold(max_pages=1))

    assert len(rows) == 1
    assert rows[0]["source"] == "govdeals"
    assert rows[0]["source_listing_id"] == "17167"
    assert rows[0]["sale_price"] == 3074.0
    assert rows[0]["state"] == "FL"
    assert rows[0]["vin"] == "1FTEX1CM9EFB48531"


def test_govdeals_seo_fallback_keeps_max_pages_as_page_budget(monkeypatch):
    async def fake_fetch_text(client, url):
        if "/en/search" in url:
            start = 2000 if "F-250" in url else 1000
            return "\n".join(
                f'<a href="/en/asset/{asset_id}/7167">asset {asset_id}</a>'
                for asset_id in range(start, start + 60)
            )
        return SOLD_GOVDEALS_SEO_HTML

    monkeypatch.setattr(govdeals, "_fetch_text", fake_fetch_text)
    monkeypatch.setattr(govdeals, "_seo_queries", lambda: ["Ford F-150", "Ford F-250"])
    monkeypatch.delenv("COMPETITOR_GOVDEALS_SEO_ASSET_URLS", raising=False)

    rows = asyncio.run(govdeals._scrape_govdeals_seo(max_pages=2))

    assert len(rows) == 48


def test_govdeals_seo_explicit_asset_urls_do_not_trigger_search(monkeypatch):
    async def fake_fetch_text(client, url):
        assert "/en/search" not in url
        return SOLD_GOVDEALS_SEO_HTML

    monkeypatch.setattr(govdeals, "_fetch_text", fake_fetch_text)
    monkeypatch.setenv("COMPETITOR_GOVDEALS_SEO_ASSET_URLS", "https://prod-seo.govdeals.com/en/asset/17167/7167")

    rows = asyncio.run(govdeals._scrape_govdeals_seo(max_pages=1))

    assert len(rows) == 1


def test_govdeals_seo_retries_transient_asset_fetch_failure(monkeypatch):
    class FakeClient:
        def __init__(self):
            self.calls = 0

        async def get(self, url, headers=None):
            self.calls += 1
            request = httpx.Request("GET", url)
            if self.calls == 1:
                return httpx.Response(502, request=request, text="")
            return httpx.Response(200, request=request, text=SOLD_GOVDEALS_SEO_HTML)

    client = FakeClient()

    html = asyncio.run(
        govdeals._fetch_text(
            client,
            "https://prod-seo.govdeals.com/en/asset/17167/7167",
        )
    )

    assert html == SOLD_GOVDEALS_SEO_HTML
    assert client.calls == 2


def test_govdeals_seo_skips_failed_asset_fetches(monkeypatch):
    async def fake_fetch_text(client, url):
        if "/en/search" in url:
            return "\n".join(
                [
                    '<a href="/en/asset/17167/7167">sold</a>',
                    '<a href="/en/asset/228/23609">temporary failure</a>',
                ]
            )
        if "/en/asset/228/23609" in url:
            raise RuntimeError("temporary 502")
        return SOLD_GOVDEALS_SEO_HTML

    monkeypatch.setattr(govdeals, "_fetch_text", fake_fetch_text)
    monkeypatch.setattr(govdeals, "_seo_queries", lambda: ["Ford F-150"])
    monkeypatch.delenv("COMPETITOR_GOVDEALS_SEO_ASSET_URLS", raising=False)

    rows = asyncio.run(govdeals._scrape_govdeals_seo(max_pages=1))

    assert len(rows) == 1


def test_normalize_publicsurplus_record_parses_title():
    record = {
        "auction_id": "987",
        "title": "2020 Chevrolet Silverado 1500 LT",
        "winning_bid": "$21,000",
        "end_date": "2026-03-15T00:00:00Z",
        "location": "Columbus, OH",
    }
    row = normalize_publicsurplus_record(record)
    assert row["source"] == "publicsurplus"
    assert row["make"].lower() == "chevrolet"
    assert row["year"] == 2020
    assert row["vehicle_class"] == "silverado-1500"
    assert row["sale_price"] == 21000.0
    assert row["state"] == "OH"


def test_normalize_govplanet_record():
    record = {
        "itemId": "42",
        "soldAmount": 19500,
        "year": 2023,
        "make": "Ford",
        "model": "F-150 XLT",
        "mileage": 30000,
        "saleDate": "2026-02-20T00:00:00Z",
        "location": "Reno, NV",
        "vin": "1FTFW1E84PFA00000",
    }
    row = normalize_govplanet_record(record)
    assert row["source"] == "govplanet"
    assert row["source_listing_id"] == "42"
    assert row["sale_price"] == 19500.0
    assert row["vehicle_class"] == "f-150"
    assert row["state"] == "NV"


def test_rate_limiter_enforces_min_interval():
    limiter = RateLimiter(min_interval=0.05)
    limiter.wait()
    start = time.monotonic()
    limiter.wait()
    assert time.monotonic() - start >= 0.04
