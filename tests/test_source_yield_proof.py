import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "report_source_yield_proof.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
SPEC = importlib.util.spec_from_file_location("report_source_yield_proof", SCRIPT_PATH)
report_source_yield_proof = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(report_source_yield_proof)


def test_classify_source_marks_accepted_flow_present():
    summary = {
        "source": "govdeals",
        "delivery_rows": 8,
        "opportunity_rows": 2,
        "active_opportunity_rows": 1,
        "status_counts": {"skipped_gate": 6, "saved_supabase": 2},
    }

    assert report_source_yield_proof.classify_source_summary(summary) == "accepted_flow_present"


def test_parse_timestamp_normalizes_naive_values_to_utc():
    parsed = report_source_yield_proof._parse_timestamp("2026-06-06T12:34:56")

    assert parsed == datetime(2026, 6, 6, 12, 34, 56, tzinfo=timezone.utc)


def test_script_entrypoint_imports_when_executed_from_repo_root():
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        cwd=SCRIPT_PATH.parents[1],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Report source-by-source live yield" in result.stdout


def test_classify_source_marks_inactive_accepted_flow_separately():
    summary = {
        "source": "publicsurplus",
        "delivery_rows": 205,
        "opportunity_rows": 2,
        "active_opportunity_rows": 0,
        "active_dos80_rows": 0,
        "status_counts": {"saved_supabase": 2, "skipped_margin": 67},
    }

    assert report_source_yield_proof.classify_source_summary(summary) == "inactive_accepted_flow_only"


def test_classify_source_separates_gate_and_margin_dominance():
    gate_summary = {
        "source": "hibid",
        "delivery_rows": 60,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {"skipped_gate": 58, "skipped_ceiling": 2},
    }
    margin_summary = {
        "source": "govdeals",
        "delivery_rows": 34,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {"skipped_margin": 33, "saved_sonar": 1},
    }

    assert report_source_yield_proof.classify_source_summary(gate_summary) == "source_quality_reject_dominant"
    assert report_source_yield_proof.classify_source_summary(margin_summary) == "economic_reject_dominant"


def test_classify_source_separates_pricing_proxy_from_bid_ceiling_dominance():
    proxy_summary = {
        "source": "proxibid",
        "delivery_rows": 3,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {"saved_sonar": 1, "skipped_ceiling": 1, "skipped_proof": 1},
        "reason_counts": {
            "none": 1,
            "pricing_maturity_proxy": 1,
            "source_quality_proof_record": 1,
        },
    }
    ceiling_summary = {
        "source": "proxibid",
        "delivery_rows": 3,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {"saved_sonar": 1, "skipped_ceiling": 1, "skipped_proof": 1},
        "reason_counts": {
            "none": 1,
            "bid_ceiling_exceeded": 1,
            "source_quality_proof_record": 1,
        },
    }

    assert report_source_yield_proof.classify_source_summary(proxy_summary) == "pricing_proxy_reject_dominant"
    assert report_source_yield_proof.classify_run_summary(proxy_summary) == "pricing_proxy_reject_dominant"
    assert report_source_yield_proof.classify_source_summary(ceiling_summary) == "pricing_ceiling_reject_dominant"
    assert report_source_yield_proof.classify_run_summary(ceiling_summary) == "pricing_ceiling_reject_dominant"


def test_classify_source_does_not_let_dirty_proxy_rows_override_clean_bid_ceiling():
    summary = {
        "source": "proxibid",
        "delivery_rows": 4,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {
            "saved_sonar": 1,
            "skipped_ceiling": 2,
            "skipped_proof": 1,
        },
        "reason_counts": {
            "none": 1,
            "bid_ceiling_exceeded": 1,
            "pricing_maturity_proxy": 1,
            "source_quality_proof_record": 1,
        },
        "dirty_rejection_rows": 1,
        "dirty_rejection_reason_counts": {"pricing_maturity_proxy": 1},
    }

    assert summary["delivery_rows"] == sum(summary["status_counts"].values())
    assert summary["delivery_rows"] == sum(summary["reason_counts"].values())
    assert report_source_yield_proof.classify_source_summary(summary) == "pricing_ceiling_reject_dominant"
    assert report_source_yield_proof.classify_run_summary(summary) == "pricing_ceiling_reject_dominant"


def test_classify_source_keeps_clean_proxy_rows_when_dirty_rows_are_unrelated():
    summary = {
        "source": "proxibid",
        "delivery_rows": 5,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {
            "saved_sonar": 1,
            "skipped_ceiling": 2,
            "skipped_gate": 1,
            "skipped_proof": 1,
        },
        "reason_counts": {
            "none": 1,
            "pricing_maturity_proxy": 2,
            "age_or_mileage_exceeded": 1,
            "source_quality_proof_record": 1,
        },
        "dirty_rejection_rows": 1,
        "dirty_rejection_reason_counts": {"age_or_mileage_exceeded": 1},
    }

    assert summary["delivery_rows"] == sum(summary["status_counts"].values())
    assert summary["delivery_rows"] == sum(summary["reason_counts"].values())
    assert report_source_yield_proof.classify_source_summary(summary) == "pricing_proxy_reject_dominant"
    assert report_source_yield_proof.classify_run_summary(summary) == "pricing_proxy_reject_dominant"


