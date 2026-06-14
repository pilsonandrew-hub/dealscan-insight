# Market-Data Provenance Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make market-data provenance, freshness, fallback share, and pricing-quality degraded states explicit in DealerScope internal truth and Supabase live-inspection proof.

**Architecture:** Add a deterministic read-only `market_data_quality` contract computed from existing persisted opportunity and pricing-substrate fields. Expose it in `GET /api/internal/pipeline-truth` and mirror the same aggregate contract in `scripts/supabase_live_inspection.py`; do not change score or alert behavior in this pass.

**Tech Stack:** Python, FastAPI internal router, Supabase REST proof script, pytest.

---

## File Map

- Modify: `tests/test_internal_pipeline_truth.py`
  - Add RED tests for internal `market_data_quality`.
- Modify: `webapp/routers/internal.py`
  - Add pure helpers for market-data quality aggregation.
  - Add `market_data_quality` to `build_pipeline_truth()`.
- Modify: `tests/test_supabase_live_inspection.py`
  - Add RED tests for live-inspection `market_data_quality`.
- Modify: `scripts/supabase_live_inspection.py`
  - Mirror the sanitized market-data quality contract.
- Optional only if duplication becomes unsafe: create `backend/ingest/market_data_quality.py`
  - Use only if both router and script would otherwise carry large divergent logic.

## Contract Constants

Use these values unless a test proves they need adjustment:

```python
MARKET_DATA_PROXY_SHARE_DEGRADED_THRESHOLD = 0.25
MARKET_DATA_FRESHNESS_THRESHOLD_HOURS = 24.0
MARKET_DATA_MIN_RETAIL_COMP_COUNT = 2
```

Stable reason keys:

```python
NO_ACTIVE_PRICING_SAMPLE = "no_active_pricing_sample"
PRICING_FIELDS_MISSING = "pricing_fields_missing"
PROXY_SHARE_HIGH = "proxy_pricing_share_above_threshold"
HIGH_SCORE_PROXY_PRESENT = "high_score_proxy_pricing_present"
PRICING_STALE = "pricing_evidence_stale"
RETAIL_COMPS_SPARSE = "retail_comps_sparse"
MANHEIM_LIVE_SHARE_LOW = "manheim_live_share_below_threshold"
MARKET_PRICES_UNUSABLE = "market_prices_unusable"
DEALER_SALES_SPARSE = "dealer_sales_sparse"
```

Status values:

```python
healthy
degraded
unavailable
unknown
```

---

### Task 1: Internal Pipeline Truth RED Tests

**Files:**
- Modify: `tests/test_internal_pipeline_truth.py`

- [ ] **Step 1: Add RED test for degraded proxy-heavy market data**

Append near the existing pipeline truth tests:

