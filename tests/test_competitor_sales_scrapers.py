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
    write_competitor_sales,
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


class _FakeCompetitorSalesTable:
    def __init__(self, failures=None, existing_by_url=None):
        self.calls = []
        self.select_calls = []
        self.delete_calls = []
        self._failures = list(failures or [])
        self._existing_by_url = existing_by_url or {}
        self._mode = None
        self._filters = {}

    def upsert(self, payload, **options):
        self._mode = "upsert"
        self.calls.append({"payload": payload, "options": options})
        return self

    def select(self, columns):
        self._mode = "select"
        self._filters = {}
        self.select_calls.append({"columns": columns, "filters": self._filters})
        return self

    def delete(self):
        self._mode = "delete"
        self._filters = {}
        self.delete_calls.append({"filters": self._filters})
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def is_(self, column, value):
        self._filters[column] = value
        return self

    def limit(self, value):
        self._filters["limit"] = value
        return self

    def execute(self):
        if self._mode == "select":
            key = (self._filters.get("source"), self._filters.get("listing_url"))
            row = self._existing_by_url.get(key)
            return type("Resp", (), {"data": [row] if row else []})()
        if self._mode == "delete":
            return type("Resp", (), {"data": [{"deleted": True}]})()
        if self._failures:
            failure = self._failures.pop(0)
            if failure is not None:
                raise failure
        return type("Resp", (), {"data": self.calls[-1]["payload"]})()


class _FakeSupabaseClient:
    def __init__(self, failures=None, existing_by_url=None):
        self.sales_table = _FakeCompetitorSalesTable(
            failures=failures,
            existing_by_url=existing_by_url,
        )

    def table(self, name):
        assert name == "competitor_sales"
        return self.sales_table


def test_write_competitor_sales_uses_listing_id_conflict_when_available():
    client = _FakeSupabaseClient()
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": "asset-1",
            "listing_url": "https://www.govdeals.com/asset/asset-1",
            "sale_price": 1000,
        },
        {
            "source": "govdeals",
            "source_listing_id": None,
            "listing_url": "https://www.govdeals.com/asset/asset-2",
            "sale_price": 2000,
        },
    ]

    assert write_competitor_sales(rows, client) == 2

    assert len(client.sales_table.calls) == 2
    assert client.sales_table.calls[0]["options"]["on_conflict"] == "source,source_listing_id"
    assert client.sales_table.calls[0]["payload"][0]["source_listing_id"] == "asset-1"
    assert client.sales_table.calls[1]["options"]["on_conflict"] == "source,listing_url"
    assert "source_listing_id" not in client.sales_table.calls[1]["payload"][0]


def test_write_competitor_sales_retries_only_url_conflicting_id_backed_rows():
    client = _FakeSupabaseClient(
        failures=[
            RuntimeError("duplicate key violates idx_competitor_sales_source_url_upsert"),
            None,
            RuntimeError("duplicate key violates idx_competitor_sales_source_url_upsert"),
        ]
    )
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": "17000",
            "listing_url": "https://www.govdeals.com/en/asset/17000/7167",
            "sale_price": 2500,
        },
        {
            "source": "govdeals",
            "source_listing_id": "17167",
            "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
            "sale_price": 3074,
        },
    ]

    assert write_competitor_sales(rows, client) == 2

    assert len(client.sales_table.calls) == 4
    assert client.sales_table.calls[0]["options"]["on_conflict"] == "source,source_listing_id"
    assert [r["source_listing_id"] for r in client.sales_table.calls[0]["payload"]] == ["17000", "17167"]
    assert client.sales_table.calls[1]["options"]["on_conflict"] == "source,source_listing_id"
    assert client.sales_table.calls[1]["payload"][0]["source_listing_id"] == "17000"
    assert client.sales_table.calls[2]["options"]["on_conflict"] == "source,source_listing_id"
    assert client.sales_table.calls[2]["payload"][0]["source_listing_id"] == "17167"
    assert client.sales_table.calls[3]["options"]["on_conflict"] == "source,source_listing_id"
    assert client.sales_table.calls[3]["payload"][0]["source_listing_id"] == "17167"


