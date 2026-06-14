from scripts import supabase_live_inspection as inspection


def test_count_does_not_assume_tables_have_id_column(monkeypatch):
    requests = []

    def fake_request(_base_url, _service_key, table, params, **kwargs):
        requests.append((table, dict(params), dict(kwargs)))
        return 200, {"Content-Range": "0-0/2"}, [{"source_name": "allsurplus"}]

    monkeypatch.setattr(inspection, "_request", fake_request)

    assert inspection._count("https://example.supabase.co", "service-key", "source_health_daily") == 2
    assert requests[0][1]["select"] == "*"
    assert requests[0][2]["count"] is True


def test_run_id_truth_audit_includes_sanitized_comp_ledger_aggregates(monkeypatch):
    columns = {
        "ingest_delivery_log": {"run_id", "listing_id", "channel", "status", "error_message", "created_at", "updated_at"},
        "webhook_log": {"run_id", "received_at", "processing_status", "error_message", "item_count", "actor_id"},
        "opportunities": {"id", "run_id", "source_site", "status", "vin", "mileage", "created_at"},
        "market_scout_runs": {"run_id", "source_name", "status", "records_found", "records_candidate", "records_rejected", "error_count", "created_at", "updated_at"},
        "sold_comp_candidates": {"id", "run_id", "source_name", "source_listing_id", "channel", "candidate_status", "rejection_reason", "created_at", "updated_at"},
        "sold_comp_reviews": {"candidate_id", "review_status", "reviewer", "reviewer_version", "created_at", "updated_at"},
        "verified_sold_comps": {"candidate_id", "source_name", "channel", "created_at", "updated_at"},
        "scrape_runs": {"run_id", "source_name", "status", "item_count", "evaluated_count", "saved_count", "skipped_count", "failed_count", "parse_event_count", "started_at", "completed_at"},
        "parse_events": {"run_id", "source_name", "event_type", "status", "reason", "created_at"},
    }
    rows = {
        "ingest_delivery_log": [
            {"run_id": "run-1", "listing_id": "a", "channel": "db_save", "status": "candidate_staged", "created_at": "2026-06-03T00:00:01Z"},
            {"run_id": "run-1", "listing_id": "b", "channel": "db_save", "status": "candidate_staged", "created_at": "2026-06-03T00:00:02Z"},
        ],
        "webhook_log": [
            {"run_id": "run-1", "received_at": "2026-06-03T00:00:00Z", "processing_status": "processed", "item_count": 2},
        ],
        "opportunities": [],
        "market_scout_runs": [
            {
                "run_id": "run-1",
                "id": "candidate-1",
                "source_name": "govdeals-sold",
                "status": "collecting",
                "records_found": 2,
                "records_candidate": 2,
                "records_rejected": 0,
                "error_count": 0,
                "created_at": "2026-06-03T00:00:00Z",
            }
        ],
        "sold_comp_candidates": [
            {
                "run_id": "run-1",
                "id": "candidate-2",
                "source_name": "govdeals-sold",
                "source_listing_id": "asset-1",
                "channel": "gov",
                "candidate_status": "candidate",
                "created_at": "2026-06-03T00:00:01Z",
            },
            {
                "run_id": "run-1",
                "source_name": "govdeals-sold",
                "source_listing_id": "asset-2",
                "channel": "gov",
                "candidate_status": "rejected",
                "rejection_reason": "missing_year_make_model",
                "created_at": "2026-06-03T00:00:02Z",
            },
            {
                "run_id": "run-1",
                "id": "candidate-3",
                "source_name": "publicsurplus-sold",
                "source_listing_id": "asset-1",
                "channel": "surplus",
                "candidate_status": "candidate",
                "created_at": "2026-06-03T00:00:03Z",
            },
        ],
        "sold_comp_reviews": [
            {"candidate_id": "candidate-1", "review_status": "accepted", "reviewer": "market_scout_verifier"},
            {"candidate_id": "candidate-2", "review_status": "rejected", "reviewer": "market_scout_verifier"},
            {"candidate_id": "candidate-3", "review_status": "accepted", "reviewer": "market_scout_verifier"},
        ],
        "verified_sold_comps": [
            {"candidate_id": "candidate-1", "source_name": "govdeals-sold", "channel": "gov"},
            {"candidate_id": "candidate-3", "source_name": "publicsurplus-sold", "channel": "surplus"},
        ],
        "scrape_runs": [
            {
                "run_id": "run-1",
                "source_name": "all-surplus",
                "status": "processed",
                "item_count": 5,
                "evaluated_count": 4,
                "saved_count": 0,
                "skipped_count": 1,
                "failed_count": 0,
                "parse_event_count": 5,
                "started_at": "2026-06-03T00:00:00Z",
                "completed_at": "2026-06-03T00:00:05Z",
            }
        ],
        "parse_events": [
            {"run_id": "run-1", "source_name": "all-surplus", "event_type": "db_save", "status": "vin_dedup_lifecycle_refreshed", "created_at": "2026-06-03T00:00:01Z"},
            {"run_id": "run-1", "source_name": "all-surplus", "event_type": "gate", "status": "skipped_gate", "reason": "age_or_mileage_exceeded", "created_at": "2026-06-03T00:00:02Z"},
        ],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])

    requests = []

    def fake_request(_base_url, _service_key, table, params, **_kwargs):
        requests.append((table, dict(params)))
        selected = str(params.get("select") or "").split(",")
        selected = [column for column in selected if column]
        if not selected:
            return 200, {}, rows[table]
        return 200, {}, [
            {column: row[column] for column in selected if column in row}
            for row in rows[table]
        ]

    monkeypatch.setattr(inspection, "_request", fake_request)

    report = inspection._run_id_truth_audit("https://example.supabase.co", "service-key", "run-1")

    assert report["scrape_runs"]["row_count"] == 1
    assert report["scrape_runs"]["status_counts"] == {"processed": 1}
    assert report["scrape_runs"]["total_item_count"] == 5
    assert report["scrape_runs"]["total_parse_event_count"] == 5
    assert report["parse_events"]["row_count"] == 2
    assert report["parse_events"]["event_type_counts"] == {"db_save": 1, "gate": 1}
    assert report["parse_events"]["status_counts"] == {"vin_dedup_lifecycle_refreshed": 1, "skipped_gate": 1}
    assert report["market_scout_runs"]["row_count"] == 1
    assert report["market_scout_runs"]["source_counts"] == {"govdeals-sold": 1}
    assert report["sold_comp_candidates"]["row_count"] == 3
    assert report["sold_comp_candidates"]["distinct_source_listing_ids"] == 2
    assert report["sold_comp_candidates"]["distinct_source_listing_keys"] == 3
    assert report["sold_comp_candidates"]["status_counts"] == {"candidate": 2, "rejected": 1}
    assert report["sold_comp_candidates"]["rejection_reason_counts"] == {"missing_year_make_model": 1}
    assert report["sold_comp_reviews"]["row_count"] == 3
    assert report["sold_comp_reviews"]["review_status_counts"] == {"accepted": 2, "rejected": 1}
    assert report["verified_sold_comps"]["row_count"] == 2
    assert report["verified_sold_comps"]["source_counts"] == {"govdeals-sold": 1, "publicsurplus-sold": 1}
    candidate_requests = [params for table, params in requests if table == "sold_comp_candidates"]
    assert "id" in candidate_requests[0]["select"].split(",")
    assert "listing_url" not in str(report)
    assert "raw_payload" not in str(report)
    assert "2021 Mercedes-Benz G-Class" not in str(report)


