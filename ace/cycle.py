from __future__ import annotations

from pathlib import Path
from typing import Any

from .action_runtime import NotificationSender, run_action_queue_dispatcher, send_operator_notification
from .autonomy_lane import run_autonomy_lane
from .briefing import generate_briefing, render_briefing_text
from .governed_execution import run_governed_execution
from .cost_guardrails import enforce_cost_guardrails
from .telegram_intake import intake_inbound_telegram_work
from .telegram_runtime import fetch_unprocessed_telegram_messages, mark_telegram_message_processed
from .governed_run_runtime import (
    TRIGGER_KIND_OPERATOR,
    complete_governed_run,
    create_or_skip_governed_cycle_run,
    fail_governed_run,
    interrupt_governed_run,
    mark_governed_run_running,
    start_governed_run,
)
from .storage import DB_PATH, STATE_DIR
from .sweep import SweepThresholds, run_sweep
from .repository import ValidationError

BRIEFING_PATH = STATE_DIR / "ace_briefing.md"


def run_cycle(
    db_path: Path | str = DB_PATH,
    *,
    thresholds: SweepThresholds | None = None,
    actor: str | None = None,
    now: str | None = None,
    notification_channel: str | None = None,
    notification_target: str | None = None,
    notification_thread_id: str | None = None,
    briefing_path: Path | str = BRIEFING_PATH,
    sender: NotificationSender | None = None,
    disable_notifications: bool = False,
) -> dict[str, Any]:
    thresholds = thresholds or SweepThresholds()
    trigger_kind = "launchd" if actor == "launchd" else TRIGGER_KIND_OPERATOR
    governed_run = create_or_skip_governed_cycle_run(
        db_path,
        trigger_kind=trigger_kind,
        active_run_stale_after_seconds=_active_run_stale_after_seconds(trigger_kind),
    )
    briefing_file = Path(briefing_path)
    notification_results: list[dict[str, Any]] = []
    ingested_messages: list[dict[str, Any]] = []

    if governed_run["status"] == "skipped":
        return {
            "governed_run": governed_run,
            "ingested_messages": ingested_messages,
            "autonomy": {"verified_done_ids": []},
            "sweep": {"findings": [], "emitted_count": 0, "suppressed_count": 0},
            "briefing": {"generated_at": None, "items": [], "sections": []},
            "briefing_path": str(briefing_file),
            "rendered_briefing": "",
            "actionable_finding_count": 0,
            "notification_count": 0,
            "notifications_suppressed": False,
            "notifications": notification_results,
        }

    try:
        start_governed_run(db_path, governed_run["run_id"])
        mark_governed_run_running(db_path, governed_run["run_id"])
        cost_status = enforce_cost_guardrails(db_path)
        if cost_status.blocked:
            raise CostGuardrailBlocked(cost_status.reason or "cost_guardrail_blocked")

        for message in fetch_unprocessed_telegram_messages():
            intake_result = intake_inbound_telegram_work(
                db_path,
                chat_id=str(message["chat_id"]),
                message_id=str(message["message_id"]),
                text=str(message["text"]),
                received_at=str(message["received_at"]),
                sender_id=str(message["sender_id"]) if message.get("sender_id") is not None else None,
                sender_name=str(message["sender_name"]) if message.get("sender_name") is not None else None,
                actor="ace.telegram_intake",
            )
            ingested_messages.append(intake_result)
            mark_telegram_message_processed(
                chat_id=str(message["chat_id"]),
                message_id=str(message["message_id"]),
                processed_at=str(message["received_at"]),
            )

        autonomy_result = run_autonomy_lane(
            db_path,
            actor=actor,
            source_session=governed_run["run_id"],
            now=now,
        )
        governed_execution_result = run_governed_execution(
            db_path,
            actor=actor,
            source_session=governed_run["run_id"],
            now=now,
        )
        action_queue_result = run_action_queue_dispatcher(
            db_path,
            actor=actor,
        )
        sweep_result = run_sweep(db_path, thresholds=thresholds, actor=actor, now=now)
        briefing = generate_briefing(db_path, thresholds=thresholds, now=now)

        rendered_briefing = render_briefing_text(briefing)
        briefing_file.parent.mkdir(parents=True, exist_ok=True)
        briefing_file.write_text(rendered_briefing + "\n", encoding="utf-8")

        actionable_findings = list(sweep_result.get("findings", []))
        notification_findings = [
            finding for finding in actionable_findings if not finding.get("suppressed", False)
        ]
        notifications_suppressed = False
        if disable_notifications:
            notifications_suppressed = bool(notification_findings)
        else:
            if notification_findings and (not notification_channel or not notification_target):
                raise ValidationError(
                    "notification_channel and notification_target are required when actionable findings exist"
                )

            for finding in notification_findings:
                notification_results.append(
                    send_operator_notification(
                        db_path,
                        finding["item_id"],
                        channel=str(notification_channel),
                        target=str(notification_target),
                        reason=str(finding["classification"]),
                        age_context=_notification_age_context(finding),
                        deadline_context=None,
                        thread_id=notification_thread_id,
                        actor=actor,
                        sender=sender,
                    )
                )

        completed_run = complete_governed_run(
            db_path,
            governed_run["run_id"],
            briefing_path=str(briefing_file),
            notification_action_id=_first_notification_action_id(notification_results),
            delivery_evidence_id=_first_notification_evidence_id(notification_results),
        )

        return {
            "governed_run": completed_run,
            "ingested_messages": ingested_messages,
            "autonomy": autonomy_result,
            "governed_execution": governed_execution_result,
            "action_queue": action_queue_result,
            "sweep": sweep_result,
            "briefing": briefing,
            "briefing_path": str(briefing_file),
            "rendered_briefing": rendered_briefing,
            "actionable_finding_count": len(actionable_findings),
            "notification_count": len(notification_results),
            "notifications_suppressed": notifications_suppressed,
            "notifications": notification_results,
        }
    except (KeyboardInterrupt, SystemExit):
        interrupt_governed_run(
            db_path,
            governed_run["run_id"],
            failure_code="cycle_interrupted",
            failure_summary="bounded ace cycle interrupted before terminal completion",
            briefing_path=str(briefing_file) if briefing_file.exists() else None,
            notification_action_id=_first_notification_action_id(notification_results),
            delivery_evidence_id=_first_notification_evidence_id(notification_results),
        )
        raise
    except Exception as exc:
        fail_governed_run(
            db_path,
            governed_run["run_id"],
            failure_code=_failure_code_for_exception(exc),
            failure_summary=str(exc) or exc.__class__.__name__,
            briefing_path=str(briefing_file) if briefing_file.exists() else None,
            notification_action_id=_first_notification_action_id(notification_results),
            delivery_evidence_id=_first_notification_evidence_id(notification_results),
        )
        raise