```python
def test_pipeline_truth_reports_market_data_quality_degraded_for_proxy_heavy_sample(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "proxy-high-score",
                "is_active": True,
                "dos_score": 86,
                "score": 86,
                "source_site": "govdeals",
                "pricing_maturity": "proxy",
                "pricing_source": "mmr_proxy",
                "pricing_updated_at": "2026-06-13T01:00:00+00:00",
                "manheim_source_status": "fallback",
                "manheim_updated_at": None,
                "retail_comp_count": 0,
                "retail_comp_confidence": None,
                "mmr_confidence_proxy": 78,
                "mileage": 25000,
                "year": 2025,
                "vin": "1FMUK8DH5SGA77978",
                "condition_grade": "Good",
                "investment_grade": "Rejected",
            },
            {
                "id": "market-comp",
                "is_active": True,
                "dos_score": 72,
                "score": 72,
                "source_site": "govdeals",
                "pricing_maturity": "market_comp",
                "pricing_source": "retail_comp",
                "pricing_updated_at": "2026-06-13T02:00:00+00:00",
                "manheim_source_status": "unavailable",
                "retail_comp_count": 3,
                "retail_comp_confidence": 0.72,
                "mmr_confidence_proxy": 88,
                "mileage": 21000,
                "year": 2024,
                "vin": "1HGCM82633A004352",
                "condition_grade": "Good",
                "investment_grade": "Gold",
            },
        ],
        "webhook_log": [],
        "alert_log": [],
        "ingest_delivery_log": [],
        "dealer_sales": [],
        "market_prices": [],
    }))

    result = internal.build_pipeline_truth()

    quality = result["market_data_quality"]
    assert quality["status"] == "degraded"
    assert quality["active_sample_size"] == 2
    assert quality["high_score_sample_size"] == 1
    assert quality["pricing_maturity_counts"] == {"proxy": 1, "market_comp": 1}
    assert quality["high_score_pricing_maturity_counts"] == {"proxy": 1}
    assert quality["manheim_source_status_counts"] == {"fallback": 1, "unavailable": 1}
    assert quality["proxy_share"] == 0.5
    assert quality["high_score_proxy_share"] == 1.0
    assert quality["fallback_share"] == 0.5
    assert quality["latest_pricing_updated_at"] == "2026-06-13T02:00:00+00:00"
    assert "proxy_pricing_share_above_threshold" in quality["degraded_reasons"]
    assert "high_score_proxy_pricing_present" in quality["degraded_reasons"]
    assert "truth_boundary" in quality
```

- [ ] **Step 2: Add RED test for healthy fresh non-proxy pricing**

```python
def test_pipeline_truth_reports_market_data_quality_healthy_for_fresh_non_proxy_sample(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "live-market",
                "is_active": True,
                "dos_score": 82,
                "score": 82,
                "source_site": "proxibid",
                "pricing_maturity": "live_market",
                "pricing_source": "live_manheim",
                "pricing_updated_at": "2099-01-01T00:00:00+00:00",
                "manheim_source_status": "live",
                "manheim_updated_at": "2099-01-01T00:00:00+00:00",
                "retail_comp_count": 3,
                "retail_comp_confidence": 0.91,
                "mmr_confidence_proxy": 94,
                "mileage": 18000,
                "year": 2025,
                "vin": "1FMUK8DH5SGA77978",
                "condition_grade": "Good",
                "investment_grade": "Platinum",
            },
        ],
        "webhook_log": [],
        "alert_log": [],
        "ingest_delivery_log": [],
        "dealer_sales": [
            {"id": "sale-1", "sale_price": 22000, "sale_date": "2099-01-01T00:00:00+00:00"},
            {"id": "sale-2", "sale_price": 23000, "sale_date": "2099-01-02T00:00:00+00:00"},
        ],
        "market_prices": [
            {
                "id": "market-1",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "source": "seeded_market_comp",
            },
        ],
    }))

    result = internal.build_pipeline_truth()

    quality = result["market_data_quality"]
    assert quality["status"] == "healthy"
    assert quality["proxy_share"] == 0.0
    assert quality["high_score_proxy_share"] == 0.0
    assert quality["freshness"]["status"] == "fresh"
    assert quality["degraded_reasons"] == []
    assert quality["unavailable_dimensions"] == []
```

- [ ] **Step 3: Run RED test command**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: failure with `KeyError: 'market_data_quality'`.

- [ ] **Step 4: Commit RED tests only**

```bash
git add tests/test_internal_pipeline_truth.py
git commit -m "test: add market data quality truth contract"
```

---

### Task 2: Internal Pipeline Truth Implementation

**Files:**
- Modify: `webapp/routers/internal.py`
- Test: `tests/test_internal_pipeline_truth.py`

- [ ] **Step 1: Add helper constants below `MID_DEAL_SCORE_THRESHOLD`**

```python
MARKET_DATA_PROXY_SHARE_DEGRADED_THRESHOLD = 0.25
MARKET_DATA_FRESHNESS_THRESHOLD_HOURS = 24.0
MARKET_DATA_MIN_RETAIL_COMP_COUNT = 2
```