def test_classify_source_does_not_let_listing_gap_proxy_rows_override_clean_bid_ceiling():
    summary = {
        "source": "proxibid",
        "delivery_rows": 12,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {
            "saved_sonar": 1,
            "skipped_ceiling": 10,
            "skipped_proof": 1,
        },
        "reason_counts": {
            "none": 1,
            "bid_ceiling_exceeded": 5,
            "pricing_maturity_proxy": 5,
            "source_quality_proof_record": 1,
        },
        "listing_metadata_gap_rows": 5,
        "listing_metadata_gap_status_counts": {"skipped_ceiling": 5},
        "listing_metadata_gap_reason_counts": {"pricing_maturity_proxy": 5},
    }

    assert summary["delivery_rows"] == sum(summary["status_counts"].values())
    assert summary["delivery_rows"] == sum(summary["reason_counts"].values())
    assert report_source_yield_proof.classify_source_summary(summary) == "pricing_ceiling_reject_dominant"
    assert report_source_yield_proof.classify_run_summary(summary) == "pricing_ceiling_reject_dominant"


def test_classify_source_separates_dirty_age_mileage_from_clean_source_quality():
    dirty_only = {
        "source": "hibid",
        "delivery_rows": 20,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {"skipped_gate": 20},
        "reason_counts": {"age_or_mileage_exceeded": 20},
    }
    mixed_clean = {
        "source": "hibid",
        "delivery_rows": 24,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "status_counts": {"skipped_gate": 21, "skipped_margin": 2, "skipped_ceiling": 1},
        "reason_counts": {"age_or_mileage_exceeded": 20, "title_brand_rejected": 1, "margin_below_floor": 2, "pricing_maturity_proxy": 1},
    }

    assert report_source_yield_proof.classify_source_summary(dirty_only) == "dirty_source_reject_only"
    assert report_source_yield_proof.classify_source_summary(mixed_clean) == "economic_reject_dominant"


def test_classify_source_ignores_proof_and_sonar_rows_for_business_outcome():
    summary = {
        "source": "govdeals",
        "delivery_rows": 4,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "channel_counts": {"db_save": 3, "sonar_mirror": 1},
        "status_counts": {"skipped_proof": 2, "skipped_margin": 1, "saved_sonar": 1},
    }

    assert report_source_yield_proof.classify_source_summary(summary) == "economic_reject_dominant"


def test_classify_source_keeps_small_split_business_outcome_mixed():
    summary = {
        "source": "govdeals",
        "delivery_rows": 4,
        "opportunity_rows": 0,
        "active_opportunity_rows": 0,
        "channel_counts": {"db_save": 3, "sonar_mirror": 1},
        "status_counts": {"skipped_proof": 1, "skipped_margin": 1, "skipped_gate": 1, "saved_sonar": 1},
    }

    assert report_source_yield_proof.classify_source_summary(summary) == "mixed_rejection_surface"


def test_build_report_marks_webhook_delivery_gap(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-1",
                    "actor_name": "ds-govdeals",
                    "status": "processed",
                    "item_count": 2,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
    )

    assert report["overall_verdict"] == "diagnostic_gap"
    assert report["source_summaries"][0]["classification"] == "webhook_without_delivery_gap"
    assert report["source_summaries"][0]["source"] == "govdeals"


def test_build_report_separates_zero_item_webhooks_from_delivery_gap(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-empty",
                    "source": "municibid",
                    "status": "processed",
                    "item_count": 0,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
    )

    assert report["overall_verdict"] == "no_recent_accepted_source_yield"
    assert report["source_summaries"][0]["classification"] == "source_empty_result"
    assert report["source_summaries"][0]["webhook_item_count_total"] == 0


def test_build_report_groups_delivery_and_opportunity_truth(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log":
            return []
        if table == "ingest_delivery_log":
            return [
                {"source_site": "hibid", "status": "skipped_gate", "error_message": "age_or_mileage_exceeded"},
                {"source_site": "hibid", "status": "skipped_gate", "error_message": "age_or_mileage_exceeded"},
                {"source_site": "govdeals", "status": "skipped_margin", "error_message": "margin_below_floor"},
            ]
        if table == "opportunities":
            return [
                {
                    "source_site": "govdeals",
                    "active": True,
                    "dos_score": 88.0,
                    "created_at": "2026-06-05T03:00:00+00:00",
                }
            ]
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
    )

    by_source = {item["source"]: item for item in report["source_summaries"]}
    assert report["overall_verdict"] == "accepted_flow_present"
    assert by_source["govdeals"]["classification"] == "accepted_flow_present"
    assert by_source["govdeals"]["active_opportunity_rows"] == 1
    assert by_source["govdeals"]["active_dos_score_buckets"] == {"80_plus": 1}
    assert by_source["govdeals"]["active_dos_score_min"] == 88.0
    assert by_source["govdeals"]["active_dos_score_max"] == 88.0
    assert by_source["govdeals"]["active_dos_score_avg"] == 88.0
    assert by_source["hibid"]["classification"] == "dirty_source_reject_only"
    assert by_source["hibid"]["dirty_rejection_rows"] == 2


