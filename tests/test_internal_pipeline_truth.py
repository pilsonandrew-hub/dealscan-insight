import inspect

from fastapi import HTTPException
from types import SimpleNamespace

from webapp.routers import internal


def test_internal_secret_rejects_missing(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-secret")
    try:
        internal.verify_internal_secret(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing internal secret should reject")


def test_internal_secret_accepts(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-secret")
    internal.verify_internal_secret("internal-secret")


def test_internal_secret_uses_constant_time_comparison():
    source = inspect.getsource(internal.verify_internal_secret)

    assert "compare_digest" in source
    assert ".strip() != expected" not in source


def test_seller_recovery_audit_returns_sanitized_evidence_backed_candidates(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "source_health_daily": [
            {
                "source_name": "govdeals",
                "observed_date": "2026-06-13",
                "total_runs": 2,
                "processed_runs": 1,
                "failed_runs": 1,
                "item_count": 20,
                "saved_count": 4,
                "skipped_count": 12,
                "parse_event_count": 16,
                "latest_started_at": "2026-06-13T01:00:00Z",
            }
        ],
        "ingest_delivery_log": [
            {
                "source_site": "govdeals",
                "status": "skipped_margin",
                "error_message": "margin_below_floor",
                "listing_url": "https://example.test/private",
                "vin": "1FTFW1E50PFA00000",
                "created_at": "2026-06-13T01:00:01Z",
            },
            {
                "source_site": "govdeals",
                "status": "skipped_gate",
                "error_message": "age_or_mileage_exceeded",
                "created_at": "2026-06-13T01:00:02Z",
            },
        ],
        "parse_events": [
            {
                "source_name": "govdeals",
                "event_type": "db_save",
                "status": "skipped_margin",
                "reason": "margin_below_floor",
                "metadata": {"listing_url": "https://example.test/private", "vin": "1FTFW1E50PFA00000"},
                "created_at": "2026-06-13T01:00:01Z",
            },
            {
                "source_name": "govdeals",
                "event_type": "db_save",
                "status": "saved",
                "created_at": "2026-06-13T01:00:02Z",
            },
        ],
        "opportunities": [
            {
                "id": "recoverable-1",
                "is_active": True,
                "source_site": "govdeals",
                "year": 2023,
                "make": "Ford",
                "model": "F-150",
                "dos_score": 82,
                "gross_margin": 6200,
                "bid_headroom": 2400,
                "pricing_maturity": "proxy",
                "vin": None,
                "mileage": None,
                "condition_grade": "Unknown",
                "auction_end_date": None,
                "risk_flags": ["missing_photos"],
                "photo_count": 0,
                "bidder_count": None,
                "listing_url": "https://example.test/private",
                "raw_data": {"description": "private text", "vin": "1FTFW1E50PFA00000"},
            },
            {
                "id": "not-recoverable",
                "is_active": True,
                "source_site": "govdeals",
                "year": 2025,
                "make": "Honda",
                "model": "Accord",
                "dos_score": 90,
                "gross_margin": 5000,
                "bid_headroom": 2000,
                "pricing_maturity": "market_comp",
                "vin": "1HGCM82633A004352",
                "mileage": 12000,
                "condition_grade": "Good",
                "auction_end_date": "2026-06-20T00:00:00Z",
                "risk_flags": [],
                "photo_count": 5,
                "bidder_count": 9,
            },
        ],
        "sonar_listings": [
            {
                "source_site": "hibid",
                "source": "hibid",
                "bidder_count": 12,
                "created_at": "2026-06-13T14:00:00Z",
            }
        ],
    }))

    result = internal.build_seller_recovery_audit()

    assert result["status"] == "ok"
    assert result["scope"] == "internal_seller_recovery_audit"
    assert result["summary"]["source_count"] == 1
    assert result["summary"]["candidate_count"] == 1
    assert result["source_health"][0]["source_name"] == "govdeals"
    assert result["source_health"][0]["failed_runs"] == 1
    assert result["listing_quality"]["missing_vin_count"] == 1
    assert result["listing_quality"]["missing_mileage_count"] == 1
    assert result["listing_quality"]["missing_auction_end_count"] == 1
    assert result["listing_quality"]["proxy_pricing_count"] == 1
    assert result["listing_quality"]["photo_count_known_count"] == 2
    assert result["listing_quality"]["zero_photo_count"] == 1
    assert result["listing_quality"]["low_photo_count_count"] == 1
    assert result["listing_quality"]["bidder_count_known_count"] == 1
    assert result["listing_quality"]["zero_bidder_count"] == 0
    assert result["listing_quality"]["thin_bidder_count"] == 0
    assert result["listing_quality"]["average_bidder_count"] == 9.0
    assert result["source_listing_quality"]["bidder_count_known_count"] == 1
    assert result["source_listing_quality"]["average_bidder_count"] == 12.0
    assert result["delivery_status_counts"] == {"skipped_margin": 1, "skipped_gate": 1}
    assert result["parse_event_status_counts"] == {"skipped_margin": 1, "saved": 1}
    assert result["parse_event_type_counts"] == {"db_save": 2}
    assert result["unsupported_dimensions"]["bidder_depth"]["status"] == "available"
    assert result["unsupported_dimensions"]["photo_count"]["status"] == "available"
    assert "bidder_depth" not in result["summary"]["unavailable_dimensions"]
    assert "photo_count" not in result["summary"]["unavailable_dimensions"]
    candidate = result["value_leak_candidates"][0]
    assert candidate["id"] == "recoverable-1"
    assert candidate["source_site"] == "govdeals"
    assert candidate["year"] == 2023
    assert candidate["make"] == "Ford"
    assert candidate["model"] == "F-150"
    assert candidate["dos_score"] == 82.0
    assert candidate["gross_margin"] == 6200.0
    assert candidate["bid_headroom"] == 2400.0
    assert candidate["pricing_maturity"] == "proxy"
    assert candidate["recovery_reasons"] == [
        "missing_vin",
        "missing_mileage",
        "missing_auction_end",
        "condition_unverified",
        "proxy_pricing",
        "missing_photos_flag",
        "zero_photo_count",
    ]
    assert 0 <= candidate["recovery_score"] <= 100
    assert candidate["recovery_tier"] in {"high", "medium", "low"}
    assert set(candidate["score_components"]) == {"value_gap", "listing_quality", "evidence_strength", "source_health"}
    assert round(sum(candidate["score_components"].values()), 2) == candidate["recovery_score"]
    assert candidate["evidence"]["photo_count_present"] is True
    assert candidate["evidence"]["bidder_depth_surface"] is None
    assert candidate["evidence"]["source_mirror_bidder_count_present"] is False
    assert candidate["truth_boundary"].startswith("Internal prioritization")
    serialized = str(result)
    assert "1FTFW1E50PFA00000" not in serialized
    assert "https://example.test/private" not in serialized
    assert "private text" not in serialized


def test_seller_recovery_audit_ranks_candidates_with_bounded_scores(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "source_health_daily": [
            {"source_name": "govdeals", "total_runs": 3, "processed_runs": 2, "failed_runs": 1, "saved_count": 4, "skipped_count": 8, "parse_event_count": 12},
            {"source_name": "hibid", "total_runs": 1, "processed_runs": 1, "failed_runs": 0, "saved_count": 1, "skipped_count": 0, "parse_event_count": 1},
        ],
        "ingest_delivery_log": [
            {"status": "skipped_margin", "error_message": "margin_below_floor", "created_at": "2026-06-13T01:00:00Z"},
            {"status": "skipped_gate", "error_message": "condition_unverified", "created_at": "2026-06-13T01:01:00Z"},
        ],
        "parse_events": [
            {"source_name": "govdeals", "event_type": "db_save", "status": "skipped_margin", "reason": "margin_below_floor"},
            {"source_name": "govdeals", "event_type": "db_save", "status": "saved", "reason": None},
        ],
        "opportunities": [
            {
                "id": "candidate-high", "is_active": True, "source_site": "govdeals", "year": 2023,
                "make": "Ford", "model": "F-150", "dos_score": 86, "gross_margin": 21000,
                "bid_headroom": 17000, "pricing_maturity": "market_comp", "vin": None,
                "mileage": None, "condition_grade": "Unknown", "auction_end_date": None,
                "risk_flags": ["missing_photos"], "photo_count": 0, "bidder_count": None,
                "listing_url": "https://private.example/high", "raw_data": {"vin": "SECRETVINHIGH"},
            },
            {
                "id": "candidate-medium", "is_active": True, "source_site": "hibid", "year": 2024,
                "make": "Toyota", "model": "Tacoma", "dos_score": 81, "gross_margin": 4200,
                "bid_headroom": 900, "pricing_maturity": "proxy", "vin": "5TSECRET",
                "mileage": 19000, "condition_grade": "Good", "auction_end_date": "2026-06-20T00:00:00Z",
                "risk_flags": [], "photo_count": 2, "bidder_count": None,
            },
        ],
        "sonar_listings": [{"source_site": "hibid", "source": "hibid", "bidder_count": 12}],
    }))

    result = internal.build_seller_recovery_audit()
    candidates = result["value_leak_candidates"]

    assert [candidate["id"] for candidate in candidates] == ["candidate-high", "candidate-medium"]
    assert candidates[0]["recovery_score"] > candidates[1]["recovery_score"]
    assert candidates[0]["recovery_tier"] == "high"
    assert candidates[1]["recovery_tier"] in {"medium", "low"}
    assert candidates[0]["source_site"] == "govdeals"
    assert candidates[0]["evidence"]["bidder_depth_surface"] is None
    assert candidates[0]["evidence"]["source_mirror_bidder_count_present"] is False
    assert candidates[1]["source_site"] == "hibid"
    assert candidates[1]["evidence"]["bidder_depth_surface"] == "source_mirror"
    assert candidates[1]["evidence"]["source_mirror_bidder_count_present"] is True
    for candidate in candidates:
        assert 0 <= candidate["recovery_score"] <= 100
        assert set(candidate["score_components"]) == {"value_gap", "listing_quality", "evidence_strength", "source_health"}
        assert round(sum(candidate["score_components"].values()), 2) == candidate["recovery_score"]
        assert "evidence" in candidate
        assert "truth_boundary" in candidate
    serialized = str(result)
    assert "SECRETVINHIGH" not in serialized
    assert "https://private.example/high" not in serialized


