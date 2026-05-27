from backend.ingest.audit_state import (
    AUDIT_FALLBACK_MARKER,
    CriticalAuditWriteError,
    attach_audit_state,
    audit_fallbacks,
    format_audit_failure,
    format_ingest_run_summary,
    increment_reason_counter,
    merge_audit_error_message,
    record_audit_fallback,
)


def test_audit_fallbacks_dedupes_truthy_labels_in_order():
    assert audit_fallbacks({"fallbacks": ["direct_pg", "", "direct_pg", "replay"]}) == [
        "direct_pg",
        "replay",
    ]


def test_record_audit_fallback_is_idempotent_and_none_safe():
    record_audit_fallback(None, "direct_pg")
    state = {}
    record_audit_fallback(state, "direct_pg")
    record_audit_fallback(state, "direct_pg")
    assert state == {"fallbacks": ["direct_pg"]}


def test_merge_audit_error_message_appends_once():
    assert merge_audit_error_message(None, ["direct_pg"]) == "audit_fallbacks=direct_pg"
    assert merge_audit_error_message("primary failed", ["direct_pg"]) == (
        "primary failed; audit_fallbacks=direct_pg"
    )
    assert merge_audit_error_message(
        "primary failed; audit_fallbacks=direct_pg", ["direct_pg"]
    ) == "primary failed; audit_fallbacks=direct_pg"
    assert merge_audit_error_message("primary failed", []) == "primary failed"


def test_format_ingest_run_summary_preserves_funnel_shape():
    assert format_ingest_run_summary(
        dataset_item_count=10,
        evaluated=9,
        saved_count=8,
        duplicate_existing=1,
        failed_save_count=2,
        sonar_write_failures=3,
        skipped=4,
        duplicate_count=5,
        notion_sync_count=6,
        hot_deals_count=7,
    ) == "funnel=items:10,evaluated:9,saved:8,existing:1,failed:2,sonar_write_failures:3,skipped:4,duplicates:5,notion_sync:6,hot_deals:7,alert_blocked:0"


def test_format_ingest_run_summary_includes_blocked_alert_reasons_by_count():
    assert format_ingest_run_summary(
        dataset_item_count=10,
        evaluated=9,
        saved_count=8,
        duplicate_existing=1,
        failed_save_count=2,
        sonar_write_failures=3,
        skipped=4,
        duplicate_count=5,
        notion_sync_count=6,
        hot_deals_count=7,
        alert_blocked_count=4,
        alert_blocked_reasons={"vin_unverified": 2, "mileage_missing": 4},
    ) == (
        "funnel=items:10,evaluated:9,saved:8,existing:1,failed:2,"
        "sonar_write_failures:3,skipped:4,duplicates:5,notion_sync:6,"
        "hot_deals:7,alert_blocked:4,"
        "alert_blocked_reasons:mileage_missing:4,vin_unverified:2"
    )


def test_attach_audit_state_marks_ok_or_fallback():
    response = {}
    attach_audit_state(response, None)
    assert response == {"audit_status": "ok"}

    response = {}
    attach_audit_state(response, {"fallbacks": ["direct_pg"]})
    assert response == {"audit_status": "fallback", "audit_fallbacks": ["direct_pg"]}


def test_format_audit_failure_includes_primary_when_present():
    assert format_audit_failure(
        surface="webhook_log",
        operation="insert",
        primary_error=RuntimeError("supabase down"),
        fallback_error=RuntimeError("pg down"),
    ) == "critical webhook_log insert failed via Supabase and direct PG fallback: supabase=supabase down; direct_pg=pg down"
    assert format_audit_failure(
        surface="webhook_log",
        operation="insert",
        primary_error=None,
        fallback_error=RuntimeError("pg down"),
    ) == "critical webhook_log insert failed via direct PG fallback: direct_pg=pg down"


def test_increment_reason_counter_adds_and_increments_reason():
    counter = {}
    increment_reason_counter(counter, "gate:rust_state")
    increment_reason_counter(counter, "gate:rust_state")
    increment_reason_counter(counter, "save_exception")
    assert counter == {"gate:rust_state": 2, "save_exception": 1}


def test_critical_audit_write_error_is_runtime_error():
    assert issubclass(CriticalAuditWriteError, RuntimeError)


def test_audit_fallback_marker_constant_matches_wire_format():
    assert AUDIT_FALLBACK_MARKER == "audit_fallbacks="