class CostGuardrailBlocked(RuntimeError):
    pass


def _active_run_stale_after_seconds(trigger_kind: str) -> int:
    if trigger_kind == "launchd":
        return 5 * 60
    return 24 * 60 * 60


def _notification_age_context(finding: dict[str, Any]) -> str:
    activity_at = str(finding["activity_at"])
    stale_after_seconds = int(finding["stale_after_seconds"])
    stale_after_hours = stale_after_seconds // 3600
    return f"last_activity={activity_at}; stale_threshold={stale_after_hours}h"


def _first_notification_action_id(notification_results: list[dict[str, Any]]) -> str | None:
    if not notification_results:
        return None
    action_id = notification_results[0].get("action_id")
    return str(action_id) if action_id is not None else None


def _first_notification_evidence_id(notification_results: list[dict[str, Any]]) -> str | None:
    if not notification_results:
        return None
    evidence_id = notification_results[0].get("evidence_id")
    return str(evidence_id) if evidence_id is not None else None


def _failure_code_for_exception(exc: Exception) -> str:
    if isinstance(exc, CostGuardrailBlocked):
        return str(exc) or "cost_guardrail_blocked"
    if isinstance(exc, ValidationError):
        return "cycle_validation_error"
    return f"cycle_{exc.__class__.__name__.lower()}"
