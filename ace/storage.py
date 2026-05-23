from __future__ import annotations

import hashlib
import json
import subprocess
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ACE_DIR = Path(__file__).resolve().parent
STATE_DIR = ACE_DIR / "state"
DB_PATH = STATE_DIR / "ace.db"
CUTOVER_EVENT_TYPE = "ace.chain.cutover.v1_1"
CUTOVER_EXECUTE_AUTHORIZATION_TOKEN = "B_CUTOVER_EXECUTE_OPERATOR_APPROVED"
DESIGN_COMMIT_HASH = "58725a87f52a734c13e12c18e17e29534cd0fc72"
LEGACY_CHAIN_DISCLOSURE_PATH = ACE_DIR / "state" / "v1_1_required_items" / "legacy-chain-defects.md"
LEGACY_CHAIN_DIAGNOSIS_PATH = ACE_DIR / "state" / "v1_1_required_items" / "slice-b1-chain-diagnosis-readonly.md"
LEGACY_KNOWN_DEFECT_COUNTS = {
    "backdated_item_created_events": 4,
    "concurrent_write_chain_breaks": 2,
    "timestamp_id_inversions": 163,
}
POST_CUTOVER_CHAIN_POLICY = {
    "event_sequence_scope": "post_cutover_only",
    "post_cutover_serialization": "begin_immediate_required_before_head_read",
    "pre_cutover_verification_policy": "inventory_only_disclosed_defects",
    "previous_event_hash_policy": "v1_1_genesis_null_with_legacy_head_in_payload",
    "transition_window_policy": "sequence_null_legacy_mode_until_cutover",
}
REQUIRED_CUTOVER_PAYLOAD_FIELDS = frozenset(
    {
        "anchor_commit_hash",
        "cutover_timestamp",
        "cutover_version",
        "design_commit_hash",
        "forbidden_claims_reference",
        "governing_decision",
        "governing_decision_reference",
        "legacy_chain_head_event_id",
        "legacy_chain_head_hash",
        "legacy_chain_head_row_id",
        "legacy_diagnosis_path",
        "legacy_disclosure_path",
        "legacy_event_count",
        "legacy_known_defect_counts",
        "post_cutover_chain_policy",
    }
)
_IMMEDIATE_CONNECTION_IDS: set[int] = set()


