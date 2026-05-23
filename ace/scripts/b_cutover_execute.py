from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from contextlib import suppress
from typing import Any, Callable

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ace.storage import (
    CUTOVER_EVENT_TYPE,
    CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
    DB_PATH,
    LEGACY_CHAIN_DISCLOSURE_PATH,
    append_cutover_genesis_event,
    connect,
    connect_readonly,
    legacy_chain_inventory,
    new_id,
    post_cutover_event_hash_chain,
    utc_now,
)

EXIT_SUCCESS = 0
EXIT_PRE_COMMIT_FAILURE = 10
EXIT_POST_COMMIT_FAILURE = 20

DEFAULT_LOG_PATH = Path(__file__).resolve().parents[1] / "state" / "v1_1_required_items" / "b-cutover-execute-log.jsonl"

RECOVERY_INSTRUCTIONS = (
    "Manual recovery required: do not rerun B-cutover-execute as a normal retry. "
    "Inspect the durable log, identify the single ace.chain.cutover.v1_1 event, "
    "then run `python3 -m ace.ace --db <db_path> audit verify`. If legacy_chain_inventory, "
    "event_hash_chain, post_cutover_event_hash_chain, evidence_consistency, "
    "governed_run_integrity, and runtime_instance_integrity are ok, record manual recovery "
    "completion. If any check fails, stop and escalate without mutating pre-cutover rows or "
    "appending another cutover event."
)


class CutoverExecutionError(RuntimeError):
    pass


class PostCommitFailure(CutoverExecutionError):
    pass


class PreCommitFailure(CutoverExecutionError):
    pass


class CutoverLogger:
    def __init__(self, path: Path, *, run_id: str, db_path: Path) -> None:
        self.path = path
        self.run_id = run_id
        self.db_path = db_path

    def write(
        self,
        step: str,
        status: str,
        *,
        commit_completed: bool,
        cutover_event_id: str | None = None,
        detail: str | None = None,
        recovery_instructions: str | None = None,
    ) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "timestamp": utc_now(),
            "run_id": self.run_id,
            "step": step,
            "status": status,
            "db_path": str(self.db_path),
            "commit_completed": commit_completed,
        }
        if cutover_event_id is not None:
            record["cutover_event_id"] = cutover_event_id
        if detail is not None:
            record["detail"] = detail
        if recovery_instructions is not None:
            record["recovery_instructions"] = recovery_instructions
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _cutover_count(db_path: Path) -> int:
    with connect_readonly(db_path) as connection:
        return connection.execute(
            "SELECT COUNT(*) AS count FROM events WHERE event_type = ?",
            (CUTOVER_EVENT_TYPE,),
        ).fetchone()["count"]


def _legacy_event_count(db_path: Path) -> int:
    with connect_readonly(db_path) as connection:
        return connection.execute("SELECT COUNT(*) AS count FROM events").fetchone()["count"]


def _require_prerequisites(db_path: Path, authorization_token: str) -> None:
    if authorization_token != CUTOVER_EXECUTE_AUTHORIZATION_TOKEN:
        raise PreCommitFailure("missing or invalid B-cutover-execute authorization token")
    if not db_path.exists():
        raise PreCommitFailure(f"database does not exist: {db_path}")
    if not LEGACY_CHAIN_DISCLOSURE_PATH.exists():
        raise PreCommitFailure(f"legacy chain disclosure missing: {LEGACY_CHAIN_DISCLOSURE_PATH}")
    if _cutover_count(db_path) != 0:
        raise PreCommitFailure(f"{CUTOVER_EVENT_TYPE} already exists")
    if _legacy_event_count(db_path) <= 0:
        raise PreCommitFailure("cutover requires at least one legacy event")


def _run_post_commit_followup(db_path: Path, cutover_event_id: str) -> str:
    with connect_readonly(db_path) as connection:
        row = connection.execute(
            "SELECT event_id FROM events WHERE event_type = ?",
            (CUTOVER_EVENT_TYPE,),
        ).fetchone()
        if row is None:
            raise PostCommitFailure("committed cutover event could not be read back")
        if row["event_id"] != cutover_event_id:
            raise PostCommitFailure("committed cutover event id mismatch")
    legacy_ok, legacy_detail = legacy_chain_inventory(db_path)
    if not legacy_ok:
        raise PostCommitFailure(f"legacy_chain_inventory failed: {legacy_detail}")
    post_ok, post_detail = post_cutover_event_hash_chain(db_path)
    if not post_ok:
        raise PostCommitFailure(f"post_cutover_event_hash_chain failed: {post_detail}")
    return f"legacy_chain_inventory={legacy_detail}; post_cutover_event_hash_chain={post_detail or 'ok'}"