def test_seller_recovery_audit_returns_rollups_and_truth_boundaries(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "source_health_daily": [
            {"source_name": "allsurplus", "total_runs": 2, "processed_runs": 1, "failed_runs": 1, "saved_count": 3, "skipped_count": 9, "parse_event_count": 11},
            {"source_name": "allsurplus", "total_runs": 1, "processed_runs": 0, "failed_runs": 1, "saved_count": 0, "skipped_count": 4, "parse_event_count": 2},
        ],
        "ingest_delivery_log": [
            {"status": "skipped_margin", "error_message": "margin_below_floor"},
            {"status": "skipped_margin", "error_message": "margin_below_floor"},
        ],
        "parse_events": [{"source_name": "allsurplus", "event_type": "db_save", "status": "skipped_margin", "reason": "margin_below_floor"}],
        "opportunities": [
            {"id": "c1", "is_active": True, "source_site": "allsurplus", "gross_margin": 9000, "bid_headroom": 7000, "dos_score": 84, "pricing_maturity": "market_comp", "vin": None, "mileage": None, "condition_grade": "Unknown", "risk_flags": ["missing_photos"], "photo_count": 0},
            {"id": "c2", "is_active": True, "source_site": "allsurplus", "gross_margin": 6000, "bid_headroom": 3000, "dos_score": 82, "pricing_maturity": "market_comp", "vin": "known", "mileage": 24000, "condition_grade": "Good", "risk_flags": [], "photo_count": 1},
        ],
        "sonar_listings": [],
    }))

    result = internal.build_seller_recovery_audit()

    assert result["recovery_rollups"]["reason_counts"]["missing_photos_flag"] == 1
    assert result["recovery_rollups"]["reason_counts"]["low_photo_count"] == 1
    assert result["recovery_rollups"]["source_counts"] == {"allsurplus": 2}
    assert result["recovery_rollups"]["top_sources_by_score"][0]["source_site"] == "allsurplus"
    assert result["source_health_summary"]["observed_source_count"] == 1
    assert result["source_health_summary"]["sources_with_failed_runs"] == 1
    assert result["source_health_summary"]["total_failed_runs"] == 2
    assert result["truth_boundaries"]["candidate_ranking"].startswith("Internal deterministic prioritization")
    assert "seller intent" in result["truth_boundaries"]["source_health"]