# Schema presence is not runtime proof. Some tables, including action_queue,
# are durable storage surfaces reserved for later execution-capable behavior,
# but their existence alone does not mean enqueue/claim/complete semantics are
# implemented in the current repository or CLI contract.
SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY,
        item_type TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        state TEXT NOT NULL,
        priority_hint TEXT,
        confidence_tier TEXT,
        verdict TEXT,
        source TEXT,
        source_session TEXT,
        deadline_at TEXT,
        owner TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        closed_at TEXT,
        closed_by TEXT,
        closed_reason TEXT,
        last_event_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE,
        item_id TEXT,
        event_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        actor TEXT,
        source TEXT,
        session_id TEXT,
        created_at TEXT NOT NULL,
        previous_event_hash TEXT,
        event_hash TEXT,
        event_sequence INTEGER,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        evidence_uri TEXT,
        created_by TEXT,
        created_at TEXT NOT NULL,
        event_id TEXT,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
        FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS action_queue (
        id TEXT PRIMARY KEY,
        item_id TEXT,
        action_type TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        status TEXT NOT NULL,
        priority INTEGER NOT NULL DEFAULT 0,
        scheduled_at TEXT,
        claimed_at TEXT,
        completed_at TEXT,
        error_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS obligations (
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        obligation_type TEXT NOT NULL,
        target_surface TEXT,
        status TEXT NOT NULL,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        satisfied_at TEXT,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS closeout_runs (
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        requested_state TEXT NOT NULL,
        result TEXT NOT NULL,
        failure_code TEXT,
        failure_detail TEXT,
        evidence_count INTEGER NOT NULL DEFAULT 0,
        open_obligation_count INTEGER NOT NULL DEFAULT 0,
        open_contradiction_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_candidates (
        id TEXT PRIMARY KEY,
        item_id TEXT NOT NULL,
        score REAL NOT NULL,
        reason_json TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        sweep_run_id TEXT,
        FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
    )
    """,
    # Current truth: resume_candidates is a durable storage and migration surface.
    # The live code evidenced here proves schema shape, repair, and writability, but
    # does not yet prove a runtime generation, ranking, or consumption contract.
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        session_key TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL,
        metadata_json TEXT NOT NULL,
        started_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        ended_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS contradictions (
        id TEXT PRIMARY KEY,
        source_item_id TEXT NOT NULL,
        target_item_id TEXT NOT NULL,
        status TEXT NOT NULL,
        reason TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT,
        FOREIGN KEY (source_item_id) REFERENCES items(id) ON DELETE CASCADE,
        FOREIGN KEY (target_item_id) REFERENCES items(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS governed_runs (
        run_id TEXT PRIMARY KEY,
        run_kind TEXT NOT NULL,
        trigger_kind TEXT NOT NULL,
        status TEXT NOT NULL,
        briefing_path TEXT,
        notification_action_id TEXT,
        delivery_evidence_id TEXT,
        created_at TEXT NOT NULL,
        started_at TEXT,
        ended_at TEXT,
        interrupted_at TEXT,
        failure_code TEXT,
        failure_summary TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cost_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recorded_at TEXT NOT NULL,
        cost_cents INTEGER NOT NULL DEFAULT 0,
        tokens INTEGER NOT NULL DEFAULT 0,
        session_count INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL,
        source_session TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_log (
        id TEXT PRIMARY KEY,
        alert_type TEXT NOT NULL,
        transport TEXT NOT NULL,
        bot_username TEXT,
        chat_id TEXT NOT NULL,
        message_id TEXT NOT NULL,
        delivery_state TEXT NOT NULL,
        sent_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_instances (
        runtime_instance_id TEXT PRIMARY KEY,
        runtime_family TEXT NOT NULL,
        status TEXT NOT NULL,
        host_identity TEXT,
        metadata_json TEXT NOT NULL,
        stale_after_seconds INTEGER NOT NULL,
        started_at TEXT NOT NULL,
        last_seen_at TEXT NOT NULL,
        ended_at TEXT,
        failure_code TEXT,
        failure_summary TEXT,
        failure_phase TEXT,
        startup_status TEXT NOT NULL DEFAULT 'starting',
        startup_completed_at TEXT,
        shutdown_status TEXT NOT NULL DEFAULT 'not_requested',
        shutdown_requested_at TEXT,
        shutdown_completed_at TEXT,
        recovery_status TEXT NOT NULL DEFAULT 'not_requested',
        recovery_attempt_count INTEGER NOT NULL DEFAULT 0,
        recovery_last_requested_at TEXT,
        recovery_last_completed_at TEXT,
        recovery_last_result TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_items_state ON items(state)",
    "CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_items_source_session_unique
    ON items(source, source_session)
    WHERE source IS NOT NULL AND source_session IS NOT NULL
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_action_queue_status ON action_queue(status)",
    "CREATE INDEX IF NOT EXISTS idx_obligations_item_status ON obligations(item_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_resume_candidates_score ON resume_candidates(score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_source ON contradictions(source_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_target ON contradictions(target_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_governed_runs_status_created_at ON governed_runs(status, created_at DESC, run_id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_alert_log_sent_at ON alert_log(sent_at DESC, id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runtime_instances_family_status_created_at ON runtime_instances(runtime_family, status, created_at DESC, runtime_instance_id DESC)",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _event_hash_payload(
    *,
    event_id: str,
    item_id: str | None,
    event_type: str,
    payload_json: str,
    actor: str | None,
    source: str | None,
    session_id: str | None,
    created_at: str,
    previous_event_hash: str | None,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "item_id": item_id,
        "event_type": event_type,
        "payload_json": payload_json,
        "actor": actor,
        "source": source,
        "session_id": session_id,
        "created_at": created_at,
        "previous_event_hash": previous_event_hash,
    }


def compute_event_hash(
    *,
    event_id: str,
    item_id: str | None,
    event_type: str,
    payload_json: str,
    actor: str | None,
    source: str | None,
    session_id: str | None,
    created_at: str,
    previous_event_hash: str | None,
) -> str:
    canonical_payload = json.dumps(
        _event_hash_payload(
            event_id=event_id,
            item_id=item_id,
            event_type=event_type,
            payload_json=payload_json,
            actor=actor,
            source=source,
            session_id=session_id,
            created_at=created_at,
            previous_event_hash=previous_event_hash,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()


def _deny_event_update_delete_authorizer(action_code, arg1, arg2, _database_name, _trigger_name):
    if action_code in {sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE} and arg1 == "events":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _install_event_write_authorizer(connection: sqlite3.Connection) -> None:
    connection.set_authorizer(_deny_event_update_delete_authorizer)


def _clear_authorizer(connection: sqlite3.Connection) -> None:
    connection.set_authorizer(None)


def _begin_immediate(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise RuntimeError("BEGIN IMMEDIATE required before any DML in append-capable write path")
    connection.execute("BEGIN IMMEDIATE")
    _IMMEDIATE_CONNECTION_IDS.add(id(connection))


def _assert_immediate_write_connection(connection: sqlite3.Connection) -> None:
    if not connection.in_transaction:
        _begin_immediate(connection)


def _current_git_commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ACE_DIR.parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("unable to resolve current git commit hash for cutover payload") from exc


def _validate_cutover_payload(payload: Mapping[str, Any]) -> None:
    missing = sorted(REQUIRED_CUTOVER_PAYLOAD_FIELDS.difference(payload))
    if missing:
        raise ValueError(f"cutover payload missing required fields: {', '.join(missing)}")
    if payload.get("cutover_version") != "v1.1":
        raise ValueError("cutover payload cutover_version must be v1.1")
    if payload.get("design_commit_hash") != DESIGN_COMMIT_HASH:
        raise ValueError("cutover payload design_commit_hash mismatch")
    if payload.get("legacy_known_defect_counts") != LEGACY_KNOWN_DEFECT_COUNTS:
        raise ValueError("cutover payload legacy_known_defect_counts mismatch")
    if payload.get("post_cutover_chain_policy") != POST_CUTOVER_CHAIN_POLICY:
        raise ValueError("cutover payload post_cutover_chain_policy mismatch")


@contextmanager
def connect(db_path: Path | str = DB_PATH):
    connection = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        _install_event_write_authorizer(connection)
        yield connection
    finally:
        _IMMEDIATE_CONNECTION_IDS.discard(id(connection))
        connection.close()


@contextmanager
def connect_readonly(db_path: Path | str = DB_PATH):
    connection = sqlite3.connect(f"file:{Path(db_path)}?mode=ro", uri=True, timeout=30.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def _install_event_append_only_triggers(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS ace_events_no_update
        BEFORE UPDATE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events table is append-only; update denied');
        END
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS ace_events_no_delete
        BEFORE DELETE ON events
        BEGIN
            SELECT RAISE(ABORT, 'events table is append-only; delete denied');
        END
        """
    )


def _drop_event_append_only_triggers_for_maintenance(connection: sqlite3.Connection) -> None:
    connection.execute("DROP TRIGGER IF EXISTS ace_events_no_update")
    connection.execute("DROP TRIGGER IF EXISTS ace_events_no_delete")


def _event_columns(connection: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in connection.execute("PRAGMA table_info(events)").fetchall()}


def _event_sequence_column_nullable(connection: sqlite3.Connection) -> bool:
    for row in connection.execute("PRAGMA table_info(events)").fetchall():
        if row["name"] == "event_sequence":
            return row["notnull"] == 0
    return True


def _event_sequence_indexes(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    indexes: list[sqlite3.Row] = []
    for index_row in connection.execute("PRAGMA index_list(events)").fetchall():
        index_name = index_row["name"]
        indexed_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA index_info({index_name})").fetchall()
        }
        if "event_sequence" in indexed_columns:
            indexes.append(index_row)
    return indexes


def _rebuild_events_for_nullable_event_sequence(connection: sqlite3.Connection) -> None:
    connection.execute("ALTER TABLE events RENAME TO events_legacy_event_sequence")
    connection.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL UNIQUE,
            item_id TEXT,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            actor TEXT,
            source TEXT,
            session_id TEXT,
            created_at TEXT NOT NULL,
            previous_event_hash TEXT,
            event_hash TEXT,
            event_sequence INTEGER,
            FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE SET NULL
        )
        """
    )
    legacy_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(events_legacy_event_sequence)").fetchall()
    }
    event_sequence_select = "event_sequence" if "event_sequence" in legacy_columns else "NULL"
    connection.execute(
        f"""
        INSERT INTO events (
            id, event_id, item_id, event_type, payload_json, actor, source, session_id,
            created_at, previous_event_hash, event_hash, event_sequence
        )
        SELECT
            id, event_id, item_id, event_type, payload_json, actor, source, session_id,
            created_at, previous_event_hash, event_hash, {event_sequence_select}
        FROM events_legacy_event_sequence
        ORDER BY id ASC
        """
    )
    connection.execute("DROP TABLE events_legacy_event_sequence")


def _ensure_event_sequence_column(connection: sqlite3.Connection) -> None:
    columns = _event_columns(connection)
    if not columns:
        return
    sequence_indexes = _event_sequence_indexes(connection) if "event_sequence" in columns else []
    for index_row in sequence_indexes:
        if index_row["unique"]:
            connection.execute(f"DROP INDEX IF EXISTS {index_row['name']}")
    if "event_sequence" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN event_sequence INTEGER")
    elif not _event_sequence_column_nullable(connection):
        _rebuild_events_for_nullable_event_sequence(connection)


def _ensure_event_hash_columns(connection: sqlite3.Connection) -> None:
    columns = _event_columns(connection)
    if not columns:
        return
    if "previous_event_hash" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN previous_event_hash TEXT")
    if "event_hash" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")


def _backfill_event_hashes(connection: sqlite3.Connection) -> None:
    _ensure_event_hash_columns(connection)
    columns = _event_columns(connection)
    if not {"previous_event_hash", "event_hash"}.issubset(columns):
        return

    missing = connection.execute(
        "SELECT COUNT(*) AS count FROM events WHERE previous_event_hash IS NULL AND event_hash IS NULL"
    ).fetchone()["count"]
    if not missing:
        return

    first_missing = connection.execute(
        "SELECT MIN(id) AS id FROM events WHERE previous_event_hash IS NULL AND event_hash IS NULL"
    ).fetchone()["id"]
    previous_event_hash = connection.execute(
        "SELECT event_hash FROM events WHERE id < ? ORDER BY id DESC LIMIT 1",
        (first_missing,),
    ).fetchone()
    previous_hash = previous_event_hash["event_hash"] if previous_event_hash else None
    rows = connection.execute(
        """
        SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
               created_at
        FROM events
        WHERE previous_event_hash IS NULL AND event_hash IS NULL
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        expected_hash = compute_event_hash(
            event_id=row["event_id"],
            item_id=row["item_id"],
            event_type=row["event_type"],
            payload_json=row["payload_json"],
            actor=row["actor"],
            source=row["source"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            previous_event_hash=previous_hash,
        )
        connection.execute(
            "UPDATE events SET previous_event_hash = ?, event_hash = ? WHERE id = ?",
            (previous_hash, expected_hash, row["id"]),
        )
        previous_hash = expected_hash


def _schema_ready_for_readonly_audit(connection: sqlite3.Connection) -> tuple[bool, str | None]:
    required_tables = {"events", "evidence", "items", "governed_runs", "runtime_instances"}
    existing_tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    missing_tables = sorted(required_tables - existing_tables)
    if missing_tables:
        return False, (
            "schema maintenance required before audit verify: missing tables "
            + ",".join(missing_tables)
            + "; run explicit ACE maintenance migration/bootstrap first"
        )

    event_columns = _event_columns(connection)
    required_event_columns = {"previous_event_hash", "event_hash", "event_sequence"}
    missing_event_columns = sorted(required_event_columns - event_columns)
    if missing_event_columns:
        return False, (
            "schema maintenance required before audit verify: events missing columns "
            + ",".join(missing_event_columns)
            + "; run explicit ACE maintenance migration/bootstrap first"
        )

    missing_hash_count = connection.execute(
        "SELECT COUNT(*) AS count FROM events WHERE event_hash IS NULL"
    ).fetchone()["count"]
    if missing_hash_count:
        return False, (
            "event hash maintenance required before audit verify: "
            f"{missing_hash_count} event rows lack event_hash; run explicit ACE maintenance migration/bootstrap first"
        )

    return True, None


def _maintenance_required_results(reason: str) -> dict[str, tuple[bool, str | None]]:
    return {
        "legacy_chain_inventory": (False, reason),
        "event_hash_chain": (False, reason),
        "post_cutover_event_hash_chain": (False, reason),
        "evidence_consistency": (False, reason),
        "governed_run_integrity": (False, reason),
        "runtime_instance_integrity": (False, reason),
    }


def _cutover_candidates(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    if "event_sequence" not in _event_columns(connection):
        return []
    rows = connection.execute(
        """
        SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
               created_at, previous_event_hash, event_hash, event_sequence
        FROM events
        WHERE event_type = ?
        ORDER BY id ASC
        """,
        (CUTOVER_EVENT_TYPE,),
    ).fetchall()
    candidates: list[sqlite3.Row] = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = None
        if row["event_sequence"] == 1 and row["previous_event_hash"] is None and isinstance(payload, dict) and payload.get("cutover_version") == "v1.1":
            candidates.append(row)
    return candidates


def _cutover_row(connection: sqlite3.Connection) -> sqlite3.Row | None:
    candidates = _cutover_candidates(connection)
    if len(candidates) == 1:
        return candidates[0]
    return None


def _assert_no_hashless_events_before_append(connection: sqlite3.Connection) -> None:
    columns = _event_columns(connection)
    if not {"previous_event_hash", "event_hash", "event_sequence"}.issubset(columns):
        raise RuntimeError(
            "event hash maintenance required before append: events hash columns missing; "
            "run explicit ACE maintenance migration/bootstrap first"
        )
    missing = connection.execute(
        "SELECT event_id FROM events WHERE event_hash IS NULL ORDER BY id ASC LIMIT 1"
    ).fetchone()
    if missing is not None:
        raise RuntimeError(
            "event hash maintenance required before append: "
            f"event {missing['event_id']} lacks event_hash; run explicit ACE maintenance migration/bootstrap first"
        )


def verify_event_hash_chain(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Return whether the append-only event hash chain is internally consistent."""

    previous_event_hash: str | None = None
    with connect_readonly(db_path) as connection:
        ready, reason = _schema_ready_for_readonly_audit(connection)
        if not ready:
            return False, reason
        rows = connection.execute(
            """
            SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
                   created_at, previous_event_hash, event_hash
            FROM events
            ORDER BY id ASC
            """
        ).fetchall()

    for row in rows:
        if row["previous_event_hash"] != previous_event_hash:
            return False, f"event {row['event_id']} has broken previous_event_hash"
        expected_hash = compute_event_hash(
            event_id=row["event_id"],
            item_id=row["item_id"],
            event_type=row["event_type"],
            payload_json=row["payload_json"],
            actor=row["actor"],
            source=row["source"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            previous_event_hash=previous_event_hash,
        )
        if row["event_hash"] != expected_hash:
            return False, f"event {row['event_id']} hash mismatch"
        previous_event_hash = row["event_hash"]
    return True, None


def _verify_event_hash_chain_bootstrapped(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    return verify_event_hash_chain(db_path)


def legacy_chain_inventory(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Report disclosed legacy chain state without treating legacy defects as a pass."""

    if not LEGACY_CHAIN_DISCLOSURE_PATH.exists():
        return False, f"legacy chain disclosure missing: {LEGACY_CHAIN_DISCLOSURE_PATH}"
    with connect_readonly(db_path) as connection:
        candidates = _cutover_candidates(connection)
        if len(candidates) == 0:
            return True, "legacy_chain_inventory=pre_cutover disclosure_present=true cutover_event=absent"
        if len(candidates) != 1:
            return False, "cutover boundary missing or ambiguous"
        cutover = candidates[0]
        try:
            payload = json.loads(cutover["payload_json"])
        except json.JSONDecodeError:
            return False, f"cutover event {cutover['event_id']} payload malformed"
        legacy_head = connection.execute(
            "SELECT id, event_id, event_hash FROM events WHERE id < ? ORDER BY id DESC LIMIT 1",
            (cutover["id"],),
        ).fetchone()
        if legacy_head is None:
            return False, f"cutover event {cutover['event_id']} has no legacy head to inventory"
        if payload.get("legacy_chain_head_row_id") != legacy_head["id"]:
            return False, f"cutover event {cutover['event_id']} legacy head row mismatch"
        if payload.get("legacy_chain_head_event_id") != legacy_head["event_id"]:
            return False, f"cutover event {cutover['event_id']} legacy head event mismatch"
        if payload.get("legacy_chain_head_hash") != legacy_head["event_hash"]:
            return False, f"cutover event {cutover['event_id']} legacy head hash mismatch"
        return True, f"legacy_chain_inventory=disclosed cutover_event_id={cutover['event_id']} legacy_policy=inventory_only_disclosed_defects"


def post_cutover_event_hash_chain(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Strict V1.1+ hash-chain verification from the cutover boundary forward."""

    with connect_readonly(db_path) as connection:
        candidates = _cutover_candidates(connection)
        if len(candidates) != 1:
            return False, "cutover boundary missing or ambiguous"
        cutover = candidates[0]
        null_row = connection.execute(
            "SELECT event_id FROM events WHERE id >= ? AND event_sequence IS NULL ORDER BY id ASC LIMIT 1",
            (cutover["id"],),
        ).fetchone()
        if null_row is not None:
            return False, f"post-cutover event {null_row['event_id']} has NULL event_sequence"
        duplicate = connection.execute(
            """
            SELECT event_sequence
            FROM events
            WHERE id >= ?
            GROUP BY event_sequence
            HAVING COUNT(*) > 1
            ORDER BY event_sequence ASC
            LIMIT 1
            """,
            (cutover["id"],),
        ).fetchone()
        if duplicate is not None:
            return False, f"duplicate post-cutover event_sequence {duplicate['event_sequence']}"
        rows = connection.execute(
            """
            SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
                   created_at, previous_event_hash, event_hash, event_sequence
            FROM events
            WHERE id >= ?
            ORDER BY event_sequence ASC, id ASC
            """,
            (cutover["id"],),
        ).fetchall()
    for expected_sequence, row in enumerate(rows, start=1):
        if row["event_sequence"] != expected_sequence:
            return False, f"post-cutover event_sequence gap at expected {expected_sequence}"
    previous_event_hash: str | None = None
    for row in rows:
        if row["previous_event_hash"] != previous_event_hash:
            return False, f"post-cutover event {row['event_id']} has broken previous_event_hash"
        expected_hash = compute_event_hash(
            event_id=row["event_id"],
            item_id=row["item_id"],
            event_type=row["event_type"],
            payload_json=row["payload_json"],
            actor=row["actor"],
            source=row["source"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            previous_event_hash=previous_event_hash,
        )
        if row["event_hash"] != expected_hash:
            return False, f"post-cutover event {row['event_id']} hash mismatch"
        previous_event_hash = row["event_hash"]
    return True, None


def verify_audit_integrity(db_path: Path | str = DB_PATH) -> dict[str, tuple[bool, str | None]]:
    """Return read-only audit verification results for governed ACE integrity surfaces."""

    try:
        with connect_readonly(db_path) as connection:
            ready, reason = _schema_ready_for_readonly_audit(connection)
    except sqlite3.OperationalError as exc:
        reason = f"schema maintenance required before audit verify: {exc}; run explicit ACE maintenance migration/bootstrap first"
        return _maintenance_required_results(reason)
    if not ready:
        assert reason is not None
        return _maintenance_required_results(reason)

    with connect_readonly(db_path) as connection:
        cutover_present = bool(_cutover_candidates(connection))
    event_hash_chain_result = post_cutover_event_hash_chain(db_path) if cutover_present else _verify_event_hash_chain_bootstrapped(db_path)
    return {
        "legacy_chain_inventory": legacy_chain_inventory(db_path),
        "event_hash_chain": event_hash_chain_result,
        "post_cutover_event_hash_chain": post_cutover_event_hash_chain(db_path) if cutover_present else (True, "post_cutover_event_hash_chain=not_started cutover_event=absent"),
        "evidence_consistency": _verify_evidence_consistency_bootstrapped(db_path),
        "governed_run_integrity": _verify_governed_run_integrity_bootstrapped(db_path),
        "runtime_instance_integrity": _verify_runtime_instance_integrity_bootstrapped(db_path),
    }


def _verify_evidence_consistency_bootstrapped(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    with connect_readonly(db_path) as connection:
        missing_item = connection.execute(
            """
            SELECT e.id, e.item_id
            FROM evidence e
            LEFT JOIN items i ON i.id = e.item_id
            WHERE i.id IS NULL
            ORDER BY e.id ASC
            LIMIT 1
            """
        ).fetchone()
        if missing_item is not None:
            return False, f"evidence {missing_item['id']} references missing item {missing_item['item_id']}"

        missing_event = connection.execute(
            """
            SELECT ev.id, ev.event_id
            FROM evidence ev
            LEFT JOIN events e ON e.event_id = ev.event_id
            WHERE ev.event_id IS NOT NULL AND e.event_id IS NULL
            ORDER BY ev.id ASC
            LIMIT 1
            """
        ).fetchone()
        if missing_event is not None:
            return False, f"evidence {missing_event['id']} references missing event {missing_event['event_id']}"

    return True, None


def _verify_governed_run_integrity_bootstrapped(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    valid_statuses = {"pending", "starting", "running", "completed", "failed", "interrupted", "skipped"}
    terminal_statuses = {"completed", "failed", "interrupted", "skipped"}
    active_statuses = {"pending", "starting", "running"}

    with connect_readonly(db_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, status, started_at, ended_at, interrupted_at, failure_code
            FROM governed_runs
            ORDER BY created_at ASC, run_id ASC
            """
        ).fetchall()

    for row in rows:
        status = row["status"]
        run_id = row["run_id"]
        if status not in valid_statuses:
            return False, f"governed_run {run_id} has invalid status {status}"
        if status in terminal_statuses and row["ended_at"] is None:
            return False, f"governed_run {run_id} has terminal status {status} without ended_at"
        if status in active_statuses and row["ended_at"] is not None:
            return False, f"governed_run {run_id} has active status {status} with ended_at"
        if status == "interrupted" and row["interrupted_at"] is None:
            return False, f"governed_run {run_id} is interrupted without interrupted_at"
        if status in {"failed", "interrupted", "skipped"} and row["failure_code"] is None:
            return False, f"governed_run {run_id} has status {status} without failure_code"

    return True, None


def _verify_runtime_instance_integrity_bootstrapped(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    valid_statuses = {"starting", "live", "stale", "stopped", "failed"}
    valid_startup = {"starting", "completed", "failed"}
    valid_shutdown = {"not_requested", "requested", "completed", "failed"}
    valid_recovery = {"not_requested", "requested", "completed", "failed"}
    terminal_statuses = {"stopped", "failed"}
    active_statuses = {"starting", "live", "stale"}

    with connect_readonly(db_path) as connection:
        rows = connection.execute(
            """
            SELECT runtime_instance_id, status, ended_at, failure_code,
                   startup_status, startup_completed_at,
                   shutdown_status, shutdown_requested_at, shutdown_completed_at,
                   recovery_status, recovery_last_requested_at,
                   recovery_last_completed_at, recovery_last_result
            FROM runtime_instances
            ORDER BY created_at ASC, runtime_instance_id ASC
            """
        ).fetchall()

    for row in rows:
        runtime_id = row["runtime_instance_id"]
        status = row["status"]
        startup_status = row["startup_status"]
        shutdown_status = row["shutdown_status"]
        recovery_status = row["recovery_status"]

        if status not in valid_statuses:
            return False, f"runtime_instance {runtime_id} has invalid status {status}"
        if startup_status not in valid_startup:
            return False, f"runtime_instance {runtime_id} has invalid startup_status {startup_status}"
        if shutdown_status not in valid_shutdown:
            return False, f"runtime_instance {runtime_id} has invalid shutdown_status {shutdown_status}"
        if recovery_status not in valid_recovery:
            return False, f"runtime_instance {runtime_id} has invalid recovery_status {recovery_status}"
        if status in terminal_statuses and row["ended_at"] is None:
            return False, f"runtime_instance {runtime_id} has terminal status {status} without ended_at"
        if status in active_statuses and row["ended_at"] is not None:
            return False, f"runtime_instance {runtime_id} has active status {status} with ended_at"
        if status == "failed" and row["failure_code"] is None:
            return False, f"runtime_instance {runtime_id} is failed without failure_code"
        if startup_status == "completed" and row["startup_completed_at"] is None:
            return False, f"runtime_instance {runtime_id} has completed startup without startup_completed_at"
        if shutdown_status in {"requested", "completed", "failed"} and row["shutdown_requested_at"] is None:
            return False, f"runtime_instance {runtime_id} has shutdown_status {shutdown_status} without shutdown_requested_at"
        if shutdown_status == "completed" and row["shutdown_completed_at"] is None:
            return False, f"runtime_instance {runtime_id} has completed shutdown without shutdown_completed_at"
        if recovery_status in {"requested", "completed", "failed"} and row["recovery_last_requested_at"] is None:
            return False, f"runtime_instance {runtime_id} has recovery_status {recovery_status} without recovery_last_requested_at"
        if recovery_status in {"completed", "failed"} and row["recovery_last_completed_at"] is None:
            return False, f"runtime_instance {runtime_id} has recovery_status {recovery_status} without recovery_last_completed_at"
        if recovery_status in {"completed", "failed"} and row["recovery_last_result"] is None:
            return False, f"runtime_instance {runtime_id} has recovery_status {recovery_status} without recovery_last_result"

    return True, None



def verify_evidence_consistency(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Verify evidence rows reference existing items and, when set, existing events."""

    bootstrap_db(db_path)
    return _verify_evidence_consistency_bootstrapped(db_path)


def verify_governed_run_integrity(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Verify governed_runs rows use valid statuses and coherent terminal timestamps."""

    bootstrap_db(db_path)
    return _verify_governed_run_integrity_bootstrapped(db_path)


def verify_runtime_instance_integrity(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Verify runtime_instances rows have coherent lifecycle status combinations."""

    bootstrap_db(db_path)
    return _verify_runtime_instance_integrity_bootstrapped(db_path)

def bootstrap_db(db_path: Path | str = DB_PATH) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        _clear_authorizer(connection)
        contradiction_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(contradictions)").fetchall()
        }
        if contradiction_columns and "target_item_id" not in contradiction_columns and "item_id" in contradiction_columns:
            connection.execute("DROP INDEX IF EXISTS idx_contradictions_source")
            connection.execute("DROP INDEX IF EXISTS idx_contradictions_target")
            connection.execute("ALTER TABLE contradictions RENAME TO contradictions_legacy")
            connection.execute(
                """
                CREATE TABLE contradictions (
                    id TEXT PRIMARY KEY,
                    source_item_id TEXT NOT NULL,
                    target_item_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT,
                    FOREIGN KEY (source_item_id) REFERENCES items(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_item_id) REFERENCES items(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO contradictions (
                    id, source_item_id, target_item_id, status, reason, created_at, resolved_at
                )
                SELECT
                    id,
                    source_item_id,
                    item_id,
                    status,
                    reason,
                    created_at,
                    resolved_at
                FROM contradictions_legacy
                """
            )
            connection.execute("DROP TABLE contradictions_legacy")

        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)

        item_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(items)").fetchall()
        }
        if item_columns and "confidence_tier" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN confidence_tier TEXT")
        if item_columns and "verdict" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN verdict TEXT")
        if item_columns and "closed_at" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN closed_at TEXT")
        if item_columns and "closed_by" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN closed_by TEXT")
        if item_columns and "closed_reason" not in item_columns:
            connection.execute("ALTER TABLE items ADD COLUMN closed_reason TEXT")

        _drop_event_append_only_triggers_for_maintenance(connection)
        _ensure_event_sequence_column(connection)
        _backfill_event_hashes(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_hash ON events(event_hash)")
        _install_event_append_only_triggers(connection)

        contradiction_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(contradictions)").fetchall()
        }
        closeout_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(closeout_runs)").fetchall()
        }
        resume_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(resume_candidates)").fetchall()
        }
        if resume_columns and "reason_json" not in resume_columns and "reason" in resume_columns:
            connection.execute("ALTER TABLE resume_candidates RENAME TO resume_candidates_legacy")
            connection.execute(
                """
                CREATE TABLE resume_candidates (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    reason_json TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    sweep_run_id TEXT,
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO resume_candidates (
                    id, item_id, score, reason_json, generated_at, sweep_run_id
                )
                SELECT
                    id,
                    item_id,
                    score,
                    json_object('reason', reason),
                    created_at,
                    NULL
                FROM resume_candidates_legacy
                """
            )
            connection.execute("DROP TABLE resume_candidates_legacy")

        runtime_instance_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(runtime_instances)").fetchall()
        }
        if runtime_instance_columns:
            if "failure_phase" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN failure_phase TEXT")
            if "startup_status" not in runtime_instance_columns:
                connection.execute(
                    "ALTER TABLE runtime_instances ADD COLUMN startup_status TEXT NOT NULL DEFAULT 'starting'"
                )
            if "startup_completed_at" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN startup_completed_at TEXT")
            if "shutdown_status" not in runtime_instance_columns:
                connection.execute(
                    "ALTER TABLE runtime_instances ADD COLUMN shutdown_status TEXT NOT NULL DEFAULT 'not_requested'"
                )
            if "shutdown_requested_at" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN shutdown_requested_at TEXT")
            if "shutdown_completed_at" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN shutdown_completed_at TEXT")
            if "recovery_status" not in runtime_instance_columns:
                connection.execute(
                    "ALTER TABLE runtime_instances ADD COLUMN recovery_status TEXT NOT NULL DEFAULT 'not_requested'"
                )
            if "recovery_attempt_count" not in runtime_instance_columns:
                connection.execute(
                    "ALTER TABLE runtime_instances ADD COLUMN recovery_attempt_count INTEGER NOT NULL DEFAULT 0"
                )
            if "recovery_last_requested_at" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN recovery_last_requested_at TEXT")
            if "recovery_last_completed_at" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN recovery_last_completed_at TEXT")
            if "recovery_last_result" not in runtime_instance_columns:
                connection.execute("ALTER TABLE runtime_instances ADD COLUMN recovery_last_result TEXT")

        session_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if session_columns and "metadata_json" not in session_columns:
            connection.execute("ALTER TABLE sessions RENAME TO sessions_legacy")
            connection.execute(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    session_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    ended_at TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO sessions (
                    id, session_key, status, metadata_json, started_at, last_seen_at, ended_at
                )
                SELECT
                    id,
                    session_key,
                    status,
                    '{}',
                    started_at,
                    started_at,
                    NULL
                FROM sessions_legacy
                """
            )
            connection.execute("DROP TABLE sessions_legacy")

        if "failure_detail" not in closeout_columns and "detail" in closeout_columns:
            connection.execute("ALTER TABLE closeout_runs RENAME TO closeout_runs_legacy")
            connection.execute(
                """
                CREATE TABLE closeout_runs (
                    id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    requested_state TEXT NOT NULL,
                    result TEXT NOT NULL,
                    failure_code TEXT,
                    failure_detail TEXT,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    open_obligation_count INTEGER NOT NULL DEFAULT 0,
                    open_contradiction_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                INSERT INTO closeout_runs (
                    id, item_id, requested_state, result, failure_code, failure_detail,
                    evidence_count, open_obligation_count, open_contradiction_count, created_at, completed_at
                )
                SELECT
                    CAST(id AS TEXT),
                    item_id,
                    'VERIFIED_DONE',
                    result,
                    failure_code,
                    detail,
                    evidence_count,
                    open_obligation_count,
                    0,
                    created_at,
                    created_at
                FROM closeout_runs_legacy
                """
            )
            connection.execute("DROP TABLE closeout_runs_legacy")
        else:
            if "requested_state" not in closeout_columns:
                connection.execute(
                    "ALTER TABLE closeout_runs ADD COLUMN requested_state TEXT NOT NULL DEFAULT 'VERIFIED_DONE'"
                )
            if "open_contradiction_count" not in closeout_columns:
                connection.execute(
                    "ALTER TABLE closeout_runs ADD COLUMN open_contradiction_count INTEGER NOT NULL DEFAULT 0"
                )
            if "completed_at" not in closeout_columns:
                connection.execute(
                    "ALTER TABLE closeout_runs ADD COLUMN completed_at TEXT"
                )
            if "failure_detail" not in closeout_columns:
                connection.execute(
                    "ALTER TABLE closeout_runs ADD COLUMN failure_detail TEXT"
                )

        connection.commit()
    return db_path


def append_event(
    connection: sqlite3.Connection,
    *,
    event_type: str,
    payload: Mapping[str, Any] | None = None,
    item_id: str | None = None,
    actor: str | None = None,
    source: str | None = None,
    session_id: str | None = None,
    event_id: str | None = None,
    created_at: str | None = None,
) -> str:
    """Write a single append-only event row and return its event id."""

    if event_type == CUTOVER_EVENT_TYPE:
        raise ValueError(f"normal append_event cannot write {CUTOVER_EVENT_TYPE}; use append_cutover_genesis_event")
    _assert_immediate_write_connection(connection)

    event_id = event_id or new_id("evt")
    created_at = created_at or utc_now()
    payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    _ensure_event_sequence_column(connection)
    _ensure_event_hash_columns(connection)
    _assert_no_hashless_events_before_append(connection)
    cutover = _cutover_row(connection)
    event_sequence: int | None = None
    if cutover is None:
        previous_event_hash = connection.execute(
            "SELECT event_hash FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
    else:
        event_sequence = connection.execute(
            "SELECT COALESCE(MAX(event_sequence), 0) + 1 AS next_sequence FROM events WHERE id >= ?",
            (cutover["id"],),
        ).fetchone()["next_sequence"]
        previous_event_hash = connection.execute(
            """
            SELECT event_hash
            FROM events
            WHERE id >= ?
            ORDER BY event_sequence DESC, id DESC
            LIMIT 1
            """,
            (cutover["id"],),
        ).fetchone()
    previous_hash = previous_event_hash["event_hash"] if previous_event_hash else None
    event_hash = compute_event_hash(
        event_id=event_id,
        item_id=item_id,
        event_type=event_type,
        payload_json=payload_json,
        actor=actor,
        source=source,
        session_id=session_id,
        created_at=created_at,
        previous_event_hash=previous_hash,
    )
    connection.execute(
        """
        INSERT INTO events (
            event_id, item_id, event_type, payload_json, actor, source, session_id,
            created_at, previous_event_hash, event_hash, event_sequence
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            item_id,
            event_type,
            payload_json,
            actor,
            source,
            session_id,
            created_at,
            previous_hash,
            event_hash,
            event_sequence,
        ),
    )
    return event_id


def append_cutover_genesis_event(
    connection: sqlite3.Connection,
    *,
    authorization_token: str,
    governing_decision_reference: str,
    actor: str,
    source: str,
    session_id: str,
    payload: Mapping[str, Any] | None = None,
) -> str:
    """Write the one-time V1.1 cutover genesis event.

    Allowed call site: the separately approved B-cutover-execute command/script only.
    Forbidden call sites: normal repository, sweep, cycle, supervisor, Telegram,
    action runtime, and any non-targeted tests.
    """

    if authorization_token != CUTOVER_EXECUTE_AUTHORIZATION_TOKEN:
        raise PermissionError("append_cutover_genesis_event requires B-cutover-execute authorization token")
    if payload is not None and not payload:
        raise ValueError("cutover payload must not be empty")

    _assert_immediate_write_connection(connection)
    _ensure_event_sequence_column(connection)
    _ensure_event_hash_columns(connection)
    _assert_no_hashless_events_before_append(connection)
    if connection.execute("SELECT 1 FROM events WHERE event_type = ? LIMIT 1", (CUTOVER_EVENT_TYPE,)).fetchone() is not None:
        raise ValueError(f"{CUTOVER_EVENT_TYPE} already exists")
    legacy_head = connection.execute(
        "SELECT id, event_id, event_hash FROM events ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if legacy_head is None:
        raise ValueError("cutover requires at least one legacy event to inventory")
    legacy_event_count = connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"]

    event_id = new_id("evt")
    created_at = utc_now()
    cutover_payload = dict(payload or {})
    cutover_payload.update(
        {
            "anchor_commit_hash": _current_git_commit_hash(),
            "cutover_timestamp": created_at,
            "cutover_version": "v1.1",
            "design_commit_hash": DESIGN_COMMIT_HASH,
            "forbidden_claims_reference": "Do not claim full-history tamper-evidence; approved claim is cutover-forward only.",
            "governing_decision": "checkpoint-forward; do not rewrite pre-cutover history",
            "governing_decision_reference": governing_decision_reference,
            "legacy_chain_head_event_id": legacy_head["event_id"],
            "legacy_chain_head_hash": legacy_head["event_hash"],
            "legacy_chain_head_row_id": legacy_head["id"],
            "legacy_diagnosis_path": "ace/state/v1_1_required_items/slice-b1-chain-diagnosis-readonly.md",
            "legacy_disclosure_path": "ace/state/v1_1_required_items/legacy-chain-defects.md",
            "legacy_event_count": legacy_event_count,
            "legacy_known_defect_counts": dict(LEGACY_KNOWN_DEFECT_COUNTS),
            "post_cutover_chain_policy": dict(POST_CUTOVER_CHAIN_POLICY),
        }
    )
    _validate_cutover_payload(cutover_payload)
    payload_json = json.dumps(cutover_payload, sort_keys=True, separators=(",", ":"))
    event_hash = compute_event_hash(
        event_id=event_id,
        item_id=None,
        event_type=CUTOVER_EVENT_TYPE,
        payload_json=payload_json,
        actor=actor,
        source=source,
        session_id=session_id,
        created_at=created_at,
        previous_event_hash=None,
    )
    connection.execute(
        """
        INSERT INTO events (
            event_id, item_id, event_type, payload_json, actor, source, session_id,
            created_at, previous_event_hash, event_hash, event_sequence
        ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?, NULL, ?, 1)
        """,
        (event_id, CUTOVER_EVENT_TYPE, payload_json, actor, source, session_id, created_at, event_hash),
    )
    return event_id
