from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(__file__).resolve().parents[1] / "state" / "ace.db"
REQUIRED_CREATED_FIELDS = (
    "source_message_text",
    "source_message_id",
    "source_chat_id",
    "source_received_at",
    "parser_rule",
    "parser_reason",
    "intake_actor",
)
REQUIRED_EVIDENCE_URIS = (
    "ace://telegram/intake-source",
    "ace://telegram/parser-decision",
    "ace://autonomy/eligible-direct-work",
)
ALLOWED_AUTONOMOUS_ACTORS = {"launchd", "ace.autonomy_lane", "ace-runtime"}
CHEAT_MARKERS = (
    "intake-direct-work",
    "manual",
    "proof seeding",
    "seeded",
)
CLOSEOUT_EVIDENCE_URIS = {
    "ace://autonomy/explicit-direct-work-closeout",
    "ace://autonomy/machine-verifiable-closeout",
}


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def _load_item(connection: sqlite3.Connection, source_session: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM items WHERE source = ? AND source_session = ?",
        ("telegram/direct", source_session),
    ).fetchone()


def _load_events(connection: sqlite3.Connection, item_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM events WHERE item_id = ? ORDER BY created_at ASC, id ASC",
        (item_id,),
    ).fetchall()


def _load_evidence(connection: sqlite3.Connection, item_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        "SELECT * FROM evidence WHERE item_id = ? ORDER BY created_at ASC, id ASC",
        (item_id,),
    ).fetchall()


