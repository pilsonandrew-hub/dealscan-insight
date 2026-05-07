from __future__ import annotations

from pathlib import Path
from typing import Any

from .repository import ItemRepository
from .storage import DB_PATH, connect, utc_now


AUTONOMY_ITEM_TYPE = "machine_verifiable_work"
AUTONOMY_ACTOR = "ace.autonomy_lane"
AUTONOMY_SOURCE = "ace/autonomy_lane.py"
AUTONOMY_EVIDENCE_URI = "ace://autonomy/machine-verifiable-closeout"
AUTONOMY_ELIGIBLE_WORK_SOURCE = "telegram/direct"
AUTONOMY_ELIGIBILITY_EVIDENCE_URI = "ace://autonomy/eligible-direct-work"
AUTONOMY_ELIGIBILITY_CREATED_BY = "ace.autonomy_lane"


def mark_item_autonomy_eligible(
    db_path: Path | str = DB_PATH,
    item_id: str | None = None,
    *,
    reason: str,
    actor: str | None = None,
) -> str:
    repo = ItemRepository(db_path)
    if item_id is None or not item_id.strip():
        raise ValueError("item_id is required")
    item = repo.get_item(item_id)
    if item is None:
        raise KeyError(f"unknown item_id: {item_id}")
    if item.item_type != "work":
        raise ValueError("only work items may be marked autonomy-eligible")
    if item.source != AUTONOMY_ELIGIBLE_WORK_SOURCE:
        raise ValueError("only telegram/direct work items may be marked autonomy-eligible")

    normalized_reason = reason.strip()
    if not normalized_reason:
        raise ValueError("reason must not be empty or whitespace-only")

    existing = _eligibility_evidence_id(db_path, item.id)
    if existing is not None:
        return existing

    evidence_text = (
        "ACE governed autonomy eligibility marker for direct work. "
        f"Reason: {normalized_reason}"
    )
    return repo.add_evidence(
        item.id,
        evidence_text=evidence_text,
        evidence_uri=AUTONOMY_ELIGIBILITY_EVIDENCE_URI,
        created_by=AUTONOMY_ELIGIBILITY_CREATED_BY,
        actor=actor,
    )


def _eligibility_evidence_id(db_path: Path | str, item_id: str) -> str | None:
    with connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT id
            FROM evidence
            WHERE item_id = ?
              AND evidence_uri = ?
              AND created_by = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (item_id, AUTONOMY_ELIGIBILITY_EVIDENCE_URI, AUTONOMY_ELIGIBILITY_CREATED_BY),
        ).fetchone()
    return row[0] if row is not None else None


def _is_autonomy_eligible(item: Any, *, repo: ItemRepository | None = None) -> bool:
    if item.item_type == AUTONOMY_ITEM_TYPE:
        return True
    if item.item_type != "work":
        return False
    if item.source != AUTONOMY_ELIGIBLE_WORK_SOURCE:
        return False
    if repo is None:
        raise ValueError("repo is required for real-work autonomy eligibility checks")
    return _eligibility_evidence_id(repo.db_path, item.id) is not None


def _approval_reason(item: Any) -> str:
    if item.item_type == AUTONOMY_ITEM_TYPE:
        return "machine-verifiable autonomy lane accepted item for governed execution"
    return "governed real-work autonomy lane accepted explicitly eligible direct work item"


def _done_reason(item: Any) -> str:
    if item.item_type == AUTONOMY_ITEM_TYPE:
        return "machine-verifiable autonomy lane completed bounded work"
    return "governed real-work autonomy lane completed explicitly eligible direct work item"


def _resolve_reason(item: Any) -> str:
    if item.item_type == AUTONOMY_ITEM_TYPE:
        return "machine-verifiable autonomy lane closeout verified from bounded evidence"
    return "governed real-work autonomy lane closeout verified from explicit eligibility evidence"


def _evidence_text(item: Any) -> str:
    if item.item_type == AUTONOMY_ITEM_TYPE:
        return (
            "ACE governed autonomy lane executed this machine-verifiable work item "
            "without user touch: autonomous approval, evidence capture, claimed-done, "
            "and closeout resolution all occurred inside the bounded lane."
        )
    return (
        "ACE governed autonomy lane executed this direct real-work item without user touch: "
        "the item carried explicit governed eligibility evidence, ACE autonomously approved "
        "it, captured evidence, marked it claimed-done, and resolved closeout through the "
        "repository-owned workflow seam."
    )


def run_autonomy_lane(
    db_path: Path | str = DB_PATH,
    *,
    actor: str | None = None,
    source_session: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    repo = ItemRepository(db_path)
    acting_actor = actor or AUTONOMY_ACTOR
    acting_session = source_session or now or utc_now()

    approved_ids: list[str] = []
    claimed_done_ids: list[str] = []
    verified_done_ids: list[str] = []
    evidence_ids: list[str] = []

    items = repo.list_items()
    for item in items:
        if not _is_autonomy_eligible(item, repo=repo):
            continue

        if item.state == "TRIAGE":
            item = repo.apply_action(
                item.id,
                "approve",
                actor=acting_actor,
                source=AUTONOMY_SOURCE,
                source_session=acting_session,
                reason=_approval_reason(item),
            )
            approved_ids.append(item.id)

        if item.state == "APPROVED":
            evidence_id = repo.add_evidence(
                item.id,
                evidence_text=_evidence_text(item),
                evidence_uri=AUTONOMY_EVIDENCE_URI,
                created_by=acting_actor,
                actor=acting_actor,
            )
            evidence_ids.append(evidence_id)
            item = repo.apply_action(
                item.id,
                "done",
                actor=acting_actor,
                source=AUTONOMY_SOURCE,
                source_session=acting_session,
                reason=_done_reason(item),
            )
            claimed_done_ids.append(item.id)

        if item.state == "CLAIMED_DONE":
            item = repo.apply_action(
                item.id,
                "resolve",
                actor=acting_actor,
                source=AUTONOMY_SOURCE,
                source_session=acting_session,
                reason=_resolve_reason(item),
            )
            verified_done_ids.append(item.id)

    return {
        "approved_ids": approved_ids,
        "claimed_done_ids": claimed_done_ids,
        "verified_done_ids": verified_done_ids,
        "evidence_ids": evidence_ids,
    }