def test_run_id_truth_audit_proves_media_and_bidder_counts_for_linked_rows(monkeypatch):
    columns = {
        "ingest_delivery_log": {"run_id", "listing_id", "opportunity_id", "channel", "status", "created_at", "updated_at"},
        "webhook_log": {"run_id", "received_at", "processing_status", "item_count", "actor_id"},
        "opportunities": {
            "id",
            "listing_id",
            "run_id",
            "source_run_id",
            "source_site",
            "step_status",
            "vin",
            "mileage",
            "photo_count",
            "bidder_count",
            "created_at",
            "raw_data",
        },
        "market_scout_runs": {"run_id", "source_name"},
        "sold_comp_candidates": {"id", "run_id", "source_name"},
        "sold_comp_reviews": {"candidate_id", "review_status"},
        "verified_sold_comps": {"candidate_id", "source_name"},
        "scrape_runs": {"run_id", "source_name", "status", "item_count", "evaluated_count", "saved_count", "skipped_count", "failed_count", "parse_event_count", "started_at", "completed_at"},
        "parse_events": {"run_id", "source_name", "event_type", "status", "reason", "created_at"},
    }
    rows = {
        "ingest_delivery_log": [
            {"run_id": "run-photo", "listing_id": "listing-a", "channel": "db_save", "status": "vin_dedup_lifecycle_refreshed", "created_at": "2026-06-13T00:00:01Z"},
            {"run_id": "run-photo", "listing_id": "listing-b", "channel": "db_save", "status": "duplicate_lifecycle_refreshed", "created_at": "2026-06-13T00:00:02Z"},
            {"run_id": "run-photo", "listing_id": "listing-c", "opportunity_id": "old-c", "channel": "db_save", "status": "duplicate_lifecycle_refreshed", "created_at": "2026-06-13T00:00:03Z"},
        ],
        "webhook_log": [{"run_id": "run-photo", "received_at": "2026-06-13T00:00:00Z", "processing_status": "processed", "item_count": 2}],
        "opportunities": [
            {"id": "old-a", "listing_id": "listing-a", "source_site": "proxibid", "photo_count": 1, "bidder_count": 5, "step_status": "complete", "raw_data": {"photo_url": "https://example.test/a.jpg"}},
            {"id": "old-b", "listing_id": "listing-b", "source_site": "proxibid", "photo_count": 4, "bidder_count": 0, "step_status": "complete", "raw_data": {"photos": ["https://example.test/b-1.jpg", "https://example.test/b-2.jpg"]}},
            {"id": "old-c", "listing_id": "listing-c", "source_site": "proxibid", "photo_count": 0, "bidder_count": 9, "step_status": "complete", "raw_data": {"image_url": "https://example.test/c.jpg"}},
        ],
        "market_scout_runs": [],
        "sold_comp_candidates": [],
        "sold_comp_reviews": [],
        "verified_sold_comps": [],
        "scrape_runs": [{"run_id": "run-photo", "source_name": "proxibid", "status": "processed", "item_count": 3, "evaluated_count": 3, "saved_count": 0, "skipped_count": 0, "failed_count": 0, "parse_event_count": 3}],
        "parse_events": [
            {"run_id": "run-photo", "source_name": "proxibid", "event_type": "db_save", "status": "vin_dedup_lifecycle_refreshed", "created_at": "2026-06-13T00:00:01Z"},
            {"run_id": "run-photo", "source_name": "proxibid", "event_type": "db_save", "status": "duplicate_lifecycle_refreshed", "created_at": "2026-06-13T00:00:02Z"},
            {"run_id": "run-photo", "source_name": "proxibid", "event_type": "db_save", "status": "duplicate_lifecycle_refreshed", "created_at": "2026-06-13T00:00:03Z"},
        ],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    requests = []

    def fake_request(_base_url, _service_key, table, params, **_kwargs):
        requests.append((table, dict(params)))
        table_rows = list(rows[table])
        if table == "opportunities":
            if params.get("run_id") or params.get("source_run_id"):
                table_rows = []
            elif params.get("listing_id") == "in.(listing-a,listing-b,listing-c)":
                table_rows = rows[table]
            elif params.get("id") == "in.(old-c)":
                table_rows = [rows[table][2]]
        selected = [column for column in str(params.get("select") or "").split(",") if column]
        if selected:
            table_rows = [
                {column: row[column] for column in selected if column in row}
                for row in table_rows
            ]
        return 200, {}, table_rows

    monkeypatch.setattr(inspection, "_request", fake_request)

    report = inspection._run_id_truth_audit("https://example.supabase.co", "service-key", "run-photo")

    assert report["opportunities"]["row_count"] == 3
    assert report["opportunities"]["photo_count_known_rows"] == 3
    assert report["opportunities"]["positive_photo_count_rows"] == 2
    assert report["opportunities"]["raw_photo_evidence_rows"] == 3
    assert report["opportunities"]["suppressed_raw_photo_evidence_rows"] == 1
    assert report["opportunities"]["max_photo_count"] == 4
    assert report["opportunities"]["average_photo_count"] == 1.67
    assert report["opportunities"]["bidder_count_known_rows"] == 3
    assert report["opportunities"]["zero_bidder_count_rows"] == 1
    assert report["opportunities"]["positive_bidder_count_rows"] == 2
    assert report["opportunities"]["max_bidder_count"] == 9
    assert report["opportunities"]["average_bidder_count"] == 4.67
    assert report["delivery_log"]["rows_with_opportunity_id"] == 1
    assert report["delivery_log"]["distinct_opportunity_ids"] == 1
    opportunity_requests = [params for table, params in requests if table == "opportunities"]
    assert any(params.get("listing_id") == "in.(listing-a,listing-b,listing-c)" for params in opportunity_requests)
    assert any(params.get("id") == "in.(old-c)" for params in opportunity_requests)
    assert "listing_url" not in str(report)
    assert "raw_data" not in str(report)


def test_run_id_truth_audit_surfaces_comp_ledger_read_failures(monkeypatch):
    columns = {
        "ingest_delivery_log": {"run_id", "status"},
        "webhook_log": {"run_id", "processing_status"},
        "opportunities": {"id", "run_id"},
        "market_scout_runs": {"run_id", "source_name"},
        "sold_comp_candidates": {"id", "run_id", "source_name"},
        "sold_comp_reviews": {"candidate_id", "review_status"},
        "verified_sold_comps": {"candidate_id", "source_name"},
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])

    def fake_request(_base_url, _service_key, table, _params, **_kwargs):
        if table == "market_scout_runs":
            raise RuntimeError("permission denied for market_scout_runs")
        if table == "sold_comp_candidates":
            raise RuntimeError("network timeout while reading candidates")
        return 200, {}, []

    monkeypatch.setattr(inspection, "_request", fake_request)

    report = inspection._run_id_truth_audit("https://example.supabase.co", "service-key", "run-1")

    assert report["market_scout_runs"]["failure"] == "permission denied for market_scout_runs"
    assert report["sold_comp_candidates"]["failure"] == "network timeout while reading candidates"
    assert report["market_scout_runs"]["row_count"] is None
    assert report["sold_comp_candidates"]["row_count"] is None


