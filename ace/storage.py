from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ACE_DIR = Path(__file__).resolve().parent
STATE_DIR = ACE_DIR / "state"
DB_PATH = STATE_DIR / "ace.db"


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
    "CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_action_queue_status ON action_queue(status)",
    "CREATE INDEX IF NOT EXISTS idx_obligations_item_status ON obligations(item_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_resume_candidates_score ON resume_candidates(score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_source ON contradictions(source_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_target ON contradictions(target_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_governed_runs_status_created_at ON governed_runs(status, created_at DESC, run_id DESC)",
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


@contextmanager
def connect(db_path: Path | str = DB_PATH):
    connection = sqlite3.connect(str(db_path), timeout=30.0)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


def _ensure_event_hash_columns(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)").fetchall()}
    if not columns:
        return
    if "previous_event_hash" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN previous_event_hash TEXT")
    if "event_hash" not in columns:
        connection.execute("ALTER TABLE events ADD COLUMN event_hash TEXT")


def _backfill_event_hashes(connection: sqlite3.Connection) -> None:
    _ensure_event_hash_columns(connection)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(events)").fetchall()}
    if not {"previous_event_hash", "event_hash"}.issubset(columns):
        return

    previous_event_hash: str | None = None
    rows = connection.execute(
        """
        SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
               created_at, previous_event_hash, event_hash
        FROM events
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
            previous_event_hash=previous_event_hash,
        )
        if row["previous_event_hash"] is None and row["event_hash"] is None:
            connection.execute(
                "UPDATE events SET previous_event_hash = ?, event_hash = ? WHERE id = ?",
                (previous_event_hash, expected_hash, row["id"]),
            )
        previous_event_hash = row["event_hash"] or expected_hash


def repair_event_hash_chain_for_legacy_races(connection: sqlite3.Connection) -> int:
    """Repair hash rows produced by pre-serialized append races.

    This is deliberately narrow: it only rewrites rows whose stored hash matches the
    row's stored previous hash, but whose stored previous hash does not match the
    canonical immediately preceding event hash. That pattern is produced by older
    concurrent appenders that computed a valid hash before another writer committed.
    Payload/hash mismatches remain tamper evidence and are not repaired here.
    """

    _ensure_event_hash_columns(connection)
    _backfill_event_hashes(connection)
    repaired = 0
    previous_event_hash: str | None = None
    rows = connection.execute(
        """
        SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
               created_at, previous_event_hash, event_hash
        FROM events
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        hash_with_stored_previous = compute_event_hash(
            event_id=row["event_id"],
            item_id=row["item_id"],
            event_type=row["event_type"],
            payload_json=row["payload_json"],
            actor=row["actor"],
            source=row["source"],
            session_id=row["session_id"],
            created_at=row["created_at"],
            previous_event_hash=row["previous_event_hash"],
        )
        if row["event_hash"] != hash_with_stored_previous:
            previous_event_hash = row["event_hash"]
            continue
        if row["previous_event_hash"] != previous_event_hash:
            repaired_hash = compute_event_hash(
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
            connection.execute(
                "UPDATE events SET previous_event_hash = ?, event_hash = ? WHERE id = ?",
                (previous_event_hash, repaired_hash, row["id"]),
            )
            repaired += 1
            previous_event_hash = repaired_hash
        else:
            previous_event_hash = row["event_hash"]
    return repaired


def verify_event_hash_chain(db_path: Path | str = DB_PATH) -> tuple[bool, str | None]:
    """Return whether the append-only event hash chain is internally consistent."""

    bootstrap_db(db_path)
    previous_event_hash: str | None = None
    with connect(db_path) as connection:
        # Take a consistent verification snapshot while also backfilling any rows
        # appended by a still-running pre-hash runtime process.
        connection.execute("BEGIN IMMEDIATE")
        _backfill_event_hashes(connection)
        rows = connection.execute(
            """
            SELECT id, event_id, item_id, event_type, payload_json, actor, source, session_id,
                   created_at, previous_event_hash, event_hash
            FROM events
            ORDER BY id ASC
            """
        ).fetchall()
        connection.commit()

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


def bootstrap_db(db_path: Path | str = DB_PATH) -> Path:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
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

        _backfill_event_hashes(connection)
        connection.execute("CREATE INDEX IF NOT EXISTS idx_events_hash ON events(event_hash)")

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

    event_id = event_id or new_id("evt")
    created_at = created_at or utc_now()
    payload_json = json.dumps(payload or {}, sort_keys=True, separators=(",", ":"))
    if not connection.in_transaction:
        connection.execute("BEGIN IMMEDIATE")
    else:
        # Force SQLite to acquire the write lock before reading the previous
        # event hash. Without this, concurrent deferred transactions can compute
        # against the same tail and later commit out of chain order.
        connection.execute("UPDATE events SET event_id = event_id WHERE 0")
    _ensure_event_hash_columns(connection)
    _backfill_event_hashes(connection)
    previous_event_hash = connection.execute(
        "SELECT event_hash FROM events ORDER BY id DESC LIMIT 1"
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
            created_at, previous_event_hash, event_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        ),
    )
    return event_id
