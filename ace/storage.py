from __future__ import annotations

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
    "CREATE INDEX IF NOT EXISTS idx_items_state ON items(state)",
    "CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_item_id ON events(item_id)",
    "CREATE INDEX IF NOT EXISTS idx_action_queue_status ON action_queue(status)",
    "CREATE INDEX IF NOT EXISTS idx_obligations_item_status ON obligations(item_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_resume_candidates_score ON resume_candidates(score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_source ON contradictions(source_item_id)",
    "CREATE INDEX IF NOT EXISTS idx_contradictions_target ON contradictions(target_item_id)",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@contextmanager
def connect(db_path: Path | str = DB_PATH):
    connection = sqlite3.connect(str(db_path))
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


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
    connection.execute(
        """
        INSERT INTO events (
            event_id, item_id, event_type, payload_json, actor, source, session_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (event_id, item_id, event_type, payload_json, actor, source, session_id, created_at),
    )
    return event_id