def test_build_report_excludes_dirty_margin_and_ceiling_rows_from_business_dominance(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-hibid-dirty",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 3,
                        "received_at": "2026-06-05T19:00:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-hibid-dirty",
                        "source_site": "hibid",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor",
                        "listing_id": "old-clean-looking",
                        "listing_url": "https://hibid.com/lot/old-clean-looking/",
                        "created_at": "2026-06-05T19:01:00+00:00",
                    },
                    {
                        "run_id": "run-hibid-dirty",
                        "source_site": "hibid",
                        "status": "skipped_ceiling",
                        "error_message": "pricing_maturity_proxy",
                        "listing_id": "missing-vin",
                        "listing_url": "https://hibid.com/lot/missing-vin/",
                        "created_at": "2026-06-05T19:02:00+00:00",
                    },
                    {
                        "run_id": "run-hibid-dirty",
                        "source_site": "hibid",
                        "status": "skipped_proof",
                        "error_message": "source_quality_proof_record",
                        "created_at": "2026-06-05T19:03:00+00:00",
                    },
                ]
            if table == "sonar_listings":
                return [
                    {
                        "listing_id": "old-clean-looking",
                        "listing_url": "https://hibid.com/lot/old-clean-looking/",
                        "year": 2016,
                        "mileage": 36492,
                        "vin": "1FM5K7D80GGA00000",
                        "created_at": "2026-06-05T19:00:30+00:00",
                    },
                    {
                        "listing_id": "missing-vin",
                        "listing_url": "https://hibid.com/lot/missing-vin/",
                        "year": 2021,
                        "mileage": 40436,
                        "vin": None,
                        "created_at": "2026-06-05T19:00:31+00:00",
                    },
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T19:04:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-hibid-dirty",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 3,
                    "received_at": "2026-06-05T19:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-hibid-dirty",
                    "source_site": "hibid",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor",
                    "listing_id": "old-clean-looking",
                    "listing_url": "https://hibid.com/lot/old-clean-looking/",
                    "created_at": "2026-06-05T19:01:00+00:00",
                },
                {
                    "run_id": "run-hibid-dirty",
                    "source_site": "hibid",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy",
                    "listing_id": "missing-vin",
                    "listing_url": "https://hibid.com/lot/missing-vin/",
                    "created_at": "2026-06-05T19:02:00+00:00",
                },
                {
                    "run_id": "run-hibid-dirty",
                    "source_site": "hibid",
                    "status": "skipped_proof",
                    "error_message": "source_quality_proof_record",
                    "created_at": "2026-06-05T19:03:00+00:00",
                },
            ]
        if table == "sonar_listings":
            return [
                {
                    "listing_id": "old-clean-looking",
                    "listing_url": "https://hibid.com/lot/old-clean-looking/",
                    "year": 2016,
                    "mileage": 36492,
                    "vin": "1FM5K7D80GGA00000",
                    "created_at": "2026-06-05T19:00:30+00:00",
                },
                {
                    "listing_id": "missing-vin",
                    "listing_url": "https://hibid.com/lot/missing-vin/",
                    "year": 2021,
                    "mileage": 40436,
                    "vin": None,
                    "created_at": "2026-06-05T19:00:31+00:00",
                },
            ]
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 20, 0, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    source_summary = report["source_summaries"][0]
    run_summary = report["run_summaries"][0]

    assert source_summary["dirty_rejection_rows"] == 2
    assert source_summary["classification"] == "dirty_source_reject_only"
    assert run_summary["dirty_rejection_rows"] == 2
    assert run_summary["classification"] == "dirty_source_reject_only"


def test_build_report_uses_listing_url_match_when_delivery_and_sonar_ids_differ(monkeypatch):
    listing_url = "https://hibid.com/lot/production-dirty-row/"

    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-hibid-url-match",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-05T19:00:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-hibid-url-match",
                        "source_site": "hibid",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor",
                        "listing_id": "delivery-key",
                        "listing_url": listing_url,
                        "created_at": "2026-06-05T19:01:00+00:00",
                    }
                ]
            if table == "sonar_listings":
                return [
                    {
                        "listing_id": "some-other-current-row",
                        "listing_url": "https://hibid.com/lot/other/",
                        "year": 2025,
                        "mileage": 1000,
                        "vin": "1HGCM82633A004352",
                        "created_at": "2026-06-05T19:30:00+00:00",
                    }
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T19:04:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-hibid-url-match",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 1,
                    "received_at": "2026-06-05T19:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-hibid-url-match",
                    "source_site": "hibid",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor",
                    "listing_id": "delivery-key",
                    "listing_url": listing_url,
                    "created_at": "2026-06-05T19:01:00+00:00",
                }
            ]
        if table == "sonar_listings" and query_dict.get("listing_url") == f"eq.{listing_url}":
            return [
                {
                    "listing_id": "sonar-key",
                    "listing_url": listing_url,
                    "year": 2016,
                    "mileage": 36492,
                    "vin": "1FM5K7D80GGA00000",
                    "created_at": "2026-06-05T18:59:30+00:00",
                }
            ]
        if table == "sonar_listings":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 20, 0, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    source_summary = report["source_summaries"][0]
    run_summary = report["run_summaries"][0]

    assert source_summary["dirty_rejection_rows"] == 1
    assert source_summary["classification"] == "dirty_source_reject_only"
    assert run_summary["dirty_rejection_rows"] == 1
    assert run_summary["classification"] == "dirty_source_reject_only"


def test_build_report_does_not_treat_unmatched_margin_rows_as_clean_economics(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-hibid-unmatched",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-05T19:00:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-hibid-unmatched",
                        "source_site": "hibid",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor",
                        "listing_id": "unmatched-margin",
                        "listing_url": "https://hibid.com/lot/unmatched-margin/",
                        "created_at": "2026-06-05T19:01:00+00:00",
                    }
                ]
            if table == "sonar_listings":
                return [
                    {
                        "listing_id": "other-listing",
                        "listing_url": "https://hibid.com/lot/other/",
                        "year": 2025,
                        "mileage": 1000,
                        "vin": "1HGCM82633A004352",
                        "created_at": "2026-06-05T19:30:00+00:00",
                    }
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T19:04:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-hibid-unmatched",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 1,
                    "received_at": "2026-06-05T19:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-hibid-unmatched",
                    "source_site": "hibid",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor",
                    "listing_id": "unmatched-margin",
                    "listing_url": "https://hibid.com/lot/unmatched-margin/",
                    "created_at": "2026-06-05T19:01:00+00:00",
                }
            ]
        if table == "sonar_listings":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 20, 0, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    source_summary = report["source_summaries"][0]
    run_summary = report["run_summaries"][0]

    assert source_summary["listing_metadata_gap_rows"] == 1
    assert source_summary["classification"] == "listing_metadata_gap"
    assert run_summary["listing_metadata_gap_rows"] == 1
    assert run_summary["classification"] == "listing_metadata_gap"