def test_seller_recovery_audit_degrades_when_opportunities_unreadable(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "source_health_daily": [],
        "ingest_delivery_log": [],
        "parse_events": [],
        "opportunities": None,
    }))

    result = internal.build_seller_recovery_audit()

    assert result["status"] == "degraded"
    assert result["sections"]["opportunities"]["status"] == "unavailable"
    assert result["summary"]["candidate_count"] == 0


def test_seller_recovery_audit_does_not_select_non_schema_delivery_or_opportunity_fields(monkeypatch):
    class SchemaStrictQuery(_Query):
        def __init__(self, table, rows):
            super().__init__(rows)
            self.table = table

        def select(self, columns, **_kwargs):
            selected = {column.strip() for column in str(columns).split(",") if column.strip()}
            if self.table == "ingest_delivery_log":
                assert "source_site" not in selected
                assert "source" not in selected
            if self.table == "opportunities":
                assert columns == "*"
            return self

    class SchemaStrictSupabase:
        def table(self, name):
            rows = {
                "source_health_daily": [],
                "ingest_delivery_log": [{"status": "skipped_margin", "error_message": "margin_below_floor"}],
                "parse_events": [],
                "opportunities": [
                    {
                        "id": "recoverable-1",
                        "is_active": True,
                        "source_site": "govdeals",
                        "year": 2023,
                        "make": "Ford",
                        "model": "F-150",
                        "dos_score": 82,
                        "gross_margin": 6200,
                        "bid_headroom": 2400,
                        "pricing_maturity": "proxy",
                        "vin": None,
                        "mileage": None,
                        "condition_grade": "Unknown",
                    }
                ],
            }[name]
            return SchemaStrictQuery(name, rows)

    monkeypatch.setattr(internal, "supabase_client", SchemaStrictSupabase())

    result = internal.build_seller_recovery_audit()

    assert result["status"] == "ok"
    assert result["summary"]["candidate_count"] == 1