def test_safe_truth_audit_includes_sanitized_post_close_queue_aggregates(monkeypatch):
    columns = {
        "opportunities": {
            "created_at",
            "source_site",
            "state",
            "year",
            "dos_score",
            "current_bid",
            "gross_margin",
            "bid_headroom",
            "pricing_maturity",
            "status",
            "is_active",
            "make",
            "model",
            "mileage",
            "vin",
            "condition_grade",
            "auction_end_date",
            "risk_flags",
            "photo_count",
            "bidder_count",
            "listing_url",
            "raw_data",
        },
        "alert_log": {"created_at", "status", "delivery_status", "channel"},
        "webhook_log": {"created_at", "received_at", "processing_status"},
        "ingest_delivery_log": {
            "run_id",
            "source_site",
            "source",
            "channel",
            "status",
            "error_message",
            "created_at",
            "listing_url",
            "vin",
        },
        "post_close_outcome_requests": {
            "source_site",
            "outcome_status",
            "referral_source",
            "referral_reason",
            "check_attempts",
            "created_at",
            "updated_at",
            "next_check_at",
            "listing_url",
            "vin",
            "metadata",
        },
        "source_health_daily": {
            "observed_date",
            "source_name",
            "total_runs",
            "processed_runs",
            "failed_runs",
            "item_count",
            "saved_count",
            "skipped_count",
            "parse_event_count",
            "latest_started_at",
        },
    }
    rows = {
        "opportunities": [],
        "alert_log": [],
        "webhook_log": [],
        "ingest_delivery_log": [
            {
                "source_site": "govdeals",
                "channel": "db_save",
                "status": "skipped_gate",
                "error_message": "age_or_mileage_exceeded",
                "created_at": "2026-06-03T19:00:01Z",
                "listing_url": "https://example.com/private-listing",
                "vin": "1FTFW1E50PFA00000",
            },
            {
                "source_site": "govdeals",
                "channel": "db_save",
                "status": "skipped_margin",
                "error_message": "margin_below_floor",
                "created_at": "2026-06-03T19:00:02Z",
            },
            {
                "source_site": "publicsurplus",
                "channel": "db_save",
                "status": "skipped_margin",
                "error_message": "margin_below_floor",
                "created_at": "2026-06-03T19:00:03Z",
            },
        ],
        "post_close_outcome_requests": [
            {
                "source_site": "govdeals",
                "outcome_status": "pending",
                "referral_source": "deal_expiry_sweeper",
                "referral_reason": "expired_opportunity",
                "check_attempts": 0,
                "created_at": "2026-06-03T19:00:00Z",
                "next_check_at": "2026-06-03T19:15:00Z",
                "listing_url": "https://example.com/private-listing",
                "vin": "1FTFW1E50PFA00000",
                "metadata": {"title": "Sensitive listing title"},
            },
            {
                "source_site": "govdeals",
                "outcome_status": "pending",
                "referral_source": "deal_expiry_sweeper",
                "referral_reason": "expired_opportunity",
                "check_attempts": 2,
                "created_at": "2026-06-03T19:01:00Z",
                "updated_at": "2026-06-03T19:03:00Z",
            },
            {
                "source_site": "publicsurplus",
                "outcome_status": "checked_no_result",
                "referral_source": "close_tracker",
                "referral_reason": "scheduled_close_check",
                "check_attempts": 1,
                "created_at": "2026-06-03T19:02:00Z",
            },
        ],
        "source_health_daily": [
            {
                "observed_date": "2026-06-03",
                "source_name": "govdeals",
                "total_runs": 2,
                "processed_runs": 1,
                "failed_runs": 1,
                "item_count": 12,
                "saved_count": 3,
                "skipped_count": 8,
                "parse_event_count": 11,
                "latest_started_at": "2026-06-03T19:03:00Z",
            },
            {
                "observed_date": "2026-06-03",
                "source_name": "publicsurplus",
                "total_runs": 1,
                "processed_runs": 1,
                "failed_runs": 0,
                "item_count": 4,
                "saved_count": 1,
                "skipped_count": 2,
                "parse_event_count": 3,
                "latest_started_at": "2026-06-03T19:02:00Z",
            },
        ],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

    report = inspection._safe_truth_audit("https://example.supabase.co", "service-key")

    assert report["post_close_outcome_requests"]["sample_count"] == 3
    assert report["recent_deliveries"]["sample_count"] == 3
    assert report["recent_deliveries"]["source_counts"] == {"govdeals": 2, "publicsurplus": 1}
    assert report["source_health_daily"]["sample_count"] == 2
    assert report["source_health_daily"]["source_counts"] == {"govdeals": 1, "publicsurplus": 1}
    assert report["source_health_daily"]["total_runs"] == 3
    assert report["source_health_daily"]["failed_runs"] == 1
    assert report["source_health_daily"]["parse_event_count"] == 14
    assert report["seller_recovery_audit"]["status"] == "ok"
    assert report["seller_recovery_audit"]["summary"]["candidate_count"] == 0
    assert report["seller_recovery_audit"]["unsupported_dimensions"]["bidder_depth"]["status"] == "unavailable"
    assert report["seller_recovery_audit"]["unsupported_dimensions"]["photo_count"]["status"] == "unavailable"
    assert report["recent_deliveries"]["status_counts"] == {"skipped_margin": 2, "skipped_gate": 1}
    assert report["recent_deliveries"]["source_status_counts"] == [
        {"source": "govdeals", "status": "skipped_gate", "count": 1},
        {"source": "govdeals", "status": "skipped_margin", "count": 1},
        {"source": "publicsurplus", "status": "skipped_margin", "count": 1},
    ]
    assert report["recent_deliveries"]["sanitized_error_counts"] == {
        "margin_below_floor": 2,
        "age_or_mileage_exceeded": 1,
    }
    assert report["post_close_outcome_requests"]["source_counts"] == {"govdeals": 2, "publicsurplus": 1}
    assert report["post_close_outcome_requests"]["outcome_status_counts"] == {
        "pending": 2,
        "checked_no_result": 1,
    }
    assert report["post_close_outcome_requests"]["referral_source_counts"] == {
        "deal_expiry_sweeper": 2,
        "close_tracker": 1,
    }
    assert report["post_close_outcome_requests"]["referral_reason_counts"] == {
        "expired_opportunity": 2,
        "scheduled_close_check": 1,
    }
    assert report["post_close_outcome_requests"]["check_attempts_total"] == 3
    assert report["post_close_outcome_requests"]["latest_created_at"] == "2026-06-03T19:02:00Z"
    assert report["post_close_outcome_requests"]["next_check_at"] == "2026-06-03T19:15:00Z"
    assert "private-listing" not in str(report)
    assert "1FTFW1E50PFA00000" not in str(report)
    assert "Sensitive listing title" not in str(report)


def test_seller_recovery_audit_reports_governed_bidder_depth_when_queryable():
    rows = [
        {
            "is_active": True,
            "source_site": "hibid",
            "year": 2024,
            "make": "Ford",
            "model": "F-150",
            "dos_score": 84,
            "gross_margin": 5000,
            "bid_headroom": 1200,
            "pricing_maturity": "market_comp",
            "vin": "1FTFW1E50PFA00000",
            "mileage": 15000,
            "condition_grade": "Good",
            "auction_end_date": "2026-06-20T00:00:00Z",
            "risk_flags": [],
            "photo_count": 4,
            "bidder_count": 11,
        },
        {
            "is_active": True,
            "source_site": "publicsurplus",
            "year": 2023,
            "make": "Toyota",
            "model": "Camry",
            "dos_score": 81,
            "gross_margin": 4200,
            "bid_headroom": 900,
            "pricing_maturity": "market_comp",
            "vin": "1HGCM82633A004352",
            "mileage": 18000,
            "condition_grade": "Good",
            "auction_end_date": "2026-06-20T00:00:00Z",
            "risk_flags": [],
            "photo_count": 2,
            "bidder_count": None,
        },
    ]

    report = inspection._summarize_seller_recovery_audit(
        opportunity_rows=rows,
        source_health_rows=[{"source_name": "hibid"}],
        delivery_rows=[],
        parse_event_rows=[],
    )

    assert report["listing_quality"]["bidder_count_known_count"] == 1
    assert report["listing_quality"]["zero_bidder_count"] == 0
    assert report["listing_quality"]["thin_bidder_count"] == 0
    assert report["listing_quality"]["average_bidder_count"] == 11.0
    assert report["unsupported_dimensions"]["bidder_depth"]["status"] == "available"
    assert "bidder_depth" not in report["summary"]["unavailable_dimensions"]


def test_seller_recovery_audit_reports_source_mirror_bidder_depth_when_opportunities_lack_it():
    report = inspection._summarize_seller_recovery_audit(
        opportunity_rows=[
            {
                "is_active": True,
                "source_site": "hibid",
                "year": 2024,
                "make": "Ford",
                "model": "F-150",
                "dos_score": 84,
                "gross_margin": 5000,
                "bid_headroom": 1200,
                "pricing_maturity": "proxy",
                "photo_count": 1,
                "bidder_count": None,
            }
        ],
        source_listing_rows=[
            {
                "source_site": "hibid",
                "source": "hibid",
                "bidder_count": 6,
                "created_at": "2026-06-13T14:00:00Z",
            }
        ],
        source_health_rows=[{"source_name": "hibid"}],
        delivery_rows=[],
        parse_event_rows=[],
    )

    assert report["listing_quality"]["bidder_count_known_count"] == 0
    assert report["source_listing_quality"]["bidder_count_known_count"] == 1
    assert report["source_listing_quality"]["average_bidder_count"] == 6.0
    assert report["unsupported_dimensions"]["bidder_depth"]["status"] == "available"
    assert report["unsupported_dimensions"]["bidder_depth"]["evidence_surface"] == "source_mirror"
    assert "bidder_depth" not in report["summary"]["unavailable_dimensions"]
    candidate = report["value_leak_candidates"][0]
    assert candidate["evidence"]["bidder_depth_surface"] == "source_mirror"
    assert candidate["evidence"]["source_mirror_bidder_count_present"] is True


def test_seller_recovery_audit_does_not_apply_source_mirror_bidder_depth_cross_source():
    report = inspection._summarize_seller_recovery_audit(
        opportunity_rows=[
            {
                "is_active": True,
                "source_site": "govdeals",
                "year": 2024,
                "make": "Ford",
                "model": "F-150",
                "dos_score": 84,
                "gross_margin": 5000,
                "bid_headroom": 1200,
                "pricing_maturity": "proxy",
                "photo_count": 1,
                "bidder_count": None,
            }
        ],
        source_listing_rows=[
            {
                "source_site": "hibid",
                "source": "hibid",
                "bidder_count": 6,
                "created_at": "2026-06-13T14:00:00Z",
            }
        ],
        source_health_rows=[{"source_name": "govdeals"}],
        delivery_rows=[],
        parse_event_rows=[],
    )

    assert report["unsupported_dimensions"]["bidder_depth"]["status"] == "available"
    candidate = report["value_leak_candidates"][0]
    assert candidate["source_site"] == "govdeals"
    assert candidate["evidence"]["bidder_depth_surface"] is None
    assert candidate["evidence"]["source_mirror_bidder_count_present"] is False


def test_seller_recovery_audit_counts_failed_sources_distinctly():
    report = inspection._summarize_seller_recovery_audit(
        opportunity_rows=[],
        source_listing_rows=[],
        source_health_rows=[
            {"source_name": "govdeals", "failed_runs": 1},
            {"source_name": "govdeals", "failed_runs": 2},
            {"source_name": "hibid", "failed_runs": 0},
        ],
        delivery_rows=[],
        parse_event_rows=[],
    )

    assert report["source_health_summary"]["observed_source_count"] == 2
    assert report["source_health_summary"]["sources_with_failed_runs"] == 1
    assert report["source_health_summary"]["total_failed_runs"] == 3


def test_safe_truth_audit_includes_sanitized_seller_recovery_candidates(monkeypatch):
    columns = {
        "opportunities": {
            "created_at",
            "source_site",
            "year",
            "make",
            "model",
            "dos_score",
            "gross_margin",
            "bid_headroom",
            "pricing_maturity",
            "is_active",
            "vin",
            "mileage",
            "condition_grade",
            "auction_end_date",
            "risk_flags",
            "photo_count",
            "listing_url",
            "raw_data",
        },
        "alert_log": {"created_at", "status"},
        "webhook_log": {"created_at", "processing_status"},
        "ingest_delivery_log": {"source_site", "status", "error_message", "created_at", "listing_url", "vin"},
        "post_close_outcome_requests": {"created_at", "source_site", "outcome_status"},
        "source_health_daily": {
            "observed_date",
            "source_name",
            "total_runs",
            "processed_runs",
            "failed_runs",
            "item_count",
            "saved_count",
            "skipped_count",
            "parse_event_count",
            "latest_started_at",
        },
        "parse_events": {"source_name", "event_type", "status", "reason", "created_at", "metadata"},
    }
    rows = {
        "opportunities": [
            {
                "created_at": "2026-06-13T02:00:00Z",
                "source_site": "govdeals",
                "year": 2023,
                "make": "Ford",
                "model": "F-150",
                "dos_score": 82,
                "gross_margin": 6200,
                "bid_headroom": 2400,
                "pricing_maturity": "proxy",
                "is_active": True,
                "vin": None,
                "mileage": None,
                "condition_grade": "Unknown",
                "auction_end_date": None,
                "risk_flags": ["missing_photos"],
                "photo_count": 0,
                "listing_url": "https://example.test/private",
                "raw_data": {
                    "description": "private raw text",
                    "vin": "1FTFW1E50PFA00000",
                    "image_url": "https://example.test/private-image.jpg",
                },
            },
        ],
        "alert_log": [],
        "webhook_log": [],
        "ingest_delivery_log": [
            {
                "source_site": "govdeals",
                "status": "skipped_margin",
                "error_message": "margin_below_floor",
                "created_at": "2026-06-13T02:00:00Z",
                "listing_url": "https://example.test/private",
                "vin": "1FTFW1E50PFA00000",
            },
        ],
        "post_close_outcome_requests": [],
        "source_health_daily": [
            {
                "observed_date": "2026-06-13",
                "source_name": "govdeals",
                "total_runs": 1,
                "processed_runs": 1,
                "failed_runs": 0,
                "item_count": 6,
                "saved_count": 1,
                "skipped_count": 4,
                "parse_event_count": 5,
                "latest_started_at": "2026-06-13T02:00:00Z",
            },
        ],
        "parse_events": [
            {
                "source_name": "govdeals",
                "event_type": "db_save",
                "status": "skipped_margin",
                "reason": "margin_below_floor",
                "created_at": "2026-06-13T02:00:01Z",
                "metadata": {"vin": "1FTFW1E50PFA00000", "listing_url": "https://example.test/private"},
            }
        ],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

    report = inspection._safe_truth_audit("https://example.supabase.co", "service-key")

    assert report["seller_recovery_audit"]["summary"]["candidate_count"] == 1
    assert report["seller_recovery_audit"]["listing_quality"]["missing_vin_count"] == 1
    assert report["seller_recovery_audit"]["listing_quality"]["missing_mileage_count"] == 1
    assert report["seller_recovery_audit"]["listing_quality"]["photo_count_known_count"] == 1
    assert report["seller_recovery_audit"]["listing_quality"]["zero_photo_count"] == 1
    assert report["seller_recovery_audit"]["listing_quality"]["raw_photo_evidence_count"] == 1
    assert report["seller_recovery_audit"]["listing_quality"]["suppressed_raw_photo_evidence_count"] == 1
    assert report["seller_recovery_audit"]["unsupported_dimensions"]["photo_count"]["status"] == "available"
    assert "photo_count" not in report["seller_recovery_audit"]["summary"]["unavailable_dimensions"]
    assert report["seller_recovery_audit"]["value_leak_candidates"][0]["recovery_reasons"] == [
        "missing_vin",
        "missing_mileage",
        "missing_auction_end",
        "condition_unverified",
        "proxy_pricing",
        "missing_photos_flag",
        "zero_photo_count",
    ]
    candidate = report["seller_recovery_audit"]["value_leak_candidates"][0]
    assert candidate["recovery_score"] > 0
    assert candidate["recovery_tier"] in {"high", "medium", "low"}
    assert round(sum(candidate["score_components"].values()), 2) == candidate["recovery_score"]
    assert candidate["evidence"]["photo_count_present"] is True
    assert report["seller_recovery_audit"]["recovery_rollups"]["reason_counts"]["missing_photos_flag"] == 1
    assert report["seller_recovery_audit"]["source_health_summary"]["observed_source_count"] == 1
    assert report["seller_recovery_audit"]["truth_boundaries"]["candidate_ranking"].startswith(
        "Internal deterministic prioritization"
    )
    serialized = str(report)
    assert "1FTFW1E50PFA00000" not in serialized
    assert "https://example.test/private" not in serialized
    assert "private raw text" not in serialized


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
        "sonar_listings": {"created_at", "source_site", "source", "bidder_count"},
        "alert_log": {"created_at", "status"},
        "webhook_log": {"created_at", "processing_status"},
        "ingest_delivery_log": {"source_site", "status", "error_message", "created_at"},
        "post_close_outcome_requests": {"created_at", "source_site", "outcome_status"},
        "source_health_daily": {
            "observed_date",
            "source_name",
            "total_runs",
            "processed_runs",
            "failed_runs",
            "item_count",
            "saved_count",
            "skipped_count",
            "parse_event_count",
            "latest_started_at",
        },
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
        "sonar_listings": [],
        "alert_log": [],
        "webhook_log": [],
        "ingest_delivery_log": [],
        "post_close_outcome_requests": [],
        "source_health_daily": [],
        "parse_events": [],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

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


def test_safe_truth_audit_market_data_quality_keeps_zero_dos_from_falling_back_to_score(monkeypatch):
    columns = {
        "opportunities": {
            "created_at",
            "dos_score",
            "score",
            "pricing_maturity",
            "pricing_updated_at",
            "manheim_source_status",
            "retail_comp_count",
            "is_active",
        },
        "sonar_listings": {"created_at", "source_site", "source", "bidder_count"},
        "alert_log": {"created_at", "status"},
        "webhook_log": {"created_at", "processing_status"},
        "ingest_delivery_log": {"source_site", "status", "error_message", "created_at"},
        "post_close_outcome_requests": {"created_at", "source_site", "outcome_status"},
        "source_health_daily": {"observed_date", "source_name", "total_runs", "processed_runs", "failed_runs", "item_count", "saved_count", "skipped_count", "parse_event_count", "latest_started_at"},
        "parse_events": {"source_name", "event_type", "status", "reason", "created_at"},
        "market_prices": {"id", "avg_price", "low_price", "high_price", "sample_size", "expires_at", "source"},
        "dealer_sales": {"id", "sale_price", "sale_date"},
    }
    rows = {
        "opportunities": [
            {
                "created_at": "2099-01-01T00:00:00Z",
                "dos_score": 0,
                "score": 88,
                "pricing_maturity": "proxy",
                "pricing_updated_at": "2099-01-01T00:00:00+00:00",
                "manheim_source_status": "fallback",
                "retail_comp_count": 0,
                "is_active": True,
            }
        ],
        "sonar_listings": [],
        "alert_log": [],
        "webhook_log": [],
        "ingest_delivery_log": [],
        "post_close_outcome_requests": [],
        "source_health_daily": [],
        "parse_events": [],
        "market_prices": [],
        "dealer_sales": [],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

    quality = inspection._safe_truth_audit("https://example.supabase.co", "service-key")["market_data_quality"]

    assert quality["high_score_sample_size"] == 0
    assert quality["high_score_proxy_share"] == 0.0
    assert "high_score_proxy_pricing_present" not in quality["degraded_reasons"]


def test_safe_truth_audit_market_data_quality_includes_pricing_substrate_degradation(monkeypatch):
    columns = {
        "opportunities": {
            "created_at",
            "dos_score",
            "score",
            "pricing_maturity",
            "pricing_updated_at",
            "manheim_source_status",
            "retail_comp_count",
            "is_active",
        },
        "sonar_listings": {"created_at", "source_site", "source", "bidder_count"},
        "alert_log": {"created_at", "status"},
        "webhook_log": {"created_at", "processing_status"},
        "ingest_delivery_log": {"source_site", "status", "error_message", "created_at"},
        "post_close_outcome_requests": {"created_at", "source_site", "outcome_status"},
        "source_health_daily": {"observed_date", "source_name", "total_runs", "processed_runs", "failed_runs", "item_count", "saved_count", "skipped_count", "parse_event_count", "latest_started_at"},
        "parse_events": {"source_name", "event_type", "status", "reason", "created_at"},
        "market_prices": {"id", "avg_price", "low_price", "high_price", "sample_size", "expires_at", "source"},
        "dealer_sales": {"id", "sale_price", "sale_date"},
    }
    rows = {
        "opportunities": [
            {
                "created_at": "2099-01-01T00:00:00Z",
                "dos_score": 82,
                "score": 82,
                "pricing_maturity": "live_market",
                "pricing_updated_at": "2099-01-01T00:00:00+00:00",
                "manheim_source_status": "live",
                "retail_comp_count": 3,
                "is_active": True,
            }
        ],
        "sonar_listings": [],
        "alert_log": [],
        "webhook_log": [],
        "ingest_delivery_log": [],
        "post_close_outcome_requests": [],
        "source_health_daily": [],
        "parse_events": [],
        "market_prices": [],
        "dealer_sales": [{"id": "sale-1", "sale_price": 22000, "sale_date": "2099-01-01T00:00:00+00:00"}],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

    quality = inspection._safe_truth_audit("https://example.supabase.co", "service-key")["market_data_quality"]

    assert quality["status"] == "degraded"
    assert "market_prices_unusable" in quality["degraded_reasons"]
    assert "dealer_sales_sparse" in quality["degraded_reasons"]


def test_safe_truth_audit_attributes_recent_deliveries_from_webhook_run_lineage(monkeypatch):
    columns = {
        "opportunities": {"created_at"},
        "alert_log": {"created_at"},
        "webhook_log": {"run_id", "source", "actor_id", "received_at", "processing_status"},
        "ingest_delivery_log": {"run_id", "channel", "status", "error_message", "created_at"},
        "post_close_outcome_requests": {"created_at"},
    }
    rows = {
        "opportunities": [],
        "alert_log": [],
        "webhook_log": [
            {
                "run_id": "run-govdeals",
                "source": "ds-govdeals",
                "actor_id": "CuKaIAcWyFS0EPrAz",
                "received_at": "2026-06-03T19:00:00Z",
                "processing_status": "processed",
            },
            {
                "run_id": "run-proxibid",
                "source": "ds-proxibid",
                "actor_id": "bxhncvtHEP712WX2e",
                "received_at": "2026-06-03T19:01:00Z",
                "processing_status": "processed",
            },
            {
                "run_id": "run-gsa",
                "source": "apify",
                "actor_id": "fvDnYmGuFBCrwpEi9",
                "received_at": "2026-06-03T19:02:00Z",
                "processing_status": "processed",
            },
        ],
        "ingest_delivery_log": [
            {
                "run_id": "run-govdeals",
                "channel": "db_save",
                "status": "skipped_gate",
                "error_message": "age_or_mileage_exceeded",
                "created_at": "2026-06-03T19:00:01Z",
            },
            {
                "run_id": "run-govdeals",
                "channel": "db_save",
                "status": "skipped_margin",
                "error_message": "margin_below_floor",
                "created_at": "2026-06-03T19:00:02Z",
            },
            {
                "run_id": "run-proxibid",
                "channel": "db_save",
                "status": "skipped_ceiling",
                "error_message": "pricing_maturity_proxy",
                "created_at": "2026-06-03T19:00:03Z",
            },
            {
                "run_id": "run-gsa",
                "channel": "db_save",
                "status": "skipped_gate",
                "error_message": "age_or_mileage_exceeded",
                "created_at": "2026-06-03T19:00:04Z",
            },
        ],
        "post_close_outcome_requests": [],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

    report = inspection._safe_truth_audit("https://example.supabase.co", "service-key")

    assert report["recent_deliveries"]["source_counts"] == {"govdeals": 2, "proxibid": 1, "gsaauctions": 1}
    assert report["recent_deliveries"]["source_status_counts"] == [
        {"source": "govdeals", "status": "skipped_gate", "count": 1},
        {"source": "govdeals", "status": "skipped_margin", "count": 1},
        {"source": "proxibid", "status": "skipped_ceiling", "count": 1},
        {"source": "gsaauctions", "status": "skipped_gate", "count": 1},
    ]