def test_build_report_fetches_primary_delivery_listing_keys(monkeypatch):
    delivery_selects: list[str] = []

    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-keyed",
                        "source": "govdeals",
                        "status": "processed",
                        "item_count": 2,
                        "received_at": "2026-06-05T19:00:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-keyed",
                        "source_site": "govdeals",
                        "channel": "db_save",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor",
                        "listing_id": "keyed-listing",
                        "listing_url": "https://govdeals.example/asset/1",
                        "created_at": "2026-06-05T19:01:00+00:00",
                    }
                ]
            if table == "sonar_listings":
                return [
                    {
                        "listing_id": "keyed-listing",
                        "listing_url": "https://govdeals.example/asset/1",
                        "year": 2025,
                        "mileage": 38,
                        "vin": "1HGCM82633A004352",
                        "created_at": "2026-06-05T19:01:01+00:00",
                    }
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T19:02:00+00:00"}]
        if table == "ingest_delivery_log":
            delivery_selects.append(str(select or ""))
            return [
                {
                    "run_id": "run-keyed",
                    "source_site": "govdeals",
                    "channel": "db_save",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor",
                    "listing_id": "keyed-listing",
                    "listing_url": "https://govdeals.example/asset/1",
                    "created_at": "2026-06-05T19:01:00+00:00",
                }
            ]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-keyed",
                    "source": "govdeals",
                    "status": "processed",
                    "item_count": 2,
                    "received_at": "2026-06-05T19:00:00+00:00",
                }
            ]
        if table == "sonar_listings":
            return [
                {
                    "listing_id": "keyed-listing",
                    "listing_url": "https://govdeals.example/asset/1",
                    "year": 2025,
                    "mileage": 38,
                    "vin": "1HGCM82633A004352",
                    "created_at": "2026-06-05T19:01:01+00:00",
                }
            ]
        if table == "delivery_log":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 20, 0, tzinfo=timezone.utc),
        run_detail_source="govdeals",
    )

    assert any("listing_id" in select and "listing_url" in select for select in delivery_selects)
    assert report["source_summaries"][0]["listing_metadata_gap_rows"] == 0
    assert report["source_summaries"][0]["classification"] == "economic_reject_dominant"
    assert report["run_summaries"][0]["classification"] == "economic_reject_dominant"


def test_build_report_does_not_call_inactive_accepted_rows_current_yield(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-old-accepted",
                    "source": "publicsurplus",
                    "status": "processed",
                    "item_count": 2,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-old-accepted",
                    "source_site": "publicsurplus",
                    "channel": "db_save",
                    "status": "saved_supabase",
                    "created_at": "2026-06-05T04:01:00+00:00",
                }
            ]
        if table == "opportunities":
            return [
                {
                    "source_site": "publicsurplus",
                    "source_run_id": "run-old-accepted",
                    "active": False,
                    "dos_score": 92.0,
                    "created_at": "2026-06-05T04:02:00+00:00",
                }
            ]
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
    )

    assert report["overall_verdict"] == "inactive_accepted_flow_only"
    assert report["source_summaries"][0]["classification"] == "inactive_accepted_flow_only"
    assert report["source_summaries"][0]["opportunity_rows"] == 1
    assert report["source_summaries"][0]["active_opportunity_rows"] == 0


def test_build_report_explains_inactive_accepted_lifecycle_reason(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-quarantined",
                    "source": "publicsurplus",
                    "status": "processed",
                    "item_count": 2,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-quarantined",
                    "source_site": "publicsurplus",
                    "channel": "db_save",
                    "status": "saved_supabase",
                    "created_at": "2026-06-05T04:01:00+00:00",
                }
            ]
        if table == "opportunities":
            return [
                {
                    "source_site": "publicsurplus",
                    "source_run_id": "run-quarantined",
                    "active": False,
                    "step_status": "q_no_cond_ev",
                    "dos_score": 92.0,
                    "created_at": "2026-06-05T04:02:00+00:00",
                },
                {
                    "source_site": "publicsurplus",
                    "source_run_id": "run-quarantined",
                    "active": False,
                    "step_status": "q_no_cond_ev",
                    "dos_score": 88.0,
                    "created_at": "2026-06-05T04:03:00+00:00",
                },
            ]
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        run_detail_source="publicsurplus",
    )

    source_summary = report["source_summaries"][0]
    run_summary = report["run_summaries"][0]

    assert source_summary["classification"] == "inactive_accepted_flow_only"
    assert source_summary["inactive_opportunity_lifecycle_counts"] == {"q_no_cond_ev": 2}
    assert run_summary["classification"] == "inactive_accepted_flow_only"
    assert run_summary["inactive_opportunity_lifecycle_counts"] == {"q_no_cond_ev": 2}