def test_seller_recovery_audit_route_requires_internal_secret(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-secret")
    try:
        internal.seller_recovery_audit(None)
    except HTTPException as exc:
        assert exc.status_code == 401
    else:
        raise AssertionError("missing internal secret should reject seller recovery audit")


def test_seller_recovery_audit_route_returns_builder_result(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_SECRET", "internal-secret")
    monkeypatch.setattr(internal, "build_seller_recovery_audit", lambda: {"status": "ok"})

    assert internal.seller_recovery_audit("internal-secret") == {"status": "ok"}


class _Query:
    def __init__(self, rows, count=None):
        self.rows = rows
        self.count = count if count is not None else len(rows)
        self.filters = []
        self._limit = None
        self._order = None

    def select(self, *_args, **_kwargs): return self
    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self
    def gt(self, column, value):
        self.filters.append(("gt", column, value))
        return self
    def gte(self, column, value):
        self.filters.append(("gte", column, value))
        return self
    def not_(self, column, operator, value):
        self.filters.append(("not_", column, operator, value))
        return self
    def limit(self, value):
        self._limit = value
        return self
    def order(self, column, desc=False, **_kwargs):
        self._order = (column, desc)
        return self
    def execute(self):
        rows = list(self.rows)
        for filter_spec in self.filters:
            method, column, *values = filter_spec
            if method == "eq":
                rows = [row for row in rows if row.get(column) == values[0]]
            elif method == "gt":
                rows = [row for row in rows if row.get(column) is not None and row.get(column) > values[0]]
            elif method == "gte":
                rows = [row for row in rows if row.get(column) is not None and str(row.get(column)) >= str(values[0])]
            elif method == "not_":
                operator, value = values
                if operator == "is" and value == "null":
                    rows = [row for row in rows if row.get(column) is not None]
        if self._order:
            column, desc = self._order
            rows = sorted(rows, key=lambda row: row.get(column) or "", reverse=desc)
        count = len(rows)
        if self._limit is not None:
            rows = rows[: self._limit]
        return SimpleNamespace(data=rows, count=count)


class _Supabase:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}

    def table(self, name):
        if name in self.overrides:
            rows = self.overrides[name]
            if rows is None:
                raise RuntimeError(f"{name} missing")
            return _Query(rows)
        rows = {
            "opportunities": [
                {
                    "id": "1",
                    "is_active": True,
                    "dos_score": 90,
                    "mileage": None,
                    "year": 2018,
                    "title": "2018 Ford Transit",
                    "pricing_maturity": "proxy",
                    "vin": None,
                    "condition_grade": "Poor",
                    "source_site": "govdeals",
                    "investment_grade": "Rejected",
                    "roi_per_day": 300,
                    "bid_headroom": 1000,
                    "current_bid_trust_score": 0.9,
                    "mmr_confidence_proxy": 90,
                    "pricing_source": "proxy",
                },
                {
                    "id": "2",
                    "is_active": True,
                    "dos_score": 91,
                    "mileage": 25000,
                    "year": 2025,
                    "title": "2025 Honda Accord",
                    "pricing_maturity": "market_comp",
                    "vin": "1HGCM82633A004352",
                    "condition_grade": "Good",
                    "source_site": "govdeals",
                    "investment_grade": "Platinum",
                    "roi_per_day": 300,
                    "bid_headroom": 1000,
                    "current_bid_trust_score": 0.9,
                    "mmr_confidence_proxy": 90,
                    "pricing_source": "market_comp",
                    "retail_comp_count": 5,
                    "retail_comp_confidence": 0.9,
                    "projected_total_cost": 10000,
                    "max_bid": 12000,
                    "expected_close_bid": 10000,
                    "raw_data": {
                        "detail_text": "Starts, runs and drives. Minor scratches noted.",
                    },
                },
                {
                    "id": "3",
                    "is_active": True,
                    "dos_score": 62,
                    "mileage": 41000,
                    "year": 2023,
                    "title": "2023 Ford Explorer",
                    "pricing_maturity": "market_comp",
                    "vin": "1FM5K8GC1PGA12345",
                    "condition_grade": "Good",
                    "source_site": "govdeals",
                    "investment_grade": "Bronze",
                    "roi_per_day": 20,
                    "bid_headroom": 500,
                    "current_bid_trust_score": 0.9,
                    "mmr_confidence_proxy": 90,
                    "pricing_source": "market_comp",
                    "retail_comp_count": 3,
                    "retail_comp_confidence": 0.81,
                    "projected_total_cost": 20000,
                    "max_bid": 20500,
                    "expected_close_bid": 20000,
                    "raw_data": {
                        "detail_text": "Starts, runs and drives. Normal wear.",
                    },
                },
            ],
            "webhook_log": [{"id": "w1", "processing_status": "processed", "source": "govdeals"}],
            "alert_log": [{"id": "a1", "sent_at": "2026-05-20T02:11:32Z", "delivery_state": "sent"}],
            "ingest_delivery_log": [{"id": "d1", "created_at": "2026-05-20T02:11:32Z", "channel": "telegram_alert", "status": "sent"}],
            "dealer_sales": [
                {"id": "sale-1", "sale_date": None, "make": "Ford", "model": "F150 HAS"},
                {"id": "sale-2", "sale_date": None, "make": "Ford", "model": "F-550"},
            ],
            "market_prices": None,
        }[name]
        if rows is None:
            raise RuntimeError(f"{name} missing")
        return _Query(rows)


def test_pipeline_truth_returns_aggregate_only(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase())
    result = internal.build_pipeline_truth()
    assert result["status"] == "ok"
    assert result["opportunities"]["active_sample"] == 3
    assert result["opportunities"]["active_dos_score_buckets_sample"] == {
        "80_plus": 2,
        "50_to_64": 1,
    }
    assert result["opportunities"]["active_dos_score_min_sample"] == 62.0
    assert result["opportunities"]["active_dos_score_max_sample"] == 91.0
    assert result["opportunities"]["active_dos_score_avg_sample"] == 81.0
    assert result["opportunities"]["active_pricing_maturity_counts_sample"] == {
        "market_comp": 2,
        "proxy": 1,
    }
    assert result["opportunities"]["active_source_counts_sample"] == {"govdeals": 3}
    assert len(result["opportunities"]["active_gate_breakdown_sample"]) == 3
    assert result["opportunities"]["active_dos80_sample"] == 2
    assert result["opportunities"]["active_dos80_missing_mileage_sample"] == 1
    breakdown = result["opportunities"]["active_dos80_gate_breakdown"]
    assert len(breakdown) == 2
    blocked = next(item for item in breakdown if item["id"] == "1")
    assert blocked["eligible"] is False
    assert "mileage_missing" in blocked["blocking_reasons"]
    assert "pricing_maturity=proxy" in blocked["blocking_reasons"]
    assert "grade=Rejected" in blocked["blocking_reasons"]
    allowed = next(item for item in breakdown if item["id"] == "2")
    assert allowed["eligible"] is True
    assert allowed["blocking_reasons"] == []
    assert result["opportunities"]["active_dos80_gate_blocker_counts_sample"] == {
        "mileage_missing": 1,
        "pricing_maturity=proxy": 1,
        "insufficient_pricing": 1,
        "vin_unverified": 1,
        "grade=Rejected": 1,
        "condition_unverified": 1,
    }
    assert result["opportunities"]["active_dos80_alert_eligible_sample"] == 1
    assert result["opportunities"]["active_dos80_condition_counts_sample"] == {
        "Poor": 1,
        "Good": 1,
    }
    assert result["opportunities"]["active_dos80_condition_blocker_basis_counts_sample"] == {
        "age_mileage_heuristic": 1,
    }
    assert result["opportunities"]["active_dos80_condition_blocker_basis_by_source_sample"] == {
        "govdeals": {
            "age_mileage_heuristic": 1,
        },
    }
    assert result["opportunities"]["active_dos80_condition_blocker_basis_samples"][0] == {
        "id": "1",
        "source_site": "govdeals",
        "title": "2018 Ford Transit",
        "year": 2018,
        "mileage": None,
        "condition_grade": "Poor",
        "condition_blocker_basis": "age_mileage_heuristic",
        "condition_signals": [],
        "source_text_excerpt": "2018 Ford Transit",
    }
    assert result["opportunities"]["active_dos80_pricing_maturity_counts_sample"] == {
        "proxy": 1,
        "market_comp": 1,
    }
    assert "latest" in result["webhooks"]
    assert result["pricing_substrate"] == {
        "market_prices_table": "missing",
        "market_prices_rows": 0,
        "market_prices_usable_rows": 0,
        "market_prices_unusable_reason_counts": {},
        "market_prices_latest_expires_at": None,
        "dealer_sales_table": "present",
        "dealer_sales_rows": 2,
        "dealer_sales_usable_rows": 0,
        "latest_dealer_sale_date": None,
        "ready_for_market_comp_pricing": False,
    }


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


def test_pipeline_truth_keeps_market_data_quality_healthy_when_market_prices_are_ready(monkeypatch):
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

    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is True
    quality = result["market_data_quality"]
    assert quality["status"] == "healthy"
    assert "dealer_sales_sparse" not in quality["degraded_reasons"]
    assert "market_prices_unusable" not in quality["degraded_reasons"]


def test_pipeline_truth_uses_same_score_resolution_for_buckets_and_dos80(monkeypatch):
    monkeypatch.setattr(
        internal,
        "supabase_client",
        _Supabase(
            {
                "opportunities": [
                    {
                        "id": "zero-dos-high-score",
                        "is_active": True,
                        "dos_score": 0,
                        "score": 82,
                        "mileage": 25000,
                        "year": 2025,
                        "title": "2025 Ford Explorer",
                        "pricing_maturity": "market_comp",
                        "vin": "1FMUK8DH5SGA77978",
                        "condition_grade": "Good",
                        "source_site": "govdeals",
                        "investment_grade": "Silver",
                    }
                ],
                "webhook_log": [],
                "alert_log": [],
                "ingest_delivery_log": [],
                "dealer_sales": [],
                "market_prices": [],
            }
        ),
    )

    result = internal.build_pipeline_truth()

    assert result["opportunities"]["active_dos_score_buckets_sample"] == {"under_50": 1}
    assert result["opportunities"]["active_dos80_sample"] == 0


def test_opportunity_condition_proof_uses_detail_text_for_exact_row(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "durango-row",
                "is_active": True,
                "dos_score": 91,
                "mileage": 13983,
                "year": 2020,
                "title": "2020 Dodge Durango SRT",
                "description": "2020 Dodge Durango SRT",
                "pricing_maturity": "market_comp",
                "vin": "1C4SDJGJ0LC123456",
                "condition_grade": "Poor",
                "source_site": "govdeals",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "2020 Dodge Durango SRT",
                    "detail_text": "Starts and runs. Exterior has minor scratches. Interior is clean.",
                    "source_run_id": "run-123",
                    "run_id": "run-123",
                    "actor_run_id": "run-123",
                    "listing_url": "https://www.govdeals.com/asset/197/5804?utm=test",
                    "listing_id": "govdeals:197/5804",
                    "vin": "1C4SDJGJ0LC123456",
                },
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_opportunity_condition_proof("durango-row")

    assert result["status"] == "ok"
    assert result["selector"] == {"id": "durango-row"}
    assert result["opportunity"]["id"] == "durango-row"
    assert result["opportunity"]["condition_blocker_basis"] == "age_mileage_heuristic"
    assert result["opportunity"]["condition_signals"] == []
    assert result["opportunity"]["source_text_excerpt"].startswith("2020 Dodge Durango SRT Starts and runs")
    assert result["opportunity"]["condition_evidence_fields"] == {
        "description": {"present": True, "length": len("2020 Dodge Durango SRT"), "matches_title": True},
        "details": {"present": False, "length": 0, "matches_title": False},
        "condition_notes": {"present": False, "length": 0, "matches_title": False},
        "detail_text": {"present": True, "length": len("Starts and runs. Exterior has minor scratches. Interior is clean."), "matches_title": False},
        "assetLongDesc": {"present": False, "length": 0, "matches_title": False},
    }
    assert result["opportunity"]["raw_data_keys_present"] == [
        "actor_run_id",
        "description",
        "detail_text",
        "listing_id",
        "listing_url",
        "run_id",
        "source_run_id",
        "vin",
    ]
    assert result["opportunity"]["source_identity"] == {
        "listing_id": "govdeals:197/5804",
        "listing_url": "https://www.govdeals.com/asset/197/5804",
        "source_run_id": "run-123",
        "run_id": "run-123",
        "actor_run_id": "run-123",
        "apify_run_id": None,
        "vin_present": True,
        "vin_suffix": "123456",
    }
    assert result["opportunity"]["condition_backfill_assessment"] == {
        "stored_source_condition_evidence": True,
        "status": "source_condition_evidence_present",
        "reason": "stored row already has non-title condition evidence",
    }


def test_opportunity_condition_proof_blocks_backfill_when_stored_evidence_missing(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "durango-row",
                "is_active": True,
                "dos_score": 91,
                "mileage": 13983,
                "year": 2020,
                "title": "2020 Dodge Durango SRT",
                "condition_grade": "Poor",
                "source_site": "govdeals",
                "raw_data": {
                    "description": "2020 Dodge Durango SRT",
                    "listing_url": "https://www.govdeals.com/asset/197/5804?utm=test",
                    "source_run_id": "old-run",
                },
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_opportunity_condition_proof("durango-row")

    assert result["opportunity"]["source_identity"]["listing_url"] == "https://www.govdeals.com/asset/197/5804"
    assert result["opportunity"]["condition_evidence_fields"]["description"] == {
        "present": True,
        "length": len("2020 Dodge Durango SRT"),
        "matches_title": True,
    }
    assert result["opportunity"]["condition_evidence_fields"]["detail_text"]["present"] is False
    assert result["opportunity"]["condition_backfill_assessment"] == {
        "stored_source_condition_evidence": False,
        "status": "blocked_missing_source_condition_evidence",
        "reason": "stored row has no non-title condition evidence to justify backfill",
    }


def test_pipeline_truth_reports_condition_storage_gap_samples(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "stored-gap",
                "is_active": True,
                "dos_score": 91,
                "mileage": 13983,
                "year": 2020,
                "title": "2020 Dodge Durango SRT",
                "pricing_maturity": "market_comp",
                "vin": "1C4SDJGJ6LC324462",
                "condition_grade": "Poor",
                "source_site": "govdeals",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "2020 Dodge Durango SRT",
                    "listing_url": "https://www.govdeals.com/asset/197/5804?utm=test",
                    "actor_run_id": "actor-run-1",
                    "source_run_id": "source-run-1",
                    "vin": "1C4SDJGJ6LC324462",
                },
            },
            {
                "id": "stored-evidence",
                "is_active": True,
                "dos_score": 90,
                "mileage": 12000,
                "year": 2021,
                "title": "2021 Dodge Durango",
                "pricing_maturity": "market_comp",
                "vin": "1C4RDJFG3MC696184",
                "condition_grade": "Poor",
                "source_site": "govdeals",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "2021 Dodge Durango",
                    "detail_text": "Starts and runs. Exterior has minor scratches.",
                    "listing_url": "https://www.govdeals.com/asset/202/8585",
                },
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()

    opportunities = result["opportunities"]
    assert opportunities["active_dos80_condition_storage_gap_count_sample"] == 1
    assert opportunities["active_dos80_condition_storage_gap_by_source_sample"] == {"govdeals": 1}
    assert opportunities["active_dos80_condition_storage_gap_samples"][0]["id"] == "stored-gap"
    assert opportunities["active_dos80_condition_storage_gap_samples"][0]["source_identity"] == {
        "listing_id": None,
        "listing_url": "https://www.govdeals.com/asset/197/5804",
        "source_run_id": "source-run-1",
        "run_id": None,
        "actor_run_id": "actor-run-1",
        "apify_run_id": None,
        "vin_present": True,
        "vin_suffix": "324462",
    }
    assert opportunities["active_dos80_condition_storage_gap_samples"][0]["condition_backfill_assessment"]["status"] == "blocked_missing_source_condition_evidence"


def test_pipeline_truth_blocks_active_dos80_good_grade_without_source_condition_evidence(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "missing-condition-proof",
                "is_active": True,
                "dos_score": 93,
                "mileage": 12000,
                "year": 2024,
                "title": "2024 Toyota Camry",
                "pricing_maturity": "market_comp",
                "vin": "4T1C11AK0RU000001",
                "condition_grade": "Good",
                "source_site": "publicsurplus",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "2024 Toyota Camry",
                },
            }
        ],
        "webhook_log": [],
        "alert_log": [],
        "ingest_delivery_log": [],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()
    opportunities = result["opportunities"]
    breakdown = opportunities["active_dos80_gate_breakdown"][0]

    assert breakdown["eligible"] is False
    assert "condition_evidence_missing" in breakdown["blocking_reasons"]
    assert opportunities["active_dos80_alert_eligible_sample"] == 0
    assert opportunities["active_dos80_condition_storage_gap_count_sample"] == 1
    assert opportunities["active_dos80_condition_storage_gap_by_source_sample"] == {"publicsurplus": 1}
    assert opportunities["active_dos80_condition_storage_gap_samples"][0]["id"] == "missing-condition-proof"


