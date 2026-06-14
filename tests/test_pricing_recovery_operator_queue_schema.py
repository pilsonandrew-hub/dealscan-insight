from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260614_pricing_recovery_operator_queue.sql"


def test_pricing_recovery_queue_schema_exists_with_safe_columns():
    sql = MIGRATION.read_text()

    assert "create table if not exists public.pricing_recovery_requests" in sql.lower()
    assert "create table if not exists public.pricing_recovery_request_events" in sql.lower()
    assert "group_key text not null unique" in sql.lower()
    assert "queue_status text not null" in sql.lower()
    assert "latest_proof_run_id text" in sql.lower()
    assert "latest_proof_head_sha text" in sql.lower()
    forbidden = ["vin ", "listing_url", "title ", "description ", "raw_payload", "token", "secret"]
    lowered = sql.lower()
    for word in forbidden:
        assert word not in lowered


def test_pricing_recovery_queue_schema_has_status_constraints_and_audit_indexes():
    sql = MIGRATION.read_text().lower()

    assert "check (queue_status in (" in sql
    assert "'open'" in sql
    assert "'evidence_requested'" in sql
    assert "'preview_ready'" in sql
    assert "'applied'" in sql
    assert "check (status in (" in sql
    assert "blocked_no_internal_comp_evidence" in sql
    assert "create index if not exists idx_pricing_recovery_requests_queue_status" in sql
    assert "create index if not exists idx_pricing_recovery_request_events_request_id" in sql