def test_build_report_selects_only_available_live_columns(monkeypatch):
    queries_by_table = {}

    def fake_fetch(base_url, service_role_key, table, query):
        queries_by_table.setdefault(table, []).append(dict(query))
        select = dict(query).get("select")
        if select and "actor_name" in select:
            raise AssertionError("actor_name should not be selected when live columns do not expose it")
        if table == "webhook_log" and select == "*":
            return [{"run_id": "run-1", "source": "govdeals", "status": "processed", "received_at": "2026-06-05T04:00:00+00:00"}]
        if table == "ingest_delivery_log" and select == "*":
            return [{"run_id": "run-1", "source_site": "govdeals", "status": "skipped_margin", "created_at": "2026-06-05T04:01:00+00:00"}]
        if table == "opportunities" and select == "*":
            return [{"source_site": "govdeals", "is_active": True, "score": 86.0, "created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [{"run_id": "run-1", "source": "govdeals", "status": "processed", "received_at": "2026-06-05T04:00:00+00:00"}]
        if table == "ingest_delivery_log":
            return [{"run_id": "run-1", "source_site": "govdeals", "status": "skipped_margin", "created_at": "2026-06-05T04:01:00+00:00"}]
        if table == "opportunities":
            return [{"source_site": "govdeals", "is_active": True, "score": 86.0, "created_at": "2026-06-05T04:02:00+00:00"}]
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
    )

    assert report["overall_verdict"] == "accepted_flow_present"
    assert "actor_name" not in queries_by_table["webhook_log"][1]["select"]
    assert "is_active" in queries_by_table["opportunities"][1]["select"]


def test_build_report_maps_actor_id_to_source_for_delivery_rows(monkeypatch, tmp_path):
    deployment = tmp_path / "deployment.json"
    deployment.write_text(
        '{"actors": {"ds-govdeals": {"id": "actor-govdeals"}}}',
        encoding="utf-8",
    )

    def fake_fetch(base_url, service_role_key, table, query):
        select = dict(query).get("select")
        if table == "webhook_log" and select == "*":
            return [{"run_id": "run-1", "actor_id": "actor-govdeals", "source": "apify", "status": "processed", "received_at": "2026-06-05T04:00:00+00:00"}]
        if table == "ingest_delivery_log" and select == "*":
            return [{"run_id": "run-1", "status": "skipped_margin", "created_at": "2026-06-05T04:01:00+00:00"}]
        if table == "opportunities" and select == "*":
            return [{"created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [{"run_id": "run-1", "actor_id": "actor-govdeals", "source": "apify", "status": "processed", "received_at": "2026-06-05T04:00:00+00:00"}]
        if table == "ingest_delivery_log":
            return [{"run_id": "run-1", "status": "skipped_margin", "created_at": "2026-06-05T04:01:00+00:00"}]
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        deployment_path=deployment,
    )

    assert report["source_summaries"][0]["source"] == "govdeals"
    assert report["source_summaries"][0]["delivery_rows"] == 1


def test_build_report_includes_sanitized_run_summaries_for_requested_source(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log" and dict(query).get("select") == "*":
            return [
                {
                    "run_id": "run-hibid-1",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 3,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log" and dict(query).get("select") == "*":
            return [
                {
                    "run_id": "run-hibid-1",
                    "source_site": "hibid",
                    "status": "skipped_gate",
                    "error_message": "age_or_mileage_exceeded",
                    "created_at": "2026-06-05T04:01:00+00:00",
                }
            ]
        if table == "opportunities" and dict(query).get("select") == "*":
            return [{"created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-hibid-1",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 3,
                    "received_at": "2026-06-05T04:00:00+00:00",
                },
                {
                    "run_id": "run-govdeals-1",
                    "source": "govdeals",
                    "status": "processed",
                    "item_count": 7,
                    "received_at": "2026-06-05T03:00:00+00:00",
                },
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-hibid-1",
                    "source_site": "hibid",
                    "status": "skipped_gate",
                    "error_message": "age_or_mileage_exceeded",
                    "created_at": "2026-06-05T04:01:00+00:00",
                },
                {
                    "run_id": "run-govdeals-1",
                    "source_site": "govdeals",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor: bid=27000",
                    "created_at": "2026-06-05T03:01:00+00:00",
                },
            ]
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    assert report["run_detail_source"] == "hibid"
    assert report["run_summaries"] == [
        {
            "run_id": "run-hibid-1",
            "source": "hibid",
            "webhook_rows": 1,
            "webhook_processed_rows": 1,
            "webhook_item_count_total": 3,
            "delivery_rows": 1,
            "status_counts": {"skipped_gate": 1},
            "reason_counts": {"age_or_mileage_exceeded": 1},
            "opportunity_rows": 0,
            "active_opportunity_rows": 0,
            "active_dos80_rows": 0,
            "inactive_opportunity_lifecycle_counts": {},
            "dirty_rejection_rows": 1,
            "dirty_rejection_reason_counts": {"age_or_mileage_exceeded": 1},
            "listing_metadata_gap_rows": 0,
            "listing_metadata_gap_status_counts": {},
            "listing_metadata_gap_reason_counts": {},
            "classification": "dirty_source_reject_only",
        }
    ]
    run_output = str(report["run_summaries"]).lower()
    assert "title" not in run_output
    assert "vin" not in run_output
    assert "url" not in run_output


def test_source_summary_exposes_latest_run_truth_when_lookback_has_stale_blockers(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        select = dict(query).get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-new-margin",
                        "source": "jjkane",
                        "status": "processed",
                        "item_count": 4,
                        "received_at": "2026-06-06T11:05:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-new-margin",
                        "source_site": "jjkane",
                        "channel": "db_save",
                        "status": "skipped_margin",
                        "error_message": "margin_below_floor",
                        "listing_id": "new-margin",
                        "created_at": "2026-06-06T11:05:01+00:00",
                    }
                ]
            if table == "sonar_listings":
                return [
                    {
                        "listing_id": "new-margin",
                        "year": 2023,
                        "mileage": 27021,
                        "vin": "3C4NJDBN6PT520834",
                        "created_at": "2026-06-06T11:05:01+00:00",
                    }
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-06T11:05:02+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-new-margin",
                    "source": "jjkane",
                    "status": "processed",
                    "item_count": 4,
                    "received_at": "2026-06-06T11:05:00+00:00",
                },
                {
                    "run_id": "run-old-proxy",
                    "source": "jjkane",
                    "status": "processed",
                    "item_count": 4,
                    "received_at": "2026-06-06T10:45:00+00:00",
                },
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-new-margin",
                    "source_site": "jjkane",
                    "channel": "db_save",
                    "status": "skipped_margin",
                    "error_message": "margin_below_floor",
                    "listing_id": "new-margin",
                    "created_at": "2026-06-06T11:05:01+00:00",
                },
                {
                    "run_id": "run-old-proxy",
                    "source_site": "jjkane",
                    "channel": "db_save",
                    "status": "skipped_ceiling",
                    "error_message": "pricing_maturity_proxy",
                    "listing_id": "old-proxy",
                    "created_at": "2026-06-06T10:45:01+00:00",
                },
            ]
        if table == "sonar_listings":
            return [
                {
                    "listing_id": "new-margin",
                    "year": 2023,
                    "mileage": 27021,
                    "vin": "3C4NJDBN6PT520834",
                    "created_at": "2026-06-06T11:05:01+00:00",
                },
                {
                    "listing_id": "old-proxy",
                    "year": 2023,
                    "mileage": 27021,
                    "vin": "3C4NJDBN6PT520834",
                    "created_at": "2026-06-06T10:45:01+00:00",
                },
            ]
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=2,
        limit=100,
        now=datetime(2026, 6, 6, 11, 15, tzinfo=timezone.utc),
        run_detail_source="jjkane",
    )

    source_summary = report["source_summaries"][0]

    assert source_summary["reason_counts"] == {
        "margin_below_floor": 1,
        "pricing_maturity_proxy": 1,
    }
    assert source_summary["latest_run_id"] == "run-new-margin"
    assert source_summary["latest_run_classification"] == "economic_reject_dominant"
    assert source_summary["latest_run_reason_counts"] == {"margin_below_floor": 1}
    assert "pricing_maturity_proxy" not in source_summary["latest_run_reason_counts"]


