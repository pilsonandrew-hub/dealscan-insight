from __future__ import annotations

from pathlib import Path
from typing import Any

from ace.storage import connect_readonly
from ace.workflow import is_terminal_obligation_status


def load_stale_resume_contexts(
    db_path: Path | str,
    stale_rows: list[dict[str, object]],
) -> dict[str, dict[str, Any]]:
    if not stale_rows:
        return {}
    item_ids = [str(row["item_id"]) for row in stale_rows]
    contexts: dict[str, dict[str, Any]] = {
        str(row["item_id"]): {
            "item_id": str(row["item_id"]),
            "current_state": str(row["state"]),
            "days_idle": int(row["days_idle"]),
            "events": [],
            "obligations": [],
        }
        for row in stale_rows
    }
    placeholders = ",".join("?" for _ in item_ids)
    with connect_readonly(db_path) as connection:
        item_rows = connection.execute(
            f"""
            SELECT id, state, title
            FROM items
            WHERE id IN ({placeholders})
            """,
            item_ids,
        ).fetchall()
        for row in item_rows:
            item_id = str(row["id"])
            if item_id in contexts:
                contexts[item_id]["current_state"] = str(row["state"])
                contexts[item_id]["title"] = str(row["title"])

        event_rows = connection.execute(
            f"""
            SELECT item_id, event_type, created_at
            FROM events
            WHERE item_id IN ({placeholders})
            ORDER BY item_id ASC, created_at DESC, event_id DESC
            """,
            item_ids,
        ).fetchall()
        event_counts: dict[str, int] = {}
        for row in event_rows:
            item_id = str(row["item_id"])
            if item_id not in contexts:
                continue
            seen = event_counts.get(item_id, 0)
            if seen >= 3:
                continue
            contexts[item_id]["events"].append(
                {
                    "event_type": str(row["event_type"]),
                    "created_at": str(row["created_at"]),
                }
            )
            event_counts[item_id] = seen + 1

        obligation_rows = connection.execute(
            f"""
            SELECT item_id, obligation_type, status, notes
            FROM obligations
            WHERE item_id IN ({placeholders})
            ORDER BY item_id ASC, created_at ASC, id ASC
            """,
            item_ids,
        ).fetchall()
        for row in obligation_rows:
            item_id = str(row["item_id"])
            if item_id not in contexts:
                continue
            status = str(row["status"])
            if is_terminal_obligation_status(status):
                continue
            contexts[item_id]["obligations"].append(
                {
                    "obligation_type": str(row["obligation_type"]),
                    "status": status,
                    "notes": str(row["notes"]) if row["notes"] is not None else None,
                }
            )
    return contexts


def _short_item_id(item_id: str) -> str:
    if len(item_id) <= 20:
        return item_id
    return f"{item_id[:8]}...{item_id[-8:]}"


def _format_event_line(event: dict[str, Any]) -> str:
    created_at = str(event["created_at"])
    if "T" in created_at:
        created_at = created_at.split("T", 1)[0]
    return f"  - {created_at} {event['event_type']}"


def _format_obligation_line(obligation: dict[str, Any]) -> str:
    notes = obligation.get("notes")
    detail = f" ({notes})" if notes else ""
    return f"  - {obligation['obligation_type']} [{obligation['status']}]{detail}"


def render_stale_resume_context(
    stale_rows: list[dict[str, object]],
    contexts: dict[str, dict[str, Any]],
) -> str:
    if not stale_rows:
        return ""
    blocks: list[str] = ["", "Stale item resume context:"]
    for row in stale_rows:
        item_id = str(row["item_id"])
        context = contexts.get(item_id)
        if context is None:
            continue
        label = _short_item_id(item_id)
        blocks.append(
            f"{label} — state {context['current_state']}, {int(row['days_idle'])}d idle"
        )
        events = context.get("events") or []
        if events:
            blocks.append("events (latest 3):")
            blocks.extend(_format_event_line(event) for event in events)
        else:
            blocks.append("events (latest 3): none")
        obligations = context.get("obligations") or []
        if obligations:
            blocks.append("obligations (open):")
            blocks.extend(_format_obligation_line(obligation) for obligation in obligations)
        else:
            blocks.append("obligations (open): none")
        blocks.append("")
    if blocks and blocks[-1] == "":
        blocks.pop()
    return "\n".join(blocks)