def test_pipeline_truth_distinguishes_explicit_condition_damage_from_heuristic(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "explicit-damage",
                "is_active": True,
                "dos_score": 92,
                "mileage": 30000,
                "year": 2024,
                "title": "2024 Ford F-150",
                "pricing_maturity": "market_comp",
                "vin": "1FTFW1E50PFA12345",
                "condition_grade": "Poor",
                "source_site": "gsaauctions",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "Runs but has frame damage.",
                    "damage_type": "frame damage",
                },
            },
            {
                "id": "old-mileage",
                "is_active": True,
                "dos_score": 89,
                "mileage": 87540,
                "year": 2017,
                "title": "2017 Chevrolet Tahoe",
                "pricing_maturity": "market_comp",
                "vin": "1GNSKCKC0HR123456",
                "condition_grade": "Poor",
                "source_site": "jjkane",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.9,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()

    assert result["opportunities"]["active_dos80_condition_blocker_basis_counts_sample"] == {
        "explicit_negative_condition_signal": 1,
        "age_mileage_heuristic": 1,
    }
    assert result["opportunities"]["active_dos80_condition_blocker_basis_by_source_sample"] == {
        "gsaauctions": {
            "explicit_negative_condition_signal": 1,
        },
        "jjkane": {
            "age_mileage_heuristic": 1,
        },
    }
    breakdown_by_id = {
        item["id"]: item
        for item in result["opportunities"]["active_dos80_gate_breakdown"]
    }
    assert breakdown_by_id["explicit-damage"]["signals"]["condition_blocker_basis"] == "explicit_negative_condition_signal"
    assert breakdown_by_id["old-mileage"]["signals"]["condition_blocker_basis"] == "age_mileage_heuristic"

    samples_by_id = {
        item["id"]: item
        for item in result["opportunities"]["active_dos80_condition_blocker_basis_samples"]
    }
    assert samples_by_id["explicit-damage"]["condition_blocker_basis"] == "explicit_negative_condition_signal"
    assert samples_by_id["explicit-damage"]["condition_signals"] == ["frame damage"]
    assert samples_by_id["explicit-damage"]["source_text_excerpt"] == "2024 Ford F-150 Runs but has frame damage. frame damage"
    assert samples_by_id["old-mileage"]["condition_blocker_basis"] == "age_mileage_heuristic"
    assert samples_by_id["old-mileage"]["condition_signals"] == []
    assert samples_by_id["old-mileage"]["source_text_excerpt"] == "2017 Chevrolet Tahoe"


def test_pipeline_truth_classifies_gsa_repair_warning_phrases_as_explicit(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "gsa-warning",
                "is_active": True,
                "dos_score": 87,
                "mileage": 64777,
                "year": 2017,
                "title": "2017 FORD EXPLORER",
                "pricing_maturity": "market_comp",
                "vin": "1FM5K7B86HGD24032",
                "condition_grade": "Poor",
                "source_site": "gsaauctions",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.95,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "Need Jumpstart. LIGHTS ON: Check Engine. Repairs required include battery."
                },
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()

    assert result["opportunities"]["active_dos80_condition_blocker_basis_counts_sample"] == {
        "explicit_negative_condition_signal": 1,
    }
    sample = result["opportunities"]["active_dos80_condition_blocker_basis_samples"][0]
    assert sample["condition_blocker_basis"] == "explicit_negative_condition_signal"
    assert sample["condition_signals"] == ["need jumpstart", "check engine", "repairs required"]


def test_pipeline_truth_classifies_open_recall_without_remedy_as_explicit(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "jjkane-recall",
                "is_active": True,
                "dos_score": 81,
                "mileage": 94998,
                "year": 2018,
                "title": "2018 Ford Explorer Police 4WD",
                "pricing_maturity": "market_comp",
                "vin": "1FM5K8AR3JGA99780",
                "condition_grade": "Poor",
                "source_site": "jjkane",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.95,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": (
                        "Open Manufacturer Recall Number 24S02 Remedy Not Yet Available. "
                        "Exterior A-pillar applique trim may be loose, missing or become detached."
                    ),
                },
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()

    assert result["opportunities"]["active_dos80_condition_blocker_basis_counts_sample"] == {
        "explicit_negative_condition_signal": 1,
    }
    sample = result["opportunities"]["active_dos80_condition_blocker_basis_samples"][0]
    assert sample["condition_blocker_basis"] == "explicit_negative_condition_signal"
    assert "open manufacturer recall" in sample["condition_signals"]
    assert "remedy not yet available" in sample["condition_signals"]