- [ ] **Step 2: Add pure helper functions after `_status_counts`**

```python
def _round_share(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _latest_datetime(rows: list[dict[str, Any]], keys: list[str]) -> tuple[Optional[str], Optional[datetime]]:
    latest_raw: Optional[str] = None
    latest_dt: Optional[datetime] = None
    for row in rows:
        for key in keys:
            parsed = _parse_optional_datetime(row.get(key))
            if parsed and (latest_dt is None or parsed > latest_dt):
                latest_dt = parsed
                latest_raw = str(row.get(key))
    return latest_raw, latest_dt


def _market_data_quality(
    rows: list[dict[str, Any]],
    pricing_substrate: dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    active_rows = [row for row in rows if row.get("is_active") is True]
    high_score_rows = [row for row in active_rows if (_numeric_score(row) or 0.0) >= HOT_DEAL_ALERT_THRESHOLD]

    unavailable_dimensions: list[str] = []
    if active_rows and all("pricing_maturity" not in row for row in active_rows):
        unavailable_dimensions.append("pricing_maturity")
    if active_rows and all("manheim_source_status" not in row for row in active_rows):
        unavailable_dimensions.append("manheim_source_status")
    if active_rows and all("pricing_updated_at" not in row and "manheim_updated_at" not in row for row in active_rows):
        unavailable_dimensions.append("pricing_freshness")

    pricing_counts = _status_counts(active_rows, "pricing_maturity")
    high_score_pricing_counts = _status_counts(high_score_rows, "pricing_maturity")
    manheim_counts = _status_counts(active_rows, "manheim_source_status")

    active_count = len(active_rows)
    high_score_count = len(high_score_rows)
    proxy_count = sum(1 for row in active_rows if str(row.get("pricing_maturity") or "").strip().lower() == "proxy")
    high_score_proxy_count = sum(1 for row in high_score_rows if str(row.get("pricing_maturity") or "").strip().lower() == "proxy")
    fallback_count = sum(1 for row in active_rows if str(row.get("manheim_source_status") or "").strip().lower() == "fallback")
    live_count = sum(1 for row in active_rows if str(row.get("manheim_source_status") or "").strip().lower() == "live")

    latest_raw, latest_dt = _latest_datetime(active_rows, ["pricing_updated_at", "manheim_updated_at"])
    latest_age_hours = round((now - latest_dt).total_seconds() / 3600.0, 2) if latest_dt else None
    freshness_status = "fresh" if latest_age_hours is not None and latest_age_hours <= MARKET_DATA_FRESHNESS_THRESHOLD_HOURS else "stale"

    degraded_reasons: list[str] = []
    if not active_rows:
        degraded_reasons.append("no_active_pricing_sample")
    if unavailable_dimensions:
        degraded_reasons.append("pricing_fields_missing")
    if _round_share(proxy_count, active_count) > MARKET_DATA_PROXY_SHARE_DEGRADED_THRESHOLD:
        degraded_reasons.append("proxy_pricing_share_above_threshold")
    if high_score_proxy_count > 0:
        degraded_reasons.append("high_score_proxy_pricing_present")
    if freshness_status == "stale":
        degraded_reasons.append("pricing_evidence_stale")
    if active_rows and all((_as_int(row.get("retail_comp_count")) or 0) < MARKET_DATA_MIN_RETAIL_COMP_COUNT for row in active_rows if str(row.get("pricing_maturity") or "").lower() != "live_market"):
        degraded_reasons.append("retail_comps_sparse")
    if active_rows and live_count == 0 and "manheim_source_status" not in unavailable_dimensions:
        degraded_reasons.append("manheim_live_share_below_threshold")
    if pricing_substrate.get("market_prices_table") == "present" and int(pricing_substrate.get("market_prices_usable_rows") or 0) == 0:
        degraded_reasons.append("market_prices_unusable")
    if pricing_substrate.get("dealer_sales_table") == "present" and int(pricing_substrate.get("dealer_sales_usable_rows") or 0) < 2:
        degraded_reasons.append("dealer_sales_sparse")

    if unavailable_dimensions:
        status = "unknown"
    elif not active_rows:
        status = "unavailable"
    elif degraded_reasons:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "sample_size": len(rows),
        "active_sample_size": active_count,
        "high_score_sample_size": high_score_count,
        "pricing_maturity_counts": pricing_counts,
        "high_score_pricing_maturity_counts": high_score_pricing_counts,
        "manheim_source_status_counts": manheim_counts,
        "fallback_share": _round_share(fallback_count, active_count),
        "proxy_share": _round_share(proxy_count, active_count),
        "high_score_proxy_share": _round_share(high_score_proxy_count, high_score_count),
        "live_share": _round_share(live_count, active_count),
        "latest_pricing_updated_at": latest_raw,
        "latest_pricing_age_hours": latest_age_hours,
        "freshness": {
            "status": freshness_status,
            "threshold_hours": MARKET_DATA_FRESHNESS_THRESHOLD_HOURS,
        },
        "degraded_reasons": sorted(set(degraded_reasons)),
        "unavailable_dimensions": unavailable_dimensions,
        "truth_boundary": "Sanitized aggregate pricing-evidence quality from persisted rows; does not prove external provider uptime unless provider status is stored on sampled rows.",
    }
```