def _load_live_runtime(connection: sqlite3.Connection) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT *
        FROM runtime_instances
        WHERE status = 'live'
        ORDER BY created_at DESC, runtime_instance_id DESC
        LIMIT 1
        """
    ).fetchone()


def _parse_payload(row: sqlite3.Row) -> dict[str, Any]:
    try:
        payload = json.loads(row["payload_json"])
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _check(condition: bool, label: str, detail: str) -> tuple[bool, str, str]:
    return condition, label, detail


def _check_created_payload(created_event: sqlite3.Row | None) -> tuple[list[tuple[bool, str, str]], dict[str, Any]]:
    if created_event is None:
        return [
            _check(False, "item.created event", "missing item.created event"),
        ], {}

    payload = _parse_payload(created_event)
    results = [_check(True, "item.created event", f"event_id={created_event['event_id']} present")]
    for field in REQUIRED_CREATED_FIELDS:
        value = payload.get(field)
        results.append(_check(bool(value), f"created payload.{field}", "present" if value else "missing"))
    return results, payload


def _check_source_session_matches(source_session: str, payload: dict[str, Any]) -> tuple[bool, str, str]:
    chat_id = str(payload.get("source_chat_id") or "").strip()
    message_id = str(payload.get("source_message_id") or "").strip()
    expected = f"telegram:{chat_id}:{message_id}" if chat_id and message_id else ""
    return _check(expected == source_session, "source_session provenance", f"expected={expected or '[missing]'} actual={source_session}")


def _check_required_evidence(evidence_rows: list[sqlite3.Row]) -> list[tuple[bool, str, str]]:
    seen = {row["evidence_uri"] for row in evidence_rows}
    return [
        _check(uri in seen, f"evidence {uri}", "present" if uri in seen else "missing")
        for uri in REQUIRED_EVIDENCE_URIS
    ]


def _check_cheat_markers(events: list[sqlite3.Row], evidence_rows: list[sqlite3.Row]) -> tuple[bool, str, str]:
    haystacks: list[str] = []
    for row in events:
        haystacks.append(str(row["event_type"] or ""))
        haystacks.append(str(row["actor"] or ""))
        haystacks.append(str(row["source"] or ""))
        haystacks.append(str(row["session_id"] or ""))
        haystacks.append(str(row["payload_json"] or ""))
    for row in evidence_rows:
        haystacks.append(str(row["evidence_text"] or ""))
        haystacks.append(str(row["evidence_uri"] or ""))
        haystacks.append(str(row["created_by"] or ""))
    lowered = "\n".join(haystacks).lower()
    hits = [marker for marker in CHEAT_MARKERS if marker in lowered]
    return _check(not hits, "anti-cheat markers", "clear" if not hits else f"hits={', '.join(hits)}")


def _check_progression(events: list[sqlite3.Row], created_event_id: str | None) -> list[tuple[bool, str, str]]:
    state_events = [row for row in events if row["event_type"] == "item.state_changed"]
    closeout_events = [row for row in events if row["event_type"] == "item.closeout_attempted"]
    results = [
        _check(bool(state_events), "state progression", f"state_changes={len(state_events)}"),
        _check(bool(closeout_events), "closeout attempted", f"closeout_events={len(closeout_events)}"),
    ]
    if created_event_id is None:
        return results

    seen_created = False
    bad_actors: list[str] = []
    for row in events:
        if row["event_id"] == created_event_id:
            seen_created = True
            continue
        if not seen_created:
            continue
        if row["event_type"] not in {"item.state_changed", "item.closeout_attempted", "item.evidence_added"}:
            continue
        actor = str(row["actor"] or "")
        if row["event_type"] == "item.evidence_added":
            if actor in {"ace.telegram_intake", "ace.telegram_parser", "ace.autonomy_lane", "launchd", "ace-runtime"}:
                continue
        elif actor in ALLOWED_AUTONOMOUS_ACTORS:
            continue
        bad_actors.append(f"{row['event_type']}:{actor or '[missing]'}")
    results.append(_check(not bad_actors, "autonomous actor chain", "valid" if not bad_actors else "; ".join(bad_actors)))
    return results


def _check_final_state(item: sqlite3.Row) -> tuple[bool, str, str]:
    return _check(item["state"] == "VERIFIED_DONE", "final state", f"state={item['state']}")


def _check_closeout_evidence(evidence_rows: list[sqlite3.Row]) -> tuple[bool, str, str]:
    matches = [row["evidence_uri"] for row in evidence_rows if row["evidence_uri"] in CLOSEOUT_EVIDENCE_URIS]
    return _check(bool(matches), "closeout evidence", "present" if matches else "missing")


def _check_live_runtime(runtime_row: sqlite3.Row | None) -> tuple[bool, str, str]:
    if runtime_row is None:
        return _check(False, "live runtime", "no live runtime instance")
    return _check(True, "live runtime", f"runtime_instance_id={runtime_row['runtime_instance_id']}")


def certify(source_session: str, db_path: Path) -> int:
    with _connect(db_path) as connection:
        item = _load_item(connection, source_session)
        if item is None:
            print(f"FAIL item lookup :: no telegram/direct item for source_session={source_session}")
            return 1

        events = _load_events(connection, item["id"])
        evidence_rows = _load_evidence(connection, item["id"])
        runtime_row = _load_live_runtime(connection)

    created_event = next((row for row in events if row["event_type"] == "item.created"), None)
    results: list[tuple[bool, str, str]] = []
    created_results, created_payload = _check_created_payload(created_event)
    results.extend(created_results)
    results.append(_check_source_session_matches(source_session, created_payload))
    results.extend(_check_required_evidence(evidence_rows))
    results.append(_check_cheat_markers(events, evidence_rows))
    results.extend(_check_progression(events, created_event["event_id"] if created_event is not None else None))
    results.append(_check_final_state(item))
    results.append(_check_closeout_evidence(evidence_rows))
    results.append(_check_live_runtime(runtime_row))

    overall_ok = all(result[0] for result in results)
    for ok, label, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {label} :: {detail}")

    print("--- summary ---")
    print(f"source_session={source_session}")
    print(f"item_id={item['id']}")
    print(f"title={item['title']}")
    print(f"final_state={item['state']}")
    print(f"source_text={created_payload.get('source_message_text')}")
    print(f"parser_rule={created_payload.get('parser_rule')}")
    print(f"parser_reason={created_payload.get('parser_reason')}")
    if runtime_row is not None:
        print(f"runtime_instance_id={runtime_row['runtime_instance_id']}")

    print("PASS" if overall_ok else "FAIL")
    return 0 if overall_ok else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Certify a bounded V2 Telegram direct-work provenance chain."
    )
    parser.add_argument("source_session_arg", nargs="?", help="Source session to certify, e.g. telegram:7529788084:33604")
    parser.add_argument("db_path_arg", nargs="?", help="Optional ACE SQLite DB path")
    parser.add_argument("--source-session", dest="source_session_flag")
    parser.add_argument("--db-path", dest="db_path_flag")
    args = parser.parse_args(argv[1:])

    source_session = args.source_session_flag or args.source_session_arg
    if not source_session:
        parser.error("source session is required, either positional or --source-session")

    if args.source_session_flag and args.source_session_arg:
        parser.error("source session was provided both positionally and via --source-session")

    db_path_text = args.db_path_flag or args.db_path_arg
    db_path = Path(db_path_text) if db_path_text else DEFAULT_DB
    return certify(source_session, db_path)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