def test_pipeline_truth_uses_detail_text_when_description_is_title_like(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "opportunities": [
            {
                "id": "govdeals-detail-text",
                "is_active": True,
                "dos_score": 86.9,
                "mileage": 13983,
                "year": 2020,
                "title": "2020 Dodge Durango SRT",
                "pricing_maturity": "market_comp",
                "vin": "1C4SDJGJ6LC324462",
                "condition_grade": "Poor",
                "source_site": "govdeals",
                "investment_grade": "Platinum",
                "roi_per_day": 300,
                "bid_headroom": 1000,
                "current_bid_trust_score": 0.95,
                "mmr_confidence_proxy": 90,
                "pricing_source": "market_comp",
                "retail_comp_count": 5,
                "retail_comp_confidence": 0.9,
                "projected_total_cost": 10000,
                "max_bid": 12000,
                "expected_close_bid": 10000,
                "raw_data": {
                    "description": "2020 Dodge Durango SRT",
                    "detail_text": "Starts, runs and drives. Minor scratches noted.",
                },
            },
        ],
        "market_prices": [],
        "dealer_sales": [],
    }))

    result = internal.build_pipeline_truth()

    sample = result["opportunities"]["active_dos80_condition_blocker_basis_samples"][0]
    assert sample["condition_signals"] == ["runs and drives"]
    assert sample["source_text_excerpt"] == (
        "2020 Dodge Durango SRT Starts, runs and drives. Minor scratches noted."
    )


