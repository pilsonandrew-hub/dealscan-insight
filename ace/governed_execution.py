from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .repository import ItemRepository
from .storage import DB_PATH, connect, utc_now
from .telegram_intake import TELEGRAM_GOVERNED_EXECUTION_OBLIGATION


GOVERNED_EXECUTION_ACTOR = "ace.governed_execution"
GOVERNED_EXECUTION_PLAN_EVIDENCE_URI = "ace://governed-execution/plan"
GOVERNED_EXECUTION_RESULT_EVIDENCE_URI = "ace://governed-execution/result"
GOVERNED_EXECUTION_ESCALATION_EVIDENCE_URI = "ace://governed-execution/escalation"
GOVERNED_EXECUTION_SOURCE = "ace/governed_execution.py"


def run_governed_execution_planner(
    db_path: Path | str = DB_PATH,
    *,
    actor: str | None = None,
    source_session: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Attach bounded execution-plan evidence for broad work that cannot auto-close.

    This is intentionally not a general executor. It is the first production-safe
    broad-autonomy seam after intake: ACE recognizes broad direct work, records a
    concrete governed execution contract/plan, and keeps the open obligation in
    place so closeout remains blocked until a later execution/escalation seam
    satisfies it with real evidence.
    """
    repo = ItemRepository(db_path)
    acting_actor = actor or GOVERNED_EXECUTION_ACTOR
    acting_session = source_session or now or utc_now()

    planned_ids: list[str] = []
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
        if _existing_plan_evidence_id(db_path, item_id, obligation_id) is not None:
            continue

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
        evidence_id = repo.add_evidence(
            item_id,
            evidence_text=evidence_text,
            evidence_uri=GOVERNED_EXECUTION_PLAN_EVIDENCE_URI,
            created_by=GOVERNED_EXECUTION_ACTOR,
            actor=acting_actor,
        )
        planned_ids.append(item_id)
        evidence_ids.append(evidence_id)
        obligation_ids.append(obligation_id)

    return {
        "planned_ids": planned_ids,
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
