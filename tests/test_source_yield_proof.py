import importlib.util
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


def test_build_report_marks_webhook_delivery_gap(monkeypatch):
    def fake_fetch(base_url, service_role_key, table, query):
        if table == "webhook_log":
            return [
                {
                    "run_id": "run-1",
                    "actor_name": "ds-govdeals",
                    "status": "processed",
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
    assert by_source["hibid"]["classification"] == "source_quality_reject_dominant"


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