- [ ] **Step 3: Include pricing fields in `build_pipeline_truth()` select**

Change the opportunity select string to include:

```python
pricing_updated_at,manheim_source_status,manheim_updated_at
```

Keep all existing selected fields.

- [ ] **Step 4: Add `market_data_quality` to the returned object**

After `pricing_substrate` is assigned and `active_dos80` is computed, add:

```python
market_data_quality = _market_data_quality(opp_rows, pricing_substrate)
```

Then return:

```python
"pricing_substrate": pricing_substrate,
"market_data_quality": market_data_quality,
```

- [ ] **Step 5: Run GREEN focused tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit implementation**

```bash
git add webapp/routers/internal.py tests/test_internal_pipeline_truth.py
git commit -m "feat: report market data quality truth"
```

---

### Task 3: Live Inspection RED Tests

**Files:**
- Modify: `tests/test_supabase_live_inspection.py`

- [ ] **Step 1: Add pricing columns to the existing safe truth audit test fixture where needed**

In the test that calls `_safe_truth_audit`, include these opportunity columns:

```python
"pricing_updated_at",
"manheim_source_status",
"manheim_updated_at",
"retail_comp_count",
"retail_comp_confidence",
"mmr_confidence_proxy",
```

- [ ] **Step 2: Add RED live-inspection contract test**

