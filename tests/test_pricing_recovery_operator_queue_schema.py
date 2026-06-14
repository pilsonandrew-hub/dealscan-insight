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
    assert "notify pgrst, 'reload schema'" in sql
    assert "create or replace function public.set_pricing_recovery_requests_updated_at()" in sql
    assert "before update on public.pricing_recovery_requests" in sql


def test_pricing_recovery_queue_schema_locks_tables_to_service_role():
    sql = MIGRATION.read_text().lower()

    assert "alter table public.pricing_recovery_requests enable row level security" in sql
    assert "alter table public.pricing_recovery_request_events enable row level security" in sql
    assert "create policy service_role_all_pricing_recovery_requests" in sql
    assert "on public.pricing_recovery_requests" in sql
    assert "create policy service_role_all_pricing_recovery_request_events" in sql
    assert "on public.pricing_recovery_request_events" in sql
    assert sql.count("to service_role") >= 2
    assert sql.count("using (true)") >= 2
    assert sql.count("with check (true)") >= 2


def test_pricing_recovery_queue_schema_has_atomic_sync_rpc():
    sql = MIGRATION.read_text().lower()

    assert "create or replace function public.sync_pricing_recovery_request(" in sql
    assert "request_payload jsonb" in sql
    assert "event_payload jsonb" in sql
    assert "returns jsonb" in sql
    assert "insert into public.pricing_recovery_requests" in sql
    assert "on conflict (group_key) do update set" in sql
    assert "insert into public.pricing_recovery_request_events" in sql
    assert "request_id" in sql
    assert "grant execute on function public.sync_pricing_recovery_request(jsonb, jsonb) to service_role" in sql


def test_pricing_recovery_queue_schema_has_service_role_lookup_rpc():
    sql = MIGRATION.read_text().lower()

    assert "create or replace function public.get_pricing_recovery_request_by_group_key(" in sql
    assert "request_group_key text" in sql
    assert "from public.pricing_recovery_requests" in sql
    assert "where request_rows.group_key = request_group_key" in sql
    assert "jsonb_build_object(" in sql
    assert "'queue_status', request_rows.queue_status" in sql
    assert "select *\n  into saved_request\n  from public.pricing_recovery_requests request_rows" not in sql
    assert "raise exception 'get_pricing_recovery_request_by_group_key requires service_role'" in sql
    assert "grant execute on function public.get_pricing_recovery_request_by_group_key(text) to service_role" in sql