def test_pipeline_truth_requires_usable_market_prices(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
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

    assert result["pricing_substrate"]["market_prices_table"] == "present"
    assert result["pricing_substrate"]["market_prices_rows"] == 1
    assert result["pricing_substrate"]["market_prices_usable_rows"] == 1
    assert result["pricing_substrate"]["market_prices_unusable_reason_counts"] == {}
    assert result["pricing_substrate"]["market_prices_latest_expires_at"] == "2099-01-01T00:00:00+00:00"
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is True


def test_pipeline_truth_uses_row_predicates_for_market_price_readiness(monkeypatch):
    monkeypatch.setattr(internal, "_optional_filtered_count", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
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

    assert result["pricing_substrate"]["market_prices_usable_rows"] == 1
    assert result["pricing_substrate"]["market_prices_unusable_reason_counts"] == {}
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is True


def test_pipeline_truth_reports_why_market_prices_are_not_usable(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "market_prices": [
            {
                "id": "market-1",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2020-01-01T00:00:00+00:00",
                "source": "seeded_market_comp",
            },
            {
                "id": "market-2",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "source": None,
            },
            {
                "id": "market-3",
                "avg_price": 0,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 3,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "source": "seeded_market_comp",
            },
            {
                "id": "market-4",
                "avg_price": 25000,
                "low_price": 23000,
                "high_price": 27000,
                "sample_size": 1,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "source": "seeded_market_comp",
            },
        ],
    }))

    result = internal.build_pipeline_truth()

    assert result["pricing_substrate"]["market_prices_table"] == "present"
    assert result["pricing_substrate"]["market_prices_rows"] == 4
    assert result["pricing_substrate"]["market_prices_usable_rows"] == 0
    assert result["pricing_substrate"]["market_prices_unusable_reason_counts"] == {
        "expired": 1,
        "source_missing": 1,
        "nonpositive_price": 1,
        "sample_size_lt_2": 1,
    }
    assert result["pricing_substrate"]["market_prices_latest_expires_at"] == "2099-01-01T00:00:00+00:00"
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is False


