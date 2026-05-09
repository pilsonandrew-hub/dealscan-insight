from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .storage import DB_PATH, append_event, bootstrap_db, connect, new_id, utc_now
from .workflow import (
    CloseoutGateError,
    closeout_gate,
    is_terminal_contradiction_status,
    is_terminal_obligation_status,
    next_state,
    normalize_action,
    normalize_confidence_tier,
    normalize_new_contradiction_status,
    normalize_state,
    normalize_verdict,
)


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    item_type: str
    title: str
    description: str | None
    state: str
    priority_hint: str | None
    confidence_tier: str | None
    verdict: str | None
    source: str | None
    source_session: str | None
    deadline_at: str | None
    owner: str | None
    created_at: str
    updated_at: str
    closed_at: str | None
    closed_by: str | None
    closed_reason: str | None
    last_event_id: str | None


@dataclass(frozen=True)
class ItemEvent:
    event_id: str
    event_type: str
    created_at: str
    actor: str | None
    source: str | None
    session_id: str | None
    payload_status: str
    payload_json: str | None
    payload_raw: str | None


def _normalize_required_human_text(value: str | None, *, field_name: str) -> str:
    if value is None:
        raise ValidationError(f"{field_name} is required")
    normalized = value.strip()
    if not normalized:
        raise ValidationError(f"{field_name} must not be empty or whitespace-only")
    return normalized


def _row_to_obligation_resolution_result(row: Any) -> dict[str, Any]:
    return {
        "obligation_id": row["id"],
        "item_id": row["item_id"],
        "status": row["status"],
        "satisfied_at": row["satisfied_at"],
    }


def _row_to_contradiction_resolution_result(row: Any) -> dict[str, Any]:
    return {
        "contradiction_id": row["id"],
        "item_id": row["target_item_id"],
        "status": row["status"],
        "resolved_at": row["resolved_at"],
    }


def _state_changed_payload(
    *,
    item_id: str,
    previous_state: str,
    target_state: str,
    action: str,
    reason: str | None,
    closeout_run_id: str | None = None,
    closeout_event_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "item_id": item_id,
        "from_state": previous_state,
        "to_state": target_state,
        "action": action,
        "reason": reason,
    }
    if closeout_run_id is not None:
        payload["closeout_run_id"] = closeout_run_id
    if closeout_event_id is not None:
        payload["closeout_event_id"] = closeout_event_id
    return payload


def _closeout_attempted_payload(
    *,
    item_id: str,
    previous_state: str,
    target_state: str,
    reason: str | None,
    evidence_count: int,
    open_obligation_count: int,
    open_contradiction_count: int,
    passed: bool,
    failure_code: str | None,
    failure_detail: str | None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "from_state": previous_state,
        "to_state": target_state,
        "reason": reason,
        "evidence_count": evidence_count,
        "open_obligation_count": open_obligation_count,
        "open_contradiction_count": open_contradiction_count,
        "result": "passed" if passed else "blocked",
        "failure_code": failure_code,
        "failure_detail": failure_detail,
    }


def _obligation_resolved_payload(
    *,
    obligation_id: str,
    item_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "obligation_id": obligation_id,
        "item_id": item_id,
        "reason": reason,
    }


def _contradiction_resolved_payload(
    *,
    contradiction_id: str,
    item_id: str,
    source_item_id: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "contradiction_id": contradiction_id,
        "item_id": item_id,
        "source_item_id": source_item_id,
        "reason": reason,
    }