def test_run_level_positive_item_gap_controls_overall_verdict(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if dict(query).get("select") == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-gap",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 182,
                        "received_at": "2026-06-05T04:00:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-rejected",
                        "source_site": "hibid",
                        "status": "skipped_gate",
                        "error_message": "age_or_mileage_exceeded",
                        "created_at": "2026-06-05T04:01:00+00:00",
                    }
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-gap",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 182,
                    "received_at": "2026-06-05T04:00:00+00:00",
                },
                {
                    "run_id": "run-rejected",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 1,
                    "received_at": "2026-06-05T03:00:00+00:00",
                },
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-rejected",
                    "source_site": "hibid",
                    "status": "skipped_gate",
                    "error_message": "age_or_mileage_exceeded",
                    "created_at": "2026-06-05T04:01:00+00:00",
                }
            ]
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    assert report["overall_verdict"] == "diagnostic_gap"
    assert report["run_classification_counts"]["webhook_without_delivery_gap"] == 1
    by_run = {item["run_id"]: item for item in report["run_summaries"]}
    assert by_run["run-gap"]["classification"] == "webhook_without_delivery_gap"
    assert by_run["run-rejected"]["classification"] == "dirty_source_reject_only"


def test_delivery_log_fallback_prevents_false_run_gap(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        select = dict(query).get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-legacy",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 182,
                        "received_at": "2026-06-05T04:00:00+00:00",
                    }
                ]
            if table in {"ingest_delivery_log", "delivery_log"}:
                return [
                    {
                        "run_id": "run-legacy",
                        "source_site": "hibid",
                        "channel": "db_save",
                        "status": "skipped_gate",
                        "error_message": "age_or_mileage_exceeded",
                        "created_at": "2026-06-05T04:01:00+00:00",
                    }
                ]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-legacy",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 182,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return []
        if table == "delivery_log":
            return [
                {
                    "run_id": "run-legacy",
                    "source_site": "hibid",
                    "channel": "db_save",
                    "status": "skipped_gate",
                    "error_message": "age_or_mileage_exceeded",
                    "created_at": "2026-06-05T04:01:00+00:00",
                }
            ]
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    assert report["overall_verdict"] == "no_recent_accepted_source_yield"
    assert "webhook_without_delivery_gap" not in report.get("run_classification_counts", {})
    assert report["source_summaries"][0]["delivery_rows"] == 1
    assert report["source_summaries"][0]["channel_counts"] == {"db_save": 1}
    assert report["run_summaries"][0]["classification"] == "dirty_source_reject_only"


def test_delivery_log_fallback_queries_candidate_run_ids(monkeypatch):
    def legacy_row():
        return {
            "run_id": "run-legacy",
            "source_site": "hibid",
            "channel": "db_save",
            "status": "skipped_gate",
            "error_message": "age_or_mileage_exceeded",
            "created_at": "2026-06-05T04:01:00+00:00",
        }

    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-legacy",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 182,
                        "received_at": "2026-06-05T04:00:00+00:00",
                    }
                ]
            if table in {"ingest_delivery_log", "delivery_log"}:
                return [legacy_row()]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-legacy",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 182,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return []
        if table == "delivery_log" and query_dict.get("run_id") == "eq.run-legacy":
            return [legacy_row()]
        if table == "delivery_log":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    assert report["delivery_log_fallback_rows"] == 1
    assert report["overall_verdict"] == "no_recent_accepted_source_yield"
    assert report["run_summaries"][0]["delivery_rows"] == 1
    assert report["run_summaries"][0]["classification"] == "dirty_source_reject_only"


