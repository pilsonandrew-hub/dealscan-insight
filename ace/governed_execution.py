from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import ItemRepository
from .storage import DB_PATH, connect, utc_now, verify_audit_integrity
from .telegram_intake import TELEGRAM_GOVERNED_EXECUTION_OBLIGATION


GOVERNED_EXECUTION_ACTOR = "ace.governed_execution"
GOVERNED_EXECUTION_PLAN_EVIDENCE_URI = "ace://governed-execution/plan"
GOVERNED_EXECUTION_RESULT_EVIDENCE_URI = "ace://governed-execution/result"
GOVERNED_EXECUTION_ESCALATION_EVIDENCE_URI = "ace://governed-execution/escalation"
GOVERNED_EXECUTION_SOURCE = "ace/governed_execution.py"
GOVERNED_EXECUTION_ALLOWED_INSPECTION_SOURCES = {"ace/internal", "ace/self-test"}
GOVERNED_EXECUTION_INSPECTION_KEYWORDS = ("audit", "check", "inspect", "status", "verify")
GOVERNED_EXECUTION_UNSAFE_KEYWORDS = (
    "delete",
    "drop",
    "erase",
    "external",
    "post",
    "publish",
    "send",
    "shutdown",
    "stop",
    "write to",
)


def run_governed_execution_planner(
    db_path: Path | str = DB_PATH,
    *,
    actor: str | None = None,
    source_session: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    return run_governed_execution(db_path, actor=actor, source_session=source_session, now=now)


def run_governed_execution(
    db_path: Path | str = DB_PATH,
    *,
    actor: str | None = None,
    source_session: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Plan broad work and execute only bounded internal inspection obligations.

    This is intentionally not a general executor. It is the first production-safe
    broad-autonomy seam after intake: ACE recognizes broad direct work, records a
    concrete governed execution contract/plan, keeps unsafe or external work blocked
    behind evidence/escalation, and may autonomously close only narrow ACE-owned
    inspection work with durable result evidence.
    """
    repo = ItemRepository(db_path)
    acting_actor = actor or GOVERNED_EXECUTION_ACTOR
    acting_session = source_session or now or utc_now()

    planned_ids: list[str] = []
    executed_ids: list[str] = []
    closed_ids: list[str] = []
    resolved_ids: list[str] = []
    escalated_ids: list[str] = []
    evidence_ids: list[str] = []
    obligation_ids: list[str] = []

    for row in _open_governed_execution_obligations(db_path):
        item_id = str(row["item_id"])
        obligation_id = str(row["id"])
        item = repo.get_item(item_id)
        if item is None:
            continue
        result_evidence_id = _existing_evidence_id_for_obligation(
            db_path,
            item_id,
            obligation_id,
            GOVERNED_EXECUTION_RESULT_EVIDENCE_URI,
        )
        escalation_evidence_id = _existing_evidence_id_for_obligation(
            db_path,
            item_id,
            obligation_id,
            GOVERNED_EXECUTION_ESCALATION_EVIDENCE_URI,
        )
        if result_evidence_id is not None:
            repo.resolve_obligation(
                obligation_id,
                reason=(
                    "governed execution result evidence is present; broad direct-work "
                    f"obligation satisfied by evidence_id={result_evidence_id}"
                ),
                actor=acting_actor,
            )
            resolved_ids.append(item_id)
            obligation_ids.append(obligation_id)
            continue
        if escalation_evidence_id is not None:
            repo.resolve_obligation(
                obligation_id,
                reason=(
                    "governed execution escalation evidence is present; broad direct-work "
                    f"obligation satisfied by escalation_evidence_id={escalation_evidence_id}"
                ),
                actor=acting_actor,
            )
            escalated_ids.append(item_id)
            obligation_ids.append(obligation_id)
            continue
        plan_evidence_id = _existing_plan_evidence_id(db_path, item_id, obligation_id)
        if plan_evidence_id is None:
            evidence_payload = {
                "item_id": item_id,
                "obligation_id": obligation_id,
                "actor": acting_actor,
                "source": GOVERNED_EXECUTION_SOURCE,
                "source_session": acting_session,
                "plan_kind": "governed_broad_direct_work_plan",
                "contract": {
                    "may_autonomously_close": False,
                    "requires_concrete_execution_evidence": True,
                    "requires_obligation_resolution_before_closeout": True,
                    "must_escalate_if_execution_boundary_is_unclear": True,
                },
                "next_actions": [
                    "inspect the requested work scope against live source-of-truth surfaces",
                    "perform only reversible/internal work without additional authorization",
                    "attach concrete execution evidence before claiming done",
                    "resolve governed_execution_required only after evidence is attached or escalation is recorded",
                ],
            }
            evidence_text = json.dumps(evidence_payload, sort_keys=True, separators=(",", ":"))
            plan_evidence_id = repo.add_evidence(
                item_id,
                evidence_text=evidence_text,
                evidence_uri=GOVERNED_EXECUTION_PLAN_EVIDENCE_URI,
                created_by=GOVERNED_EXECUTION_ACTOR,
                actor=acting_actor,
            )
            planned_ids.append(item_id)
            evidence_ids.append(plan_evidence_id)
            obligation_ids.append(obligation_id)

        if not _is_bounded_internal_inspection_item(item):
            continue

        inspection_result = _attach_bounded_inspection_result(
            db_path,
            item_id=item_id,
            obligation_id=obligation_id,
            plan_evidence_id=plan_evidence_id,
            actor=acting_actor,
            source_session=acting_session,
        )
        evidence_ids.append(inspection_result["evidence_id"])
        executed_ids.append(item_id)
        repo.resolve_obligation(
            obligation_id,
            reason=(
                "governed execution completed bounded internal inspection; "
                f"obligation satisfied by evidence_id={inspection_result['evidence_id']}"
            ),
            actor=acting_actor,
        )
        resolved_ids.append(item_id)
        obligation_ids.append(obligation_id)

        refreshed = repo.get_item(item_id)
        if refreshed is not None and refreshed.state == "TRIAGE":
            refreshed = repo.apply_action(
                refreshed.id,
                "approve",
                actor=acting_actor,
                source=GOVERNED_EXECUTION_SOURCE,
                source_session=acting_session,
                reason="bounded internal governed execution inspection accepted for closeout",
            )
        if refreshed is not None and refreshed.state == "APPROVED":
            refreshed = repo.apply_action(
                refreshed.id,
                "done",
                actor=acting_actor,
                source=GOVERNED_EXECUTION_SOURCE,
                source_session=acting_session,
                reason="bounded internal governed execution inspection completed with result evidence",
            )
        if refreshed is not None and refreshed.state == "CLAIMED_DONE":
            if refreshed.verdict is None:
                verdict = "pass" if inspection_result["passed"] else "fail"
                refreshed = repo.record_verdict(
                    refreshed.id,
                    verdict,
                    actor=acting_actor,
                    source=GOVERNED_EXECUTION_SOURCE,
                    source_session=acting_session,
                    reason=(
                        "bounded internal inspection produced passing governed execution result evidence"
                        if inspection_result["passed"]
                        else "bounded internal inspection found failing governed execution checks"
                    ),
                )
            if refreshed.verdict in {"pass", "ship", "monitor"}:
                refreshed = repo.apply_action(
                    refreshed.id,
                    "resolve",
                    actor=acting_actor,
                    source=GOVERNED_EXECUTION_SOURCE,
                    source_session=acting_session,
                    reason="bounded internal governed execution closeout verified",
                )
                if refreshed.state == "VERIFIED_DONE":
                    closed_ids.append(item_id)

    return {
        "planned_ids": planned_ids,
        "executed_ids": executed_ids,
        "closed_ids": closed_ids,
        "resolved_ids": resolved_ids,
        "escalated_ids": escalated_ids,
        "evidence_ids": evidence_ids,
        "obligation_ids": obligation_ids,
    }


def _open_governed_execution_obligations(db_path: Path | str) -> list[Any]:
    with connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, item_id, obligation_type, status, satisfied_at
            FROM obligations
            WHERE obligation_type = ?
              AND status NOT IN ('resolved', 'done', 'closed')
              AND satisfied_at IS NULL
            ORDER BY created_at ASC, id ASC
            """,
            (TELEGRAM_GOVERNED_EXECUTION_OBLIGATION,),
        ).fetchall()
    return list(rows)


def _existing_plan_evidence_id(db_path: Path | str, item_id: str, obligation_id: str) -> str | None:
    return _existing_evidence_id_for_obligation(
        db_path,
        item_id,
        obligation_id,
        GOVERNED_EXECUTION_PLAN_EVIDENCE_URI,
        created_by=GOVERNED_EXECUTION_ACTOR,
    )


def _existing_evidence_id_for_obligation(
    db_path: Path | str,
    item_id: str,
    obligation_id: str,
    evidence_uri: str,
    *,
    created_by: str | None = None,
) -> str | None:
    with connect(db_path) as connection:
        if created_by is None:
            rows = connection.execute(
                """
                SELECT id, evidence_text
                FROM evidence
                WHERE item_id = ?
                  AND evidence_uri = ?
                ORDER BY created_at ASC, id ASC
                """,
                (item_id, evidence_uri),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, evidence_text
                FROM evidence
                WHERE item_id = ?
                  AND evidence_uri = ?
                  AND created_by = ?
                ORDER BY created_at ASC, id ASC
                """,
                (item_id, evidence_uri, created_by),
            ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["evidence_text"])
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("obligation_id") == obligation_id:
            return str(row["id"])
    return None


def _is_bounded_internal_inspection_item(item: Any) -> bool:
    title = item.title.strip().lower()
    description = (item.description or "").strip().lower()
    combined = f"{title}\n{description}"
    if item.source not in GOVERNED_EXECUTION_ALLOWED_INSPECTION_SOURCES:
        return False
    if _has_unsafe_governed_execution_keyword(combined):
        return False
    return any(keyword in combined for keyword in GOVERNED_EXECUTION_INSPECTION_KEYWORDS)


def _has_unsafe_governed_execution_keyword(text: str) -> bool:
    normalized = " ".join(text.split())
    if "external" in normalized and "no external side effects" not in normalized:
        return True
    for keyword in GOVERNED_EXECUTION_UNSAFE_KEYWORDS:
        if keyword == "external":
            continue
        if keyword in normalized:
            return True
    return False


def _attach_bounded_inspection_result(
    db_path: Path | str,
    *,
    item_id: str,
    obligation_id: str,
    plan_evidence_id: str,
    actor: str,
    source_session: str,
) -> dict[str, Any]:
    repo = ItemRepository(db_path)
    audit_result = verify_audit_integrity(db_path)
    failed_checks = {
        name: {"ok": status[0], "detail": status[1]}
        for name, status in audit_result.items()
        if not status[0]
    }
    payload = {
        "item_id": item_id,
        "obligation_id": obligation_id,
        "plan_evidence_id": plan_evidence_id,
        "actor": actor,
        "source": GOVERNED_EXECUTION_SOURCE,
        "source_session": source_session,
        "execution_kind": "bounded_internal_inspection",
        "result": "pass" if not failed_checks else "fail",
        "durable_checks": {
            name: {"ok": status[0], "detail": status[1]}
            for name, status in audit_result.items()
        },
        "contract": {
            "no_external_side_effects": True,
            "no_destructive_actions": True,
            "closed_only_bounded_internal_inspection": True,
        },
    }
    evidence_id = repo.add_evidence(
        item_id,
        evidence_text=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        evidence_uri=GOVERNED_EXECUTION_RESULT_EVIDENCE_URI,
        created_by=GOVERNED_EXECUTION_ACTOR,
        actor=actor,
    )
    return {"evidence_id": evidence_id, "passed": not failed_checks, "failed_checks": failed_checks}