```python
def test_safe_truth_audit_reports_market_data_quality(monkeypatch):
    columns = {
        "opportunities": {
            "created_at",
            "source_site",
            "dos_score",
            "score",
            "pricing_maturity",
            "pricing_source",
            "pricing_updated_at",
            "manheim_source_status",
            "manheim_updated_at",
            "retail_comp_count",
            "retail_comp_confidence",
            "mmr_confidence_proxy",
            "is_active",
            "vin",
            "listing_url",
            "raw_data",
        },
        "alert_log": {"created_at", "status"},
        "webhook_log": {"created_at", "processing_status"},
        "ingest_delivery_log": {"source_site", "status", "error_message", "created_at"},
        "post_close_outcome_requests": {"created_at", "source_site", "outcome_status"},
        "source_health_daily": {"observed_date", "source_name", "total_runs", "processed_runs", "failed_runs", "item_count", "saved_count", "skipped_count", "parse_event_count", "latest_started_at"},
        "parse_events": {"source_name", "event_type", "status", "reason", "created_at"},
    }
    rows = {
        "opportunities": [
            {
                "created_at": "2026-06-13T02:00:00Z",
                "source_site": "govdeals",
                "dos_score": 88,
                "score": 88,
                "pricing_maturity": "proxy",
                "pricing_source": "mmr_proxy",
                "pricing_updated_at": "2026-06-13T02:00:00+00:00",
                "manheim_source_status": "fallback",
                "manheim_updated_at": None,
                "retail_comp_count": 0,
                "retail_comp_confidence": None,
                "mmr_confidence_proxy": 82,
                "is_active": True,
                "vin": "1FTFW1E50PFA00000",
                "listing_url": "https://example.test/private",
                "raw_data": {"description": "private text"},
            }
        ],
        "alert_log": [],
        "webhook_log": [],
        "ingest_delivery_log": [],
        "post_close_outcome_requests": [],
        "source_health_daily": [],
        "parse_events": [],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(inspection, "_recent_rows", lambda _base, _key, table, _select, _order, _limit: rows[table])

    report = inspection._safe_truth_audit("https://example.supabase.co", "service-key")

    quality = report["market_data_quality"]
    assert quality["status"] == "degraded"
    assert quality["active_sample_size"] == 1
    assert quality["proxy_share"] == 1.0
    assert quality["high_score_proxy_share"] == 1.0
    assert quality["manheim_source_status_counts"] == {"fallback": 1}
    assert "high_score_proxy_pricing_present" in quality["degraded_reasons"]
    assert "private" not in str(quality).lower()
    assert "1FTFW" not in str(quality)
```

