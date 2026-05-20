from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import DB_PATH, bootstrap_db, connect, utc_now

_ACTIVE_ACTION_STATUSES = ("queued", "claimed")
_FAILED_ACTION_STATUS = "failed"
_ACTIVE_RUN_STATUSES = ("pending", "starting", "running")
_FAILED_RUN_STATUSES = ("failed", "interrupted")
_SKIPPED_RUN_STATUS = "skipped"
_ACTIVE_RUNTIME_STATUSES = ("starting", "live", "stale")
_FAILED_RUNTIME_STATUSES = ("failed", "stale")
_FAILED_ALERT_STATES = ("failed", "error", "rejected")


def generate_health_summary(
    db_path: Path | str = DB_PATH,
    *,
    now: str | None = None,
    stale_runtime_seconds: int = 15 * 60,
) -> dict[str, Any]:
    """Return compact operator-visible health truth from durable ACE ledgers."""

    bootstrap_db(db_path)
    generated_at = now or utc_now()
    normalized_stale_runtime_seconds = _normalize_non_negative_int(
        stale_runtime_seconds,
        field_name="stale_runtime_seconds",
    )

    with connect(db_path) as connection:
        active_action_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM action_queue WHERE status IN (?, ?)",
            _ACTIVE_ACTION_STATUSES,
        )
        failed_action_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM action_queue WHERE status = ?",
            (_FAILED_ACTION_STATUS,),
        )
        active_run_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM governed_runs WHERE status IN (?, ?, ?)",
            _ACTIVE_RUN_STATUSES,
        )
        failed_run_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM governed_runs WHERE status IN (?, ?)",
            _FAILED_RUN_STATUSES,
        )
        skipped_run_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM governed_runs WHERE status = ?",
            (_SKIPPED_RUN_STATUS,),
        )
        active_runtime_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM runtime_instances WHERE status IN (?, ?, ?)",
            _ACTIVE_RUNTIME_STATUSES,
        )
        failed_runtime_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM runtime_instances WHERE status IN (?, ?)",
            _FAILED_RUNTIME_STATUSES,
        )
        failed_alert_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM alert_log WHERE delivery_state IN (?, ?, ?)",
            _FAILED_ALERT_STATES,
        )
        notification_action_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM action_queue WHERE action_type = ?",
            ("send_operator_notification",),
        )
        completed_notification_action_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM action_queue WHERE action_type = ? AND status = ?",
            ("send_operator_notification", "completed"),
        )
        alert_delivery_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM alert_log WHERE alert_type IN (?, ?)",
            ("operator_notification", "jace_status"),
        )
        notification_delivery_evidence_count = _scalar_count(
            connection,
            "SELECT COUNT(*) FROM evidence WHERE evidence_uri = ? AND created_by = ?",
            ("ace://notification/delivery", "ace.notification_runtime"),
        )
        stale_runtime_count = _stale_runtime_count(
            connection,
            now=generated_at,
            stale_after_seconds=normalized_stale_runtime_seconds,
        )

    alert_gap_count = max(completed_notification_action_count - notification_delivery_evidence_count, 0)
    issue_count = (
        active_action_count
        + failed_action_count
        + active_run_count
        + failed_run_count
        + skipped_run_count
        + stale_runtime_count
        + failed_runtime_count
        + failed_alert_count
        + alert_gap_count
    )

    return {
        "generated_at": generated_at,
        "ok": issue_count == 0,
        "issue_count": issue_count,
        "active_action_count": active_action_count,
        "failed_action_count": failed_action_count,
        "active_run_count": active_run_count,
        "failed_run_count": failed_run_count,
        "skipped_run_count": skipped_run_count,
        "active_runtime_count": active_runtime_count,
        "stale_runtime_count": stale_runtime_count,
        "failed_runtime_count": failed_runtime_count,
        "failed_alert_count": failed_alert_count,
        "notification_action_count": notification_action_count,
        "completed_notification_action_count": completed_notification_action_count,
        "alert_delivery_count": alert_delivery_count,
        "notification_delivery_evidence_count": notification_delivery_evidence_count,
        "alert_gap_count": alert_gap_count,
        "stale_runtime_seconds": normalized_stale_runtime_seconds,
    }


def render_health_summary_lines(summary: dict[str, Any], *, prefix: str = "health") -> list[str]:
    ordered_keys = (
        "generated_at",
        "ok",
        "issue_count",
        "active_action_count",
        "failed_action_count",
        "active_run_count",
        "failed_run_count",
        "skipped_run_count",
        "active_runtime_count",
        "stale_runtime_count",
        "failed_runtime_count",
        "failed_alert_count",
        "notification_action_count",
        "completed_notification_action_count",
        "alert_delivery_count",
        "notification_delivery_evidence_count",
        "alert_gap_count",
        "stale_runtime_seconds",
    )
    lines: list[str] = []
    for key in ordered_keys:
        value = summary.get(key)
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"{prefix}.{key}={value}")
    return lines


def _scalar_count(connection: Any, query: str, parameters: tuple[Any, ...]) -> int:
    row = connection.execute(query, parameters).fetchone()
    return int(row[0])


def _stale_runtime_count(connection: Any, *, now: str, stale_after_seconds: int) -> int:
    rows = connection.execute(
        """
        SELECT last_seen_at
        FROM runtime_instances
        WHERE status IN (?, ?, ?)
        """,
        _ACTIVE_RUNTIME_STATUSES,
    ).fetchall()
    return sum(
        1
        for row in rows
        if _age_seconds(str(row["last_seen_at"]), now) >= stale_after_seconds
    )


def _age_seconds(activity_at: str, now: str) -> int:
    delta = _parse_timestamp(now) - _parse_timestamp(activity_at)
    return max(int(delta.total_seconds()), 0)


def _parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_non_negative_int(value: int, *, field_name: str) -> int:
    normalized = int(value)
    if normalized < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return normalized