def test_ingest_delivery_log_queries_candidate_run_ids(monkeypatch):
    def primary_row():
        return {
            "run_id": "run-primary",
            "source_site": "hibid",
            "channel": "db_save",
            "status": "skipped_gate",
            "error_message": "age_or_mileage_exceeded",
            "created_at": "2026-06-05T04:01:00+00:00",
        }

    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-primary",
                        "source": "hibid",
                        "status": "processed",
                        "item_count": 182,
                        "received_at": "2026-06-05T04:00:00+00:00",
                    }
                ]
            if table in {"ingest_delivery_log", "delivery_log"}:
                return [primary_row()]
            if table == "opportunities":
                return [{"created_at": "2026-06-05T04:02:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-primary",
                    "source": "hibid",
                    "status": "processed",
                    "item_count": 182,
                    "received_at": "2026-06-05T04:00:00+00:00",
                }
            ]
        if table == "ingest_delivery_log" and query_dict.get("run_id") == "eq.run-primary":
            return [primary_row()]
        if table == "ingest_delivery_log":
            return []
        if table == "delivery_log":
            return []
        if table == "opportunities":
            return []
        raise AssertionError(table)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=24,
        limit=100,
        now=datetime(2026, 6, 5, 4, 30, tzinfo=timezone.utc),
        run_detail_source="hibid",
    )

    assert report["delivery_log_fallback_rows"] == 0
    assert report["overall_verdict"] == "no_recent_accepted_source_yield"
    assert "webhook_without_delivery_gap" not in report.get("run_classification_counts", {})
    assert report["source_summaries"][0]["delivery_rows"] == 1
    assert report["run_summaries"][0]["classification"] == "dirty_source_reject_only"


def test_build_report_uses_apify_source_quality_proof_for_proof_only_runs(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-jjkane-proof",
                        "source": "jjkane",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-06T04:01:00+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-jjkane-proof",
                        "source_site": "jjkane",
                        "status": "skipped_proof",
                        "error_message": "source_quality_proof_record",
                        "created_at": "2026-06-06T04:01:10+00:00",
                    }
                ]
            if table == "sonar_listings":
                return []
            if table == "opportunities":
                return [{"created_at": "2026-06-06T04:02:00+00:00"}]
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-jjkane-proof",
                    "source": "jjkane",
                    "status": "processed",
                    "item_count": 1,
                    "received_at": "2026-06-06T04:01:00+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-jjkane-proof",
                    "source_site": "jjkane",
                    "status": "skipped_proof",
                    "error_message": "source_quality_proof_record",
                    "created_at": "2026-06-06T04:01:10+00:00",
                }
            ]
        if table in {"delivery_log", "sonar_listings", "opportunities"}:
            return []
        raise AssertionError(table)

    def fake_apify_proof(run_id, token):
        assert run_id == "run-jjkane-proof"
        assert token == "apify-token"
        return {
            "found_rows_total": 1365,
            "prefilter_passed_rows_total": 0,
            "pushed_rows_total": 0,
            "rows_excluded_age_mileage_prefilter": 1269,
            "rows_excluded_policy_prefilter": 79,
            "rows_excluded_zero_pricing_signal": 15,
        }

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)
    monkeypatch.setattr(report_source_yield_proof, "_fetch_apify_source_quality_proof", fake_apify_proof)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=8,
        limit=100,
        now=datetime(2026, 6, 6, 4, 5, tzinfo=timezone.utc),
        run_detail_source="jjkane",
        apify_token="apify-token",
    )

    source_summary = report["source_summaries"][0]
    run_summary = report["run_summaries"][0]

    assert source_summary["classification"] == "source_quality_reject_dominant"
    assert source_summary["source_quality_found_rows_total"] == 1365
    assert source_summary["source_quality_pushed_rows_total"] == 0
    assert source_summary["source_quality_exclusion_counts"]["rows_excluded_zero_pricing_signal"] == 15
    assert run_summary["classification"] == "source_quality_reject_dominant"
    assert run_summary["source_quality_exclusion_counts"]["rows_excluded_age_mileage_prefilter"] == 1269


def test_source_summary_separates_aggregate_and_latest_source_quality_proof(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-publicsurplus-old",
                        "source": "publicsurplus",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-06T10:00:00+00:00",
                    },
                    {
                        "run_id": "run-publicsurplus-new",
                        "source": "publicsurplus",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-06T12:00:00+00:00",
                    },
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-publicsurplus-old",
                        "source_site": "publicsurplus",
                        "status": "skipped_proof",
                        "error_message": "source_quality_proof_record",
                        "created_at": "2026-06-06T10:00:10+00:00",
                    },
                    {
                        "run_id": "run-publicsurplus-new",
                        "source_site": "publicsurplus",
                        "status": "skipped_proof",
                        "error_message": "source_quality_proof_record",
                        "created_at": "2026-06-06T12:00:10+00:00",
                    },
                ]
            if table in {"sonar_listings", "opportunities"}:
                return []
        if table in {"webhook_log", "ingest_delivery_log"}:
            return fake_fetch(base_url, service_role_key, table, [("select", "*")])
        if table in {"delivery_log", "sonar_listings", "opportunities"}:
            return []
        raise AssertionError(table)

    def fake_apify_proof(run_id, token):
        assert token == "apify-token"
        if run_id == "run-publicsurplus-old":
            return {
                "source": "publicsurplus",
                "found_rows_total": 159,
                "prefilter_passed_rows_total": 0,
                "pushed_rows_total": 0,
                "rows_excluded_unaccounted_after_prefilter": 0,
            }
        if run_id == "run-publicsurplus-new":
            return {
                "source": "publicsurplus",
                "found_rows_total": 318,
                "prefilter_passed_rows_total": 0,
                "pushed_rows_total": 0,
                "rows_excluded_age_mileage_prefilter": 91,
                "rows_excluded_bid_range": 107,
                "rows_excluded_non_vehicle": 70,
                "rows_excluded_out_of_scope": 14,
                "rows_excluded_policy_prefilter": 2,
                "rows_excluded_rust_state": 34,
                "rows_excluded_unaccounted_after_prefilter": 0,
            }
        raise AssertionError(run_id)

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)
    monkeypatch.setattr(report_source_yield_proof, "_fetch_apify_source_quality_proof", fake_apify_proof)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=6,
        limit=100,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        apify_token="apify-token",
    )

    source_summary = report["source_summaries"][0]

    assert source_summary["source_quality_proof_run_count"] == 2
    assert source_summary["source_quality_found_rows_total"] == 477
    assert source_summary["source_quality_visible_exclusion_rows_total"] == 318
    assert source_summary["latest_run_id"] == "run-publicsurplus-new"
    assert source_summary["latest_run_source_quality_found_rows_total"] == 318
    assert source_summary["latest_run_source_quality_visible_exclusion_rows_total"] == 318
    assert source_summary["latest_run_source_quality_exclusion_counts"] == {
        "rows_excluded_age_mileage_prefilter": 91,
        "rows_excluded_bid_range": 107,
        "rows_excluded_non_vehicle": 70,
        "rows_excluded_out_of_scope": 14,
        "rows_excluded_policy_prefilter": 2,
        "rows_excluded_rust_state": 34,
        "rows_excluded_unaccounted_after_prefilter": 0,
    }