- [ ] **Step 3: Run RED live-inspection command**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q
```

Expected: failure with `KeyError: 'market_data_quality'`.

- [ ] **Step 4: Commit RED live-inspection tests**

```bash
git add tests/test_supabase_live_inspection.py
git commit -m "test: require market data quality live proof"
```

---

### Task 4: Live Inspection Implementation

**Files:**
- Modify: `scripts/supabase_live_inspection.py`
- Test: `tests/test_supabase_live_inspection.py`

- [ ] **Step 1: Add constants near existing module constants**

```python
MARKET_DATA_PROXY_SHARE_DEGRADED_THRESHOLD = 0.25
MARKET_DATA_FRESHNESS_THRESHOLD_HOURS = 24.0
MARKET_DATA_MIN_RETAIL_COMP_COUNT = 2
HOT_DEAL_ALERT_THRESHOLD = 80.0
```

If `HOT_DEAL_ALERT_THRESHOLD` already exists in the script, reuse it.

- [ ] **Step 2: Add helper functions near other summarizers**

Add these helpers with script-local names:

```python
def _market_data_round_share(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _market_data_parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _market_data_latest_datetime(rows: list[dict[str, Any]], keys: list[str]) -> tuple[str | None, datetime | None]:
    latest_raw: str | None = None
    latest_dt: datetime | None = None
    for row in rows:
        for key in keys:
            parsed = _market_data_parse_datetime(row.get(key))
            if parsed and (latest_dt is None or parsed > latest_dt):
                latest_dt = parsed
                latest_raw = str(row.get(key))
    return latest_raw, latest_dt
```

Then add `_summarize_market_data_quality()`:

```python
def _summarize_market_data_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    active_rows = [row for row in rows if row.get("is_active") is True]
    high_score_rows = [
        row for row in active_rows
        if (_coerce_float(row.get("dos_score")) or _coerce_float(row.get("score")) or 0.0) >= HOT_DEAL_ALERT_THRESHOLD
    ]

    unavailable_dimensions: list[str] = []
    if active_rows and all("pricing_maturity" not in row for row in active_rows):
        unavailable_dimensions.append("pricing_maturity")
    if active_rows and all("manheim_source_status" not in row for row in active_rows):
        unavailable_dimensions.append("manheim_source_status")
    if active_rows and all("pricing_updated_at" not in row and "manheim_updated_at" not in row for row in active_rows):
        unavailable_dimensions.append("pricing_freshness")

    pricing_counts = dict(Counter(str(row.get("pricing_maturity")) for row in active_rows if row.get("pricing_maturity") is not None).most_common(20))
    high_score_pricing_counts = dict(Counter(str(row.get("pricing_maturity")) for row in high_score_rows if row.get("pricing_maturity") is not None).most_common(20))
    manheim_counts = dict(Counter(str(row.get("manheim_source_status")) for row in active_rows if row.get("manheim_source_status") is not None).most_common(20))

    active_count = len(active_rows)
    high_score_count = len(high_score_rows)
    proxy_count = sum(1 for row in active_rows if str(row.get("pricing_maturity") or "").strip().lower() == "proxy")
    high_score_proxy_count = sum(1 for row in high_score_rows if str(row.get("pricing_maturity") or "").strip().lower() == "proxy")
    fallback_count = sum(1 for row in active_rows if str(row.get("manheim_source_status") or "").strip().lower() == "fallback")
    live_count = sum(1 for row in active_rows if str(row.get("manheim_source_status") or "").strip().lower() == "live")

    latest_raw, latest_dt = _market_data_latest_datetime(active_rows, ["pricing_updated_at", "manheim_updated_at"])
    latest_age_hours = round((now - latest_dt).total_seconds() / 3600.0, 2) if latest_dt else None
    freshness_status = "fresh" if latest_age_hours is not None and latest_age_hours <= MARKET_DATA_FRESHNESS_THRESHOLD_HOURS else "stale"

    degraded_reasons: list[str] = []
    if not active_rows:
        degraded_reasons.append("no_active_pricing_sample")
    if unavailable_dimensions:
        degraded_reasons.append("pricing_fields_missing")
    if _market_data_round_share(proxy_count, active_count) > MARKET_DATA_PROXY_SHARE_DEGRADED_THRESHOLD:
        degraded_reasons.append("proxy_pricing_share_above_threshold")
    if high_score_proxy_count > 0:
        degraded_reasons.append("high_score_proxy_pricing_present")
    if freshness_status == "stale":
        degraded_reasons.append("pricing_evidence_stale")
    non_live_rows = [row for row in active_rows if str(row.get("pricing_maturity") or "").lower() != "live_market"]
    if non_live_rows and all((_coerce_int(row.get("retail_comp_count")) or 0) < MARKET_DATA_MIN_RETAIL_COMP_COUNT for row in non_live_rows):
        degraded_reasons.append("retail_comps_sparse")
    if active_rows and live_count == 0 and "manheim_source_status" not in unavailable_dimensions:
        degraded_reasons.append("manheim_live_share_below_threshold")

    if unavailable_dimensions:
        status = "unknown"
    elif not active_rows:
        status = "unavailable"
    elif degraded_reasons:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "sample_size": len(rows),
        "active_sample_size": active_count,
        "high_score_sample_size": high_score_count,
        "pricing_maturity_counts": pricing_counts,
        "high_score_pricing_maturity_counts": high_score_pricing_counts,
        "manheim_source_status_counts": manheim_counts,
        "fallback_share": _market_data_round_share(fallback_count, active_count),
        "proxy_share": _market_data_round_share(proxy_count, active_count),
        "high_score_proxy_share": _market_data_round_share(high_score_proxy_count, high_score_count),
        "live_share": _market_data_round_share(live_count, active_count),
        "latest_pricing_updated_at": latest_raw,
        "latest_pricing_age_hours": latest_age_hours,
        "freshness": {
            "status": freshness_status,
            "threshold_hours": MARKET_DATA_FRESHNESS_THRESHOLD_HOURS,
        },
        "degraded_reasons": sorted(set(degraded_reasons)),
        "unavailable_dimensions": unavailable_dimensions,
        "truth_boundary": "Sanitized aggregate pricing-evidence quality from persisted rows; does not print VINs, listing URLs, titles, or raw payloads.",
    }
