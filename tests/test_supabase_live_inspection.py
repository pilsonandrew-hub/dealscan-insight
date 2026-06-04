from scripts import supabase_live_inspection as inspection


def test_run_id_truth_audit_includes_sanitized_comp_ledger_aggregates(monkeypatch):
    columns = {
        "ingest_delivery_log": {"run_id", "listing_id", "channel", "status", "error_message", "created_at", "updated_at"},
        "webhook_log": {"run_id", "received_at", "processing_status", "error_message", "item_count", "actor_id"},
        "opportunities": {"id", "run_id", "source_site", "status", "vin", "mileage", "created_at"},
        "market_scout_runs": {"run_id", "source_name", "status", "records_found", "records_candidate", "records_rejected", "error_count", "created_at", "updated_at"},
        "sold_comp_candidates": {"run_id", "source_name", "source_listing_id", "channel", "candidate_status", "rejection_reason", "created_at", "updated_at"},
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
        ],
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])

    def fake_request(_base_url, _service_key, table, _params, **_kwargs):
        return 200, {}, rows[table]

    monkeypatch.setattr(inspection, "_request", fake_request)

    report = inspection._run_id_truth_audit("https://example.supabase.co", "service-key", "run-1")

    assert report["market_scout_runs"]["row_count"] == 1
    assert report["market_scout_runs"]["source_counts"] == {"govdeals-sold": 1}
    assert report["sold_comp_candidates"]["row_count"] == 2
    assert report["sold_comp_candidates"]["distinct_source_listing_ids"] == 2
    assert report["sold_comp_candidates"]["status_counts"] == {"candidate": 1, "rejected": 1}
    assert report["sold_comp_candidates"]["rejection_reason_counts"] == {"missing_year_make_model": 1}
    assert "listing_url" not in str(report)
    assert "raw_payload" not in str(report)
    assert "2021 Mercedes-Benz G-Class" not in str(report)


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
            "status",
            "listing_url",
        },
        "alert_log": {"created_at", "status", "delivery_status", "channel"},
        "webhook_log": {"created_at", "received_at", "processing_status"},
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
    }
    rows = {
        "opportunities": [],
        "alert_log": [],
        "webhook_log": [],
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
    }

    monkeypatch.setattr(inspection, "_available_columns", lambda _base, _key, table: columns[table])
    monkeypatch.setattr(
        inspection,
        "_recent_rows",
        lambda _base, _key, table, _select, _order, _limit: rows[table],
    )

    report = inspection._safe_truth_audit("https://example.supabase.co", "service-key")

    assert report["post_close_outcome_requests"]["sample_count"] == 3
    assert report["post_close_outcome_requests"]["source_counts"] == {"govdeals": 2, "publicsurplus": 1}
    assert report["post_close_outcome_requests"]["outcome_status_counts"] == {
        "pending": 2,
        "checked_no_result": 1,
    }
    assert report["post_close_outcome_requests"]["referral_source_counts"] == {
        "deal_expiry_sweeper": 2,
        "close_tracker": 1,
    }
    assert report["post_close_outcome_requests"]["check_attempts_total"] == 3
    assert report["post_close_outcome_requests"]["latest_created_at"] == "2026-06-03T19:02:00Z"
    assert "private-listing" not in str(report)
    assert "1FTFW1E50PFA00000" not in str(report)
    assert "Sensitive listing title" not in str(report)