def test_source_quality_visible_exclusion_total_ignores_diagnostic_subcounters(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-govdeals-proof",
                        "source": "govdeals",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-06T12:00:00+00:00",
                    },
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-govdeals-proof",
                        "source_site": "govdeals",
                        "status": "skipped_proof",
                        "error_message": "source_quality_proof_record",
                        "created_at": "2026-06-06T12:00:10+00:00",
                    },
                ]
            if table in {"sonar_listings", "opportunities"}:
                return []
        if table in {"webhook_log", "ingest_delivery_log"}:
            return fake_fetch(base_url, service_role_key, table, [("select", "*")])
        if table in {"delivery_log", "sonar_listings", "opportunities"}:
            return []
        raise AssertionError(table)

    def fake_apify_proof(run_id, token):
        assert run_id == "run-govdeals-proof"
        assert token == "apify-token"
        return {
            "source_site": "govdeals",
            "found_rows_total": 5,
            "prefilter_passed_rows_total": 5,
            "pushed_rows_total": 1,
            "rows_excluded_missing_required_data": 2,
            "rows_excluded_missing_vin": 2,
            "rows_excluded_missing_mileage": 1,
            "rows_excluded_after_detail_attempt": 1,
            "rows_excluded_without_detail_attempt": 1,
            "rows_excluded_age_mileage_after_detail": 1,
            "rows_excluded_policy_after_detail": 1,
            "rows_excluded_unaccounted_after_prefilter": 0,
        }

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)
    monkeypatch.setattr(report_source_yield_proof, "_fetch_apify_source_quality_proof", fake_apify_proof)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=6,
        limit=100,
        now=datetime(2026, 6, 6, 12, 30, tzinfo=timezone.utc),
        apify_token="apify-token",
    )

    source_summary = report["source_summaries"][0]

    assert source_summary["source_quality_visible_exclusion_rows_total"] == 4
    assert source_summary["latest_run_source_quality_visible_exclusion_rows_total"] == 4
    assert source_summary["latest_run_source_quality_exclusion_counts"]["rows_excluded_missing_vin"] == 2


def test_build_report_surfaces_sanitized_source_quality_rejection_reasons(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        query_dict = dict(query)
        select = query_dict.get("select")
        if select == "*":
            if table == "webhook_log":
                return [
                    {
                        "run_id": "run-proxibid-proof",
                        "source": "proxibid",
                        "status": "processed",
                        "item_count": 1,
                        "received_at": "2026-06-06T07:12:40+00:00",
                    }
                ]
            if table == "ingest_delivery_log":
                return [
                    {
                        "run_id": "run-proxibid-proof",
                        "source_site": "proxibid",
                        "status": "skipped_proof",
                        "error_message": "source_quality_proof_record",
                        "created_at": "2026-06-06T07:12:45+00:00",
                    }
                ]
            if table in {"sonar_listings", "opportunities"}:
                return []
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-proxibid-proof",
                    "source": "proxibid",
                    "status": "processed",
                    "item_count": 1,
                    "received_at": "2026-06-06T07:12:40+00:00",
                }
            ]
        if table == "ingest_delivery_log":
            return [
                {
                    "run_id": "run-proxibid-proof",
                    "source_site": "proxibid",
                    "status": "skipped_proof",
                    "error_message": "source_quality_proof_record",
                    "created_at": "2026-06-06T07:12:45+00:00",
                }
            ]
        if table in {"delivery_log", "sonar_listings", "opportunities"}:
            return []
        raise AssertionError(table)

    def fake_apify_proof(run_id, token):
        assert run_id == "run-proxibid-proof"
        assert token == "apify-token"
        return {
            "found_rows_total": 1294,
            "prefilter_passed_rows_total": 24,
            "pushed_rows_total": 0,
            "rows_excluded_age_mileage_prefilter": 715,
            "rejection_reasons": {
                "condition_reject": 21,
                "mileage_over_50k": 3,
            },
        }

    monkeypatch.setattr(report_source_yield_proof, "_fetch_postgrest_rows", fake_fetch)
    monkeypatch.setattr(report_source_yield_proof, "_fetch_apify_source_quality_proof", fake_apify_proof)

    report = report_source_yield_proof.build_source_yield_report(
        "https://example.supabase.co/rest/v1",
        "service-key",
        lookback_hours=1,
        limit=100,
        now=datetime(2026, 6, 6, 7, 15, tzinfo=timezone.utc),
        run_detail_source="proxibid",
        apify_token="apify-token",
    )

    source_summary = report["source_summaries"][0]
    run_summary = report["run_summaries"][0]

    assert source_summary["source_quality_prefilter_passed_rows_total"] == 24
    assert source_summary["source_quality_pushed_rows_total"] == 0
    assert source_summary["source_quality_rejection_reason_counts"] == {
        "condition_reject": 21,
        "mileage_over_50k": 3,
    }
    assert run_summary["source_quality_rejection_reason_counts"]["condition_reject"] == 21