def test_write_competitor_sales_does_not_overwrite_conflicting_existing_listing_id():
    client = _FakeSupabaseClient(
        failures=[
            RuntimeError(
                'duplicate key value violates unique constraint '
                '"idx_competitor_sales_source_url_upsert"'
            ),
            RuntimeError(
                'duplicate key value violates unique constraint '
                '"idx_competitor_sales_source_url_upsert"'
            ),
        ],
        existing_by_url={
            ("govdeals", "https://www.govdeals.com/en/asset/17167/7167"): {
                "source_listing_id": "different-stable-id"
            }
        },
    )
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": "17167",
            "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
            "sale_price": 3074,
        },
    ]

    assert write_competitor_sales(rows, client) == 0

    assert len(client.sales_table.calls) == 2
    assert all(call["options"]["on_conflict"] == "source,source_listing_id" for call in client.sales_table.calls)
    assert client.sales_table.select_calls == [
        {
            "columns": "source_listing_id",
            "filters": {
                "source": "govdeals",
                "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
                "limit": 1,
            },
        }
    ]


def test_write_competitor_sales_url_fallback_can_claim_url_only_existing_row():
    client = _FakeSupabaseClient(
        failures=[
            RuntimeError(
                'duplicate key value violates unique constraint '
                '"idx_competitor_sales_source_url_upsert"'
            ),
            RuntimeError(
                'duplicate key value violates unique constraint '
                '"idx_competitor_sales_source_url_upsert"'
            ),
        ],
        existing_by_url={
            ("govdeals", "https://www.govdeals.com/en/asset/17167/7167"): {
                "source_listing_id": None
            }
        },
    )
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": "17167",
            "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
            "sale_price": 3074,
        },
    ]

    assert write_competitor_sales(rows, client) == 1

    assert len(client.sales_table.calls) == 3
    assert client.sales_table.delete_calls[0]["filters"] == {
        "source": "govdeals",
        "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
        "source_listing_id": "null",
    }
    assert client.sales_table.calls[2]["options"]["on_conflict"] == "source,source_listing_id"
    assert client.sales_table.calls[2]["payload"][0]["source_listing_id"] == "17167"


def test_write_competitor_sales_deletes_url_only_duplicate_then_retries_listing_id():
    client = _FakeSupabaseClient(
        failures=[
            RuntimeError(
                'duplicate key value violates unique constraint '
                '"idx_competitor_sales_source_url_upsert"'
            ),
            RuntimeError(
                'duplicate key value violates unique constraint '
                '"idx_competitor_sales_source_url_upsert"'
            ),
            None,
        ],
        existing_by_url={
            ("govdeals", "https://www.govdeals.com/en/asset/17167/7167"): {
                "source_listing_id": None
            }
        },
    )
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": "17167",
            "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
            "sale_price": 3074,
        },
    ]

    assert write_competitor_sales(rows, client) == 1

    assert len(client.sales_table.delete_calls) == 1
    assert client.sales_table.delete_calls[0]["filters"] == {
        "source": "govdeals",
        "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
        "source_listing_id": "null",
    }
    assert len(client.sales_table.calls) == 3
    assert client.sales_table.calls[2]["options"]["on_conflict"] == "source,source_listing_id"
    assert client.sales_table.calls[2]["payload"][0]["source_listing_id"] == "17167"


def test_write_competitor_sales_retries_url_only_rows_individually_after_batch_failure():
    client = _FakeSupabaseClient(
        failures=[
            RuntimeError("temporary postgrest batch failure"),
            None,
            RuntimeError("row still malformed"),
        ]
    )
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": None,
            "listing_url": "https://www.govdeals.com/en/asset/17000/7167",
            "sale_price": 2500,
        },
        {
            "source": "govdeals",
            "source_listing_id": None,
            "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
            "sale_price": 3074,
        },
    ]

    assert write_competitor_sales(rows, client) == 1

    assert len(client.sales_table.calls) == 3
    assert client.sales_table.calls[0]["options"]["on_conflict"] == "source,listing_url"
    assert len(client.sales_table.calls[0]["payload"]) == 2
    assert client.sales_table.calls[1]["payload"][0]["listing_url"].endswith("/17000/7167")
    assert client.sales_table.calls[2]["payload"][0]["listing_url"].endswith("/17167/7167")


def test_write_competitor_sales_does_not_retry_unrelated_source_url_errors():
    client = _FakeSupabaseClient(failures=[RuntimeError("source_url parser timeout")])
    rows = [
        {
            "source": "govdeals",
            "source_listing_id": "17167",
            "listing_url": "https://www.govdeals.com/en/asset/17167/7167",
            "sale_price": 3074,
        },
    ]

    assert write_competitor_sales(rows, client) == 0

    assert len(client.sales_table.calls) == 1
    assert client.sales_table.calls[0]["options"]["on_conflict"] == "source,source_listing_id"


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
