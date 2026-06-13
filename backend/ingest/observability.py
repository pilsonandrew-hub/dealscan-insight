"""Sanitized ingest observability writes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Mapping


logger = logging.getLogger(__name__)

SENSITIVE_METADATA_KEYS = {
    "listing_url",
    "url",
    "vin",
    "raw_payload",
    "raw_data",
    "description",
    "detail_text",
    "details",
    "condition_notes",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _sanitize_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in SENSITIVE_METADATA_KEYS:
            continue
        if value in (None, "", {}, []):
            continue
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
    return sanitized


def upsert_scrape_run_start(
    supabase_client: Any,
    *,
    run_id: str,
    source_name: str,
    actor_id: str | None = None,
    dataset_id: str | None = None,
    item_count: int = 0,
) -> bool:
    if supabase_client is None or not run_id:
        return False
    now_iso = _now_iso()
    payload = {
        "run_id": run_id,
        "source_name": source_name or "unknown",
        "actor_id": actor_id,
        "dataset_id": dataset_id,
        "status": "started",
        "item_count": _safe_int(item_count),
        "started_at": now_iso,
        "updated_at": now_iso,
    }
    try:
        supabase_client.table("scrape_runs").upsert(payload, on_conflict="run_id").execute()
        return True
    except Exception as exc:
        logger.warning("[INGEST_OBSERVABILITY] scrape run start write failed for run_id=%s: %s", run_id, exc)
        return False


def upsert_scrape_run_completion(
    supabase_client: Any,
    *,
    run_id: str,
    source_name: str,
    status: str,
    item_count: int = 0,
    evaluated_count: int = 0,
    saved_count: int = 0,
    existing_count: int = 0,
    skipped_count: int = 0,
    failed_count: int = 0,
    duplicate_count: int = 0,
    hot_deal_count: int = 0,
    alert_blocked_count: int = 0,
    parse_event_count: int = 0,
    skip_reasons: Mapping[str, Any] | None = None,
    save_outcomes: Mapping[str, Any] | None = None,
    error_message: str | None = None,
) -> bool:
    if supabase_client is None or not run_id:
        return False
    now_iso = _now_iso()
    payload = {
        "run_id": run_id,
        "source_name": source_name or "unknown",
        "status": status,
        "item_count": _safe_int(item_count),
        "evaluated_count": _safe_int(evaluated_count),
        "saved_count": _safe_int(saved_count),
        "existing_count": _safe_int(existing_count),
        "skipped_count": _safe_int(skipped_count),
        "failed_count": _safe_int(failed_count),
        "duplicate_count": _safe_int(duplicate_count),
        "hot_deal_count": _safe_int(hot_deal_count),
        "alert_blocked_count": _safe_int(alert_blocked_count),
        "parse_event_count": _safe_int(parse_event_count),
        "skip_reasons": dict(skip_reasons or {}),
        "save_outcomes": dict(save_outcomes or {}),
        "error_message": error_message,
        "completed_at": now_iso,
        "updated_at": now_iso,
    }
    try:
        supabase_client.table("scrape_runs").upsert(payload, on_conflict="run_id").execute()
        return True
    except Exception as exc:
        logger.warning("[INGEST_OBSERVABILITY] scrape run completion write failed for run_id=%s: %s", run_id, exc)
        return False


def record_parse_event(
    supabase_client: Any,
    *,
    run_id: str,
    source_name: str,
    event_type: str,
    status: str,
    item_index: int | None = None,
    listing_id: str | None = None,
    reason: str | None = None,
    error_message: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> bool:
    if supabase_client is None or not run_id:
        return False
    payload = {
        "run_id": run_id,
        "source_name": source_name or "unknown",
        "event_type": event_type,
        "item_index": item_index,
        "listing_id": listing_id,
        "status": status,
        "reason": reason,
        "error_message": error_message,
        "metadata": _sanitize_metadata(metadata),
    }
    try:
        supabase_client.table("parse_events").insert(payload).execute()
        return True
    except Exception as exc:
        logger.warning("[INGEST_OBSERVABILITY] parse event write failed for run_id=%s status=%s: %s", run_id, status, exc)
        return False