def test_pipeline_truth_accepts_recent_positive_dealer_sales(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "market_prices": [],
        "dealer_sales": [
            {"id": "sale-1", "sale_price": 22000, "sale_date": "2099-01-01T00:00:00+00:00"},
            {"id": "sale-2", "sale_price": 23000, "sale_date": "2099-01-02T00:00:00+00:00"},
        ],
    }))

    result = internal.build_pipeline_truth()

    assert result["pricing_substrate"]["market_prices_table"] == "present"
    assert result["pricing_substrate"]["market_prices_rows"] == 0
    assert result["pricing_substrate"]["dealer_sales_rows"] == 2
    assert result["pricing_substrate"]["dealer_sales_usable_rows"] == 2
    assert result["pricing_substrate"]["latest_dealer_sale_date"] == "2099-01-02T00:00:00+00:00"
    assert result["pricing_substrate"]["ready_for_market_comp_pricing"] is True


def test_pipeline_truth_reports_alerts_runtime_status(monkeypatch):
    from webapp.routers import internal

    monkeypatch.setenv("ALERTS_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    status = internal._alerts_runtime_status()

    assert status == {
        "enabled": False,
        "source": "env",
        "raw_value": "false",
        "production_default": "true",
        "telegram_bot_configured": True,
        "telegram_chat_configured": False,
        "telegram_ready": False,
    }

    monkeypatch.delenv("ALERTS_ENABLED", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")
    status = internal._alerts_runtime_status()

    assert status["enabled"] is True
    assert status["source"] == "production_default"
    assert status["telegram_bot_configured"] is True
    assert status["telegram_chat_configured"] is True
    assert status["telegram_ready"] is True