```

The implementation must not copy row payloads into the return object.

- [ ] **Step 3: Expand `_safe_truth_audit()` opportunity column allowlist**

Add to `desired_opportunity_columns`:

```python
"pricing_source",
"pricing_updated_at",
"manheim_source_status",
"manheim_updated_at",
"retail_comp_count",
"retail_comp_confidence",
"mmr_confidence_proxy",
```

- [ ] **Step 4: Return `market_data_quality` from `_safe_truth_audit()`**

Add:

```python
"market_data_quality": _summarize_market_data_quality(recent_opportunities),
```

near `recent_opportunities`.

- [ ] **Step 5: Run GREEN live-inspection tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit implementation**

```bash
git add scripts/supabase_live_inspection.py tests/test_supabase_live_inspection.py
git commit -m "feat: prove market data quality in live inspection"
```

---

### Task 5: Broader Verification And PR

**Files:**
- No new implementation files unless Task 2 or 4 required helper extraction.

- [ ] **Step 1: Run focused combined tests**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run adjacent scoring and alert tests**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_ingest_scoring.py tests/test_alert_send_gate.py tests/test_alert_thresholds.py tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full local suite**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests -q
```

Expected: all tests pass.

- [ ] **Step 4: Inspect diff for accidental sensitive output**

```bash
git diff --check
rg -n "vin|listing_url|raw_data|description|token|secret" webapp/routers/internal.py scripts/supabase_live_inspection.py tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py
```

Expected: no new sensitive fields are emitted from `market_data_quality`; existing tests may include sensitive fixture strings only to prove sanitization.

- [ ] **Step 5: Push branch and open PR**

```bash
git push -u origin fix/market-data-provenance-hardening
gh pr create --title "Report market data quality truth" --body "Adds a sanitized market_data_quality contract to internal pipeline truth and Supabase live inspection so proxy/fallback-heavy pricing states are explicit instead of hidden behind green ingest."
```

- [ ] **Step 6: Wait for PR checks and review**

Required checks:

- DealerScope CI
- Cursor Code Review
- Vercel Deploy Gate
- Cursor Bugbot, if present
- Any repository-required business-rule checks

Address every current actionable review finding with RED/GREEN tests before merge.

---

### Task 6: Merge, Deploy, And Live Proof

**Files:**
- No direct file edits unless review requires them.

- [ ] **Step 1: Merge PR only after checks and review are clean**

Use GitHub merge after all required checks pass.

- [ ] **Step 2: Verify current main checks**

```bash
gh run list --branch main --limit 12 --json databaseId,workflowName,status,conclusion,headSha,url
```

Expected: latest main checks on the merge commit are `completed` with `success`.

- [ ] **Step 3: Verify Railway health**

```bash
curl -fsS https://dealscan-insight-production.up.railway.app/healthz
```

Expected: JSON with `"status":"ok"`.

- [ ] **Step 4: Trigger fresh Supabase Live Inspection**

```bash
gh workflow run "DealerScope Supabase Live Inspection" --ref main
```

Then wait for completion:

```bash
gh run list --workflow "DealerScope Supabase Live Inspection" --branch main --limit 3 --json databaseId,status,conclusion,headSha,url
```

Expected: latest run on the merge commit succeeds.

- [ ] **Step 5: Inspect live-inspection log**

```bash
gh run view <RUN_ID> --log | rg -n "market_data_quality|proxy_share|fallback_share|degraded_reasons|latest_pricing_age_hours|truth_boundary"
```

Expected: log includes the new `market_data_quality` contract with status, shares, degraded reasons, freshness age, unavailable dimensions, and truth boundary.

- [ ] **Step 6: Final classification**

Only send `live-confirmed` if all of the following are true:

- PR merged to `main`.
- Main checks green on merge commit.
- Railway health OK after deploy.
- Fresh Supabase Live Inspection succeeds on merge commit.
- Live log proves `market_data_quality` is printed with the required keys.

If any condition is missing, classify as `live-improved but pending` or `locally validated only` with the exact missing gate.