class ItemRepository:
    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        bootstrap_db(self.db_path)

    def create_item(
        self,
        *,
        item_type: str,
        title: str,
        description: str | None = None,
        state: str = "TRIAGE",
        priority_hint: str | None = None,
        confidence_tier: str | None = None,
        verdict: str | None = None,
        source: str | None = None,
        source_session: str | None = None,
        deadline_at: str | None = None,
        owner: str | None = None,
        actor: str | None = None,
        created_payload_extra: dict[str, object] | None = None,
    ) -> Item:
        normalized_item_type = item_type.strip()
        if not normalized_item_type:
            raise ValidationError("item_type must not be empty or whitespace-only")
        normalized_title = title.strip()
        if not normalized_title:
            raise ValidationError("title must not be empty or whitespace-only")
        normalized_description = None
        if description is not None:
            normalized_description = description.strip()
            if not normalized_description:
                raise ValidationError("description must not be empty or whitespace-only")
        normalized_priority_hint = None
        if priority_hint is not None:
            normalized_priority_hint = priority_hint.strip()
            if not normalized_priority_hint:
                raise ValidationError("priority_hint must not be empty or whitespace-only")
        normalized_confidence_tier = None
        if confidence_tier is not None:
            normalized_confidence_tier = normalize_confidence_tier(confidence_tier)
        normalized_verdict = None
        if verdict is not None:
            normalized_verdict = normalize_verdict(verdict)
        normalized_source = None
        if source is not None:
            normalized_source = source.strip()
            if not normalized_source:
                raise ValidationError("source must not be empty or whitespace-only")
        normalized_source_session = None
        if source_session is not None:
            normalized_source_session = source_session.strip()
            if not normalized_source_session:
                raise ValidationError("source_session must not be empty or whitespace-only")
        normalized_owner = None
        if owner is not None:
            normalized_owner = owner.strip()
            if not normalized_owner:
                raise ValidationError("owner must not be empty or whitespace-only")
        normalized_state = normalize_state(state)
        item_id = new_id("item")
        created_at = utc_now()
        event_payload = {
            "item_id": item_id,
            "item_type": normalized_item_type,
            "title": normalized_title,
            "description": normalized_description,
            "state": normalized_state,
            "priority_hint": normalized_priority_hint,
            "confidence_tier": normalized_confidence_tier,
            "verdict": normalized_verdict,
            "source": normalized_source,
            "source_session": normalized_source_session,
            "deadline_at": deadline_at,
            "owner": normalized_owner,
        }
        if created_payload_extra:
            event_payload.update(created_payload_extra)

        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO items (
                    id, item_type, title, description, state, priority_hint,
                    confidence_tier, verdict, source, source_session, deadline_at,
                    owner, created_at, updated_at, last_event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item_id,
                    normalized_item_type,
                    normalized_title,
                    normalized_description,
                    normalized_state,
                    normalized_priority_hint,
                    normalized_confidence_tier,
                    normalized_verdict,
                    normalized_source,
                    normalized_source_session,
                    deadline_at,
                    normalized_owner,
                    created_at,
                    created_at,
                    None,
                ),
            )
            event_id = append_event(
                connection,
                event_type="item.created",
                payload=event_payload,
                item_id=item_id,
                actor=actor,
                source=source,
                session_id=source_session,
                created_at=created_at,
            )
            connection.execute(
                "UPDATE items SET last_event_id = ? WHERE id = ?",
                (event_id, item_id),
            )
            connection.commit()
            final_row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            assert final_row is not None, "item creation failed unexpectedly"
            return self._row_to_item(final_row)

    def add_evidence(
        self,
        item_id: str,
        *,
        evidence_text: str,
        evidence_uri: str | None = None,
        created_by: str | None = None,
        actor: str | None = None,
    ) -> str:
        normalized_evidence_text = evidence_text.strip()
        if not normalized_evidence_text:
            raise ValidationError("evidence_text must not be empty or whitespace-only")
        normalized_evidence_uri = None
        if evidence_uri is not None:
            normalized_evidence_uri = evidence_uri.strip()
            if not normalized_evidence_uri:
                raise ValidationError("evidence_uri must not be empty or whitespace-only")
        normalized_created_by = None
        if created_by is not None:
            normalized_created_by = created_by.strip()
            if not normalized_created_by:
                raise ValidationError("created_by must not be empty or whitespace-only")
        evidence_id = new_id("evidence")
        created_at = utc_now()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO evidence (
                    id, item_id, evidence_text, evidence_uri, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    item_id,
                    normalized_evidence_text,
                    normalized_evidence_uri,
                    normalized_created_by,
                    created_at,
                ),
            )
            append_event(
                connection,
                event_type="item.evidence_added",
                payload={
                    "item_id": item_id,
                    "evidence_id": evidence_id,
                    "evidence_text": normalized_evidence_text,
                    "evidence_uri": normalized_evidence_uri,
                    "created_by": normalized_created_by,
                },
                item_id=item_id,
                actor=actor,
                created_at=created_at,
            )
            connection.commit()
        return evidence_id

    def add_obligation(
        self,
        item_id: str,
        *,
        obligation_type: str,
        status: str = "open",
        target_surface: str | None = None,
        notes: str | None = None,
        actor: str | None = None,
    ) -> str:
        normalized_obligation_type = obligation_type.strip()
        if not normalized_obligation_type:
            raise ValidationError("obligation_type must not be empty or whitespace-only")
        normalized_notes = None
        if notes is not None:
            normalized_notes = notes.strip()
            if not normalized_notes:
                raise ValidationError("notes must not be empty or whitespace-only")
        normalized_target_surface = None
        if target_surface is not None:
            normalized_target_surface = target_surface.strip()
            if not normalized_target_surface:
                raise ValidationError("target_surface must not be empty or whitespace-only")
        obligation_id = new_id("obligation")
        created_at = utc_now()
        normalized_status = status.strip().lower()
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO obligations (
                    id, item_id, obligation_type, target_surface, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    obligation_id,
                    item_id,
                    normalized_obligation_type,
                    normalized_target_surface,
                    normalized_status,
                    normalized_notes,
                    created_at,
                    created_at,
                ),
            )
            append_event(
                connection,
                event_type="item.obligation_added",
                payload={
                    "item_id": item_id,
                    "obligation_id": obligation_id,
                    "obligation_type": normalized_obligation_type,
                    "target_surface": normalized_target_surface,
                    "status": normalized_status,
                    "notes": normalized_notes,
                },
                item_id=item_id,
                actor=actor,
                created_at=created_at,
            )
            connection.commit()
        return obligation_id

    def resolve_obligation(
        self,
        obligation_id: str,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        normalized_reason = _normalize_required_human_text(reason, field_name="reason")

        updated_at = utc_now()
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, item_id, status, satisfied_at
                FROM obligations
                WHERE id = ?
                """,
                (obligation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown obligation_id: {obligation_id}")

            if row["satisfied_at"] is None and not is_terminal_obligation_status(row["status"]):
                connection.execute(
                    """
                    UPDATE obligations
                    SET status = ?, satisfied_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    ("resolved", updated_at, updated_at, obligation_id),
                )
                append_event(
                    connection,
                    event_type="item.obligation_resolved",
                    payload=_obligation_resolved_payload(
                        obligation_id=obligation_id,
                        item_id=row["item_id"],
                        reason=normalized_reason,
                    ),
                    item_id=row["item_id"],
                    actor=actor,
                    created_at=updated_at,
                )
                connection.commit()
                row = connection.execute(
                    """
                    SELECT id, item_id, status, satisfied_at
                    FROM obligations
                    WHERE id = ?
                    """,
                    (obligation_id,),
                ).fetchone()
                assert row is not None, "obligation resolution failed unexpectedly"

            return _row_to_obligation_resolution_result(row)

    def add_contradiction(
        self,
        item_id: str,
        *,
        source_item_id: str,
        status: str = "open",
        reason: str | None = None,
        actor: str | None = None,
    ) -> str:
        normalized_reason: str | None = None
        if reason is not None:
            normalized_reason = reason.strip()
            if not normalized_reason:
                raise ValidationError("reason must not be empty or whitespace-only")
        contradiction_id = new_id("contradiction")
        created_at = utc_now()
        normalized_status = normalize_new_contradiction_status(status)
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO contradictions (
                    id, source_item_id, target_item_id, status, reason, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contradiction_id,
                    source_item_id,
                    item_id,
                    normalized_status,
                    normalized_reason,
                    created_at,
                    None,
                ),
            )
            append_event(
                connection,
                event_type="item.contradiction_added",
                payload={
                    "item_id": item_id,
                    "contradiction_id": contradiction_id,
                    "source_item_id": source_item_id,
                    "status": normalized_status,
                    "reason": normalized_reason,
                },
                item_id=item_id,
                actor=actor,
                created_at=created_at,
            )
            connection.commit()
        return contradiction_id

    def record_correction(
        self,
        item_id: str,
        *,
        corrected_item_id: str,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        normalized_reason = _normalize_required_human_text(reason, field_name="reason")

        if item_id == corrected_item_id:
            raise ValidationError("corrected_item_id must differ from item_id")

        contradiction_id = self.add_contradiction(
            item_id,
            source_item_id=corrected_item_id,
            reason=normalized_reason,
            actor=actor,
        )

        created_at = utc_now()
        with connect(self.db_path) as connection:
            original_row = connection.execute(
                "SELECT id FROM items WHERE id = ?",
                (item_id,),
            ).fetchone()
            corrected_row = connection.execute(
                "SELECT id FROM items WHERE id = ?",
                (corrected_item_id,),
            ).fetchone()

            if original_row is None:
                raise KeyError(f"unknown item_id: {item_id}")
            if corrected_row is None:
                raise KeyError(f"unknown corrected_item_id: {corrected_item_id}")

            append_event(
                connection,
                event_type="item.correction_recorded",
                payload={
                    "item_id": item_id,
                    "corrected_item_id": corrected_item_id,
                    "contradiction_id": contradiction_id,
                    "reason": normalized_reason,
                },
                item_id=item_id,
                actor=actor,
                created_at=created_at,
            )
            append_event(
                connection,
                event_type="item.correction_linked",
                payload={
                    "item_id": corrected_item_id,
                    "supersedes_item_id": item_id,
                    "contradiction_id": contradiction_id,
                    "reason": normalized_reason,
                },
                item_id=corrected_item_id,
                actor=actor,
                created_at=created_at,
            )
            connection.commit()

        return {
            "item_id": item_id,
            "corrected_item_id": corrected_item_id,
            "contradiction_id": contradiction_id,
            "reason": normalized_reason,
        }

    def resolve_contradiction(
        self,
        contradiction_id: str,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any]:
        normalized_reason = _normalize_required_human_text(reason, field_name="reason")

        updated_at = utc_now()
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, source_item_id, target_item_id, status, reason, resolved_at
                FROM contradictions
                WHERE id = ?
                """,
                (contradiction_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown contradiction_id: {contradiction_id}")
            if row["resolved_at"] is None and not is_terminal_contradiction_status(row["status"]):
                connection.execute(
                    """
                    UPDATE contradictions
                    SET status = ?, resolved_at = ?
                    WHERE id = ?
                    """,
                    ("resolved", updated_at, contradiction_id),
                )
                append_event(
                    connection,
                    event_type="item.contradiction_resolved",
                    payload=_contradiction_resolved_payload(
                        contradiction_id=contradiction_id,
                        item_id=row["target_item_id"],
                        source_item_id=row["source_item_id"],
                        reason=normalized_reason,
                    ),
                    item_id=row["target_item_id"],
                    actor=actor,
                    created_at=updated_at,
                )
                connection.commit()
                row = connection.execute(
                    """
                    SELECT id, source_item_id, target_item_id, status, reason, resolved_at
                    FROM contradictions
                    WHERE id = ?
                    """,
                    (contradiction_id,),
                ).fetchone()
                assert row is not None, "contradiction resolution failed unexpectedly"

            return _row_to_contradiction_resolution_result(row)

    def get_item(self, item_id: str) -> Item | None:
        with connect(self.db_path) as connection:
            row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        return self._row_to_item(row) if row else None

    def get_item_by_source_and_session(
        self,
        source: str,
        source_session: str,
    ) -> Item | None:
        normalized_source = source.strip()
        if not normalized_source:
            raise ValidationError("source must not be empty or whitespace-only")
        normalized_source_session = source_session.strip()
        if not normalized_source_session:
            raise ValidationError("source_session must not be empty or whitespace-only")

        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM items
                WHERE source = ? AND source_session = ?
                ORDER BY created_at ASC, id ASC
                """,
                (normalized_source, normalized_source_session),
            ).fetchall()

        if not rows:
            return None
        if len(rows) > 1:
            raise ValidationError(
                f"duplicate provenance rows for source={normalized_source} source_session={normalized_source_session}"
            )
        return self._row_to_item(rows[0])

    def list_items(self, *, state: str | None = None) -> list[Item]:
        query = "SELECT * FROM items"
        params: list[Any] = []
        if state is not None:
            query += " WHERE state = ?"
            params.append(normalize_state(state))
        query += " ORDER BY created_at ASC, id ASC"

        with connect(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()
        return [self._row_to_item(row) for row in rows]

    def list_item_events(
        self,
        item_id: str,
        *,
        event_type: str | None = None,
        limit: int | None = None,
    ) -> list[ItemEvent]:
        """Return the canonical bounded event history view for item inspection.

        This is the single retrieval/order authority used by the CLI `show` path:
        repository-level filtering, newest-first bounded selection, same-timestamp
        row-recency tiebreaking, malformed-payload truth labeling, then reversal into
        chronological operator display order.
        """
        query = """
            SELECT event_id, event_type, payload_json, actor, source, session_id, created_at
            FROM events
            WHERE item_id = ?
        """
        params: list[Any] = [item_id]
        if event_type is not None:
            query += " AND event_type = ?"
            params.append(event_type)
        # Same-timestamp ordering authority is storage-row recency, not lexical event_id.
        # We fetch newest-first using the autoincrement row id as the stable tiebreak,
        # then reverse the bounded result for chronological operator display.
        query += " ORDER BY created_at DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with connect(self.db_path) as connection:
            rows = connection.execute(query, params).fetchall()

        rows = list(reversed(rows))

        events: list[ItemEvent] = []
        for row in rows:
            raw_payload = row["payload_json"]
            try:
                parsed = json.loads(raw_payload)
                canonical_payload = json.dumps(parsed, sort_keys=True, separators=(",", ":"))
                payload_status = "parsed"
                payload_json = canonical_payload
                payload_raw = None
            except json.JSONDecodeError:
                payload_status = "malformed"
                payload_json = None
                payload_raw = raw_payload

            events.append(
                ItemEvent(
                    event_id=row["event_id"],
                    event_type=row["event_type"],
                    created_at=row["created_at"],
                    actor=row["actor"],
                    source=row["source"],
                    session_id=row["session_id"],
                    payload_status=payload_status,
                    payload_json=payload_json,
                    payload_raw=payload_raw,
                )
            )
        return events

    def item_evidence_count(self, item_id: str) -> int:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT id FROM evidence WHERE item_id = ?",
                (item_id,),
            ).fetchall()
        return len(rows)

    def item_open_obligation_count(self, item_id: str) -> int:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT status, satisfied_at FROM obligations WHERE item_id = ?",
                (item_id,),
            ).fetchall()

        count = 0
        for row in rows:
            if row["satisfied_at"] is None and not is_terminal_obligation_status(row["status"]):
                count += 1
        return count

    def item_open_contradiction_count(self, item_id: str) -> int:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT status, resolved_at
                FROM contradictions
                WHERE target_item_id = ?
                """,
                (item_id,),
            ).fetchall()

        count = 0
        for row in rows:
            if row["resolved_at"] is None and not is_terminal_contradiction_status(row["status"]):
                count += 1
        return count

    def apply_action(
        self,
        item_id: str,
        action: str,
        *,
        actor: str | None = None,
        source: str | None = None,
        source_session: str | None = None,
        reason: str | None = None,
    ) -> Item:
        updated_at = utc_now()
        normalized_action = normalize_action(action)
        closeout_item: Item | None = None
        with connect(self.db_path) as connection:
            row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise KeyError(f"unknown item_id: {item_id}")

            previous_state = row["state"]
            target_state = next_state(previous_state, normalized_action)

            if previous_state == "CLAIMED_DONE" and normalized_action == "resolve":
                closeout_item = self._finalize_closeout(
                    connection,
                    item_id=item_id,
                    previous_state=previous_state,
                    target_state=target_state,
                    actor=actor,
                    source=source,
                    source_session=source_session,
                    reason=reason,
                    updated_at=updated_at,
                )
            else:
                event_id = append_event(
                    connection,
                    event_type="item.state_changed",
                    payload=_state_changed_payload(
                        item_id=item_id,
                        previous_state=previous_state,
                        target_state=target_state,
                        action=normalized_action,
                        reason=reason,
                    ),
                    item_id=item_id,
                    actor=actor,
                    source=source,
                    session_id=source_session,
                    created_at=updated_at,
                )
                connection.execute(
                    """
                    UPDATE items
                    SET state = ?, updated_at = ?, last_event_id = ?
                    WHERE id = ?
                    """,
                    (target_state, updated_at, event_id, item_id),
                )
                connection.commit()
                final_row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
                assert final_row is not None, "item update failed unexpectedly"
                return self._row_to_item(final_row)

        if closeout_item is not None:
            return closeout_item
        raise AssertionError("apply_action reached unreachable path")

    def _finalize_closeout(
        self,
        connection: sqlite3.Connection,
        *,
        item_id: str,
        previous_state: str,
        target_state: str,
        actor: str | None,
        source: str | None,
        source_session: str | None,
        reason: str | None,
        updated_at: str,
    ) -> Item:
        """Execute the canonical closeout transition from CLAIMED_DONE to VERIFIED_DONE.

        This is the single repository execution boundary for closeout: gather gate inputs
        from repository evidence/obligation/contradiction authorities, persist the
        `item.closeout_attempted` event and `closeout_runs` ledger row, enforce the
        workflow closeout gate, then emit the final state-change event only on pass.
        """
        evidence_count = self.item_evidence_count(item_id)
        open_obligation_count = self.item_open_obligation_count(item_id)
        contradiction_count = self.item_open_contradiction_count(item_id)

        passed, failure_code, failure_detail = closeout_gate(
            evidence_count,
            open_obligation_count,
            contradiction_count,
        )
        run_id = new_id("closeout")
        attempt_event_id = append_event(
            connection,
            event_type="item.closeout_attempted",
            payload=_closeout_attempted_payload(
                item_id=item_id,
                previous_state=previous_state,
                target_state=target_state,
                reason=reason,
                evidence_count=evidence_count,
                open_obligation_count=open_obligation_count,
                open_contradiction_count=contradiction_count,
                passed=passed,
                failure_code=failure_code,
                failure_detail=failure_detail,
            ),
            item_id=item_id,
            actor=actor,
            source=source,
            session_id=source_session,
            created_at=updated_at,
        )
        connection.execute(
            """
            INSERT INTO closeout_runs (
                id, item_id, requested_state, result, failure_code, failure_detail,
                evidence_count, open_obligation_count, open_contradiction_count, created_at, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                item_id,
                target_state,
                "passed" if passed else "blocked",
                failure_code,
                failure_detail,
                evidence_count,
                open_obligation_count,
                contradiction_count,
                updated_at,
                updated_at,
            ),
        )

        if not passed:
            connection.commit()
            raise CloseoutGateError(f"{failure_code}: {failure_detail}")

        state_event_id = append_event(
            connection,
            event_type="item.state_changed",
            payload=_state_changed_payload(
                item_id=item_id,
                previous_state=previous_state,
                target_state=target_state,
                action="resolve",
                reason=reason,
                closeout_run_id=run_id,
                closeout_event_id=attempt_event_id,
            ),
            item_id=item_id,
            actor=actor,
            source=source,
            session_id=source_session,
            created_at=updated_at,
        )
        connection.execute(
            """
            UPDATE items
            SET state = ?, updated_at = ?, last_event_id = ?
            WHERE id = ?
            """,
            (target_state, updated_at, state_event_id, item_id),
        )
        connection.execute(
            "UPDATE closeout_runs SET result = ?, completed_at = ? WHERE id = ?",
            ("passed", updated_at, run_id),
        )
        connection.commit()

        final_row = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        assert final_row is not None, "closeout update failed unexpectedly"
        return self._row_to_item(final_row)

    @staticmethod
    def _row_to_item(row: Any) -> Item:
        return Item(
            id=row["id"],
            item_type=row["item_type"],
            title=row["title"],
            description=row["description"],
            state=row["state"],
            priority_hint=row["priority_hint"],
            confidence_tier=row["confidence_tier"],
            verdict=row["verdict"],
            source=row["source"],
            source_session=row["source_session"],
            deadline_at=row["deadline_at"],
            owner=row["owner"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            closed_at=row["closed_at"],
            closed_by=row["closed_by"],
            closed_reason=row["closed_reason"],
            last_event_id=row["last_event_id"],
        )
