"""Pure ingest audit-state formatting helpers."""

from __future__ import annotations

from typing import Any, Optional

AUDIT_FALLBACK_MARKER = "audit_fallbacks="



def increment_reason_counter(counter: dict[str, int], reason: str) -> None:
    counter[reason] = counter.get(reason, 0) + 1


def audit_fallbacks(audit_state: Optional[dict[str, Any]]) -> list[str]:
    fallbacks = (audit_state or {}).get("fallbacks") or []
    deduped: list[str] = []
    for fallback in fallbacks:
        if fallback and fallback not in deduped:
            deduped.append(str(fallback))
    return deduped


def record_audit_fallback(audit_state: Optional[dict[str, Any]], fallback_label: str) -> None:
    if audit_state is None:
        return
    fallbacks = audit_state.setdefault("fallbacks", [])
    if fallback_label not in fallbacks:
        fallbacks.append(fallback_label)


def merge_audit_error_message(
    error_message: Optional[str],
    fallback_labels: list[str],
    *,
    marker_prefix: str = AUDIT_FALLBACK_MARKER,
) -> Optional[str]:
    labels = [label for label in fallback_labels if label]
    if not labels:
        return error_message
    marker = f"{marker_prefix}{','.join(labels)}"
    if not error_message:
        return marker
    if marker in error_message:
        return error_message
    return f"{error_message}; {marker}"


def format_ingest_run_summary(
    *,
    dataset_item_count: int,
    evaluated: int,
    saved_count: int,
    duplicate_existing: int,
    failed_save_count: int,
    sonar_write_failures: int = 0,
    skipped: int,
    duplicate_count: int,
    notion_sync_count: int,
    hot_deals_count: int,
) -> str:
    return (
        "funnel="
        f"items:{dataset_item_count},"
        f"evaluated:{evaluated},"
        f"saved:{saved_count},"
        f"existing:{duplicate_existing},"
        f"failed:{failed_save_count},"
        f"sonar_write_failures:{sonar_write_failures},"
        f"skipped:{skipped},"
        f"duplicates:{duplicate_count},"
        f"notion_sync:{notion_sync_count},"
        f"hot_deals:{hot_deals_count}"
    )


def attach_audit_state(response: dict[str, Any], audit_state: Optional[dict[str, Any]]) -> None:
    fallbacks = audit_fallbacks(audit_state)
    response["audit_status"] = "fallback" if fallbacks else "ok"
    if fallbacks:
        response["audit_fallbacks"] = fallbacks


def format_audit_failure(
    *,
    surface: str,
    operation: str,
    primary_error: Optional[BaseException],
    fallback_error: BaseException,
) -> str:
    if primary_error is not None:
        return (
            f"critical {surface} {operation} failed via Supabase and direct PG fallback: "
            f"supabase={primary_error}; direct_pg={fallback_error}"
        )
    return f"critical {surface} {operation} failed via direct PG fallback: direct_pg={fallback_error}"