def execute_cutover(
    *,
    db_path: Path,
    log_path: Path,
    authorization_token: str,
    governing_decision_reference: str,
    actor: str = "b-cutover-execute",
    source: str = "ace/scripts/b_cutover_execute.py",
    session_id: str | None = None,
    failpoint: str | None = None,
    post_commit_followup: Callable[[Path, str], str] = _run_post_commit_followup,
) -> tuple[int, str | None]:
    """Execute the one-time cutover with explicit pre/post-commit failure handling."""

    run_id = new_id("cutover_run")
    session_id = session_id or f"v1.1-cutover:{run_id}"
    logger = CutoverLogger(log_path, run_id=run_id, db_path=db_path)
    commit_completed = False
    cutover_event_id: str | None = None
    connection: sqlite3.Connection | None = None
    try:
        logger.write("run.started", "ok", commit_completed=False)
        logger.write("prerequisites.before", "ok", commit_completed=False)
        _require_prerequisites(db_path, authorization_token)
        if failpoint == "pre_commit":
            raise PreCommitFailure("injected pre-commit failure")
        logger.write("prerequisites.after", "ok", commit_completed=False)

        logger.write("cutover.transaction.begin.before", "ok", commit_completed=False)
        with connect(db_path) as opened_connection:
            connection = opened_connection
            cutover_event_id = append_cutover_genesis_event(
                connection,
                authorization_token=authorization_token,
                governing_decision_reference=governing_decision_reference,
                actor=actor,
                source=source,
                session_id=session_id,
            )
            logger.write(
                "cutover.append.after",
                "ok",
                commit_completed=False,
                cutover_event_id=cutover_event_id,
            )
            if failpoint == "before_commit":
                raise PreCommitFailure("injected before-commit failure")
            connection.commit()
            commit_completed = True
            logger.write(
                "cutover.commit.after",
                "ok",
                commit_completed=True,
                cutover_event_id=cutover_event_id,
            )

        logger.write(
            "post_commit.followup.before",
            "ok",
            commit_completed=True,
            cutover_event_id=cutover_event_id,
            recovery_instructions=RECOVERY_INSTRUCTIONS,
        )
        if failpoint == "post_commit":
            raise PostCommitFailure("injected post-commit failure")
        detail = post_commit_followup(db_path, cutover_event_id)
        logger.write(
            "post_commit.followup.after",
            "ok",
            commit_completed=True,
            cutover_event_id=cutover_event_id,
            detail=detail,
            recovery_instructions=RECOVERY_INSTRUCTIONS,
        )
        logger.write("run.completed", "ok", commit_completed=True, cutover_event_id=cutover_event_id)
        return EXIT_SUCCESS, cutover_event_id
    except PreCommitFailure as exc:
        if connection is not None and not commit_completed:
            with suppress(sqlite3.ProgrammingError):
                connection.rollback()
        logger.write("run.failed.pre_commit", "failed", commit_completed=False, detail=str(exc))
        return EXIT_PRE_COMMIT_FAILURE, None
    except Exception as exc:
        if not commit_completed:
            if connection is not None:
                with suppress(sqlite3.ProgrammingError):
                    connection.rollback()
            try:
                logger.write("run.failed.pre_commit", "failed", commit_completed=False, detail=str(exc))
            except Exception:
                pass
            return EXIT_PRE_COMMIT_FAILURE, None
        logger.write(
            "run.failed.post_commit",
            "failed",
            commit_completed=True,
            cutover_event_id=cutover_event_id,
            detail=str(exc),
            recovery_instructions=RECOVERY_INSTRUCTIONS,
        )
        return EXIT_POST_COMMIT_FAILURE, cutover_event_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Execute the one-time ACE V1.1 cutover genesis append")
    parser.add_argument("--db", default=str(DB_PATH), help="ACE SQLite database path")
    parser.add_argument("--log-path", default=str(DEFAULT_LOG_PATH), help="Durable JSONL execution log path")
    parser.add_argument("--authorization-token", required=True, help="B-cutover-execute authorization token")
    parser.add_argument("--governing-decision-reference", required=True, help="Durable operator approval reference")
    parser.add_argument("--actor", default="b-cutover-execute")
    parser.add_argument("--source", default="ace/scripts/b_cutover_execute.py")
    parser.add_argument("--session-id")
    parser.add_argument(
        "--failpoint",
        choices=("pre_commit", "before_commit", "post_commit"),
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    exit_code, cutover_event_id = execute_cutover(
        db_path=Path(args.db),
        log_path=Path(args.log_path),
        authorization_token=args.authorization_token,
        governing_decision_reference=args.governing_decision_reference,
        actor=args.actor,
        source=args.source,
        session_id=args.session_id,
        failpoint=args.failpoint,
    )
    print(f"b_cutover_execute.exit_code={exit_code}")
    print(f"b_cutover_execute.log_path={Path(args.log_path)}")
    if cutover_event_id is not None:
        print(f"b_cutover_execute.cutover_event_id={cutover_event_id}")
    if exit_code == EXIT_PRE_COMMIT_FAILURE:
        print("b_cutover_execute.failure_class=pre_commit_safe_to_retry")
    if exit_code == EXIT_POST_COMMIT_FAILURE:
        print("b_cutover_execute.failure_class=post_commit_manual_recovery_required")
        print(f"b_cutover_execute.recovery_instructions={RECOVERY_INSTRUCTIONS}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
