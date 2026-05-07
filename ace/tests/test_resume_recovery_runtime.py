from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository, ValidationError
from ace.storage import bootstrap_db, connect


class ResumeRecoveryRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)
        self.item = self.repo.create_item(item_type="note", title="Resume recovery target")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _session_row(self, session_id: str) -> dict[str, object]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, session_key, status, metadata_json, started_at, last_seen_at, ended_at
                FROM sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        return dict(row)

    def _candidate_row(self, candidate_id: str) -> dict[str, object]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, item_id, score, reason_json, generated_at, sweep_run_id
                FROM resume_candidates
                WHERE id = ?
                """,
                (candidate_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        return dict(row)

    def _evidence_rows(self) -> list[dict[str, object]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT item_id, evidence_text, evidence_uri, created_by
                FROM evidence
                WHERE item_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (self.item.id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def test_register_session_reuses_existing_row_and_select_is_deterministic(self) -> None:
        from ace.resume_recovery_runtime import (
            register_resume_candidate,
            register_resume_session,
            select_resume_candidate,
        )

        first_session = register_resume_session(
            self.db_path,
            session_key="phase3.session",
            metadata={"source": "unit-test"},
        )
        second_session = register_resume_session(
            self.db_path,
            session_key="phase3.session",
            metadata={"source": "unit-test"},
        )

        self.assertEqual(first_session["session_id"], second_session["session_id"])
        self.assertEqual(first_session["status"], "registered")
        self.assertEqual(second_session["status"], "registered")

        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "resume", "detail": "bounded recovery candidate"},
        )
        selected_first = select_resume_candidate(
            self.db_path,
            candidate["candidate_id"],
            session_id=first_session["session_id"],
        )
        selected_second = select_resume_candidate(
            self.db_path,
            candidate["candidate_id"],
            session_id=first_session["session_id"],
        )

        self.assertEqual(selected_first["status"], "selected")
        self.assertEqual(selected_second["status"], "selected")
        self.assertEqual(selected_first["session_id"], first_session["session_id"])
        self.assertEqual(selected_second["session_id"], first_session["session_id"])

        session_row = self._session_row(first_session["session_id"])
        self.assertEqual(session_row["status"], "selected")
        self.assertIn("selected_candidate_id", json.loads(session_row["metadata_json"]))

        with connect(self.db_path) as connection:
            session_count = connection.execute(
                "SELECT COUNT(*) FROM sessions WHERE session_key = ?",
                ("phase3.session",),
            ).fetchone()[0]
            candidate_count = connection.execute(
                "SELECT COUNT(*) FROM resume_candidates WHERE id = ?",
                (candidate["candidate_id"],),
            ).fetchone()[0]
        self.assertEqual(session_count, 1)
        self.assertEqual(candidate_count, 1)

    def test_register_candidate_reuses_existing_row(self) -> None:
        from ace.resume_recovery_runtime import register_resume_candidate

        reason = {"kind": "resume", "detail": "bounded recovery candidate"}
        first = register_resume_candidate(self.db_path, item_id=self.item.id, score=0.75, reason=reason)
        second = register_resume_candidate(self.db_path, item_id=self.item.id, score=0.75, reason=reason)

        self.assertEqual(first["candidate_id"], second["candidate_id"])
        self.assertEqual(first["item_id"], self.item.id)
        self.assertEqual(second["item_id"], self.item.id)

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM resume_candidates WHERE id = ?",
                (first["candidate_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_select_rejects_a_different_candidate_for_the_same_session(self) -> None:
        from ace.resume_recovery_runtime import (
            register_resume_candidate,
            register_resume_session,
            select_resume_candidate,
        )

        session = register_resume_session(self.db_path, session_key="phase3.session", metadata={"source": "unit-test"})
        first_item = self.item
        second_item = self.repo.create_item(item_type="note", title="Second resume target")
        first_candidate = register_resume_candidate(
            self.db_path,
            item_id=first_item.id,
            score=0.75,
            reason={"kind": "resume", "detail": "first candidate"},
        )
        second_candidate = register_resume_candidate(
            self.db_path,
            item_id=second_item.id,
            score=0.80,
            reason={"kind": "resume", "detail": "second candidate"},
        )

        select_resume_candidate(self.db_path, first_candidate["candidate_id"], session_id=session["session_id"])

        with self.assertRaises(ValidationError):
            select_resume_candidate(self.db_path, second_candidate["candidate_id"], session_id=session["session_id"])

    def test_register_session_rejects_malformed_metadata_with_zero_partial_writes(self) -> None:
        from ace.resume_recovery_runtime import register_resume_session

        with self.assertRaises(ValidationError):
            register_resume_session(self.db_path, session_key="phase3.session", metadata="not-a-mapping")

        with connect(self.db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        self.assertEqual(count, 0)

    def test_terminal_dismissal_writes_one_evidence_row_and_is_replay_safe(self) -> None:
        from ace.resume_recovery_runtime import (
            RECOVERY_CREATED_BY,
            RECOVERY_EVIDENCE_URI,
            complete_resume_candidate,
            register_resume_candidate,
            register_resume_session,
            select_resume_candidate,
        )

        session = register_resume_session(self.db_path, session_key="phase3.session", metadata={"source": "unit-test"})
        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "resume", "detail": "bounded recovery candidate"},
        )
        select_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])

        first = complete_resume_candidate(
            self.db_path,
            candidate["candidate_id"],
            session_id=session["session_id"],
            terminal_status="dismissed",
        )
        second = complete_resume_candidate(
            self.db_path,
            candidate["candidate_id"],
            session_id=session["session_id"],
            terminal_status="dismissed",
        )

        self.assertEqual(first["status"], "dismissed")
        self.assertEqual(second["status"], "dismissed")
        self.assertTrue(first["evidence_written"])
        self.assertFalse(second["evidence_written"])
        self.assertEqual(first["evidence_id"], second["evidence_id"])

        session_row = self._session_row(session["session_id"])
        self.assertEqual(session_row["status"], "dismissed")
        self.assertIsNotNone(session_row["ended_at"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["evidence_uri"], RECOVERY_EVIDENCE_URI)
        self.assertEqual(evidence_rows[0]["created_by"], RECOVERY_CREATED_BY)
        self.assertEqual(
            json.loads(evidence_rows[0]["evidence_text"]),
            {
                "candidate_id": candidate["candidate_id"],
                "item_id": self.item.id,
                "outcome": "resume_recovery_dismissed",
                "session_id": session["session_id"],
                "session_key": "phase3.session",
                "terminal_status": "dismissed",
            },
        )

    def test_complete_rejects_stale_target_without_writing_success_artifact(self) -> None:
        from ace.resume_recovery_runtime import (
            complete_resume_candidate,
            register_resume_candidate,
            register_resume_session,
            select_resume_candidate,
        )

        session = register_resume_session(self.db_path, session_key="phase3.session", metadata={"source": "unit-test"})
        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "resume", "detail": "bounded recovery candidate"},
        )
        select_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])

        raw_connection = sqlite3.connect(self.db_path)
        try:
            raw_connection.execute("PRAGMA foreign_keys = OFF")
            raw_connection.execute("DELETE FROM items WHERE id = ?", (self.item.id,))
            raw_connection.commit()
        finally:
            raw_connection.close()

        result = complete_resume_candidate(
            self.db_path,
            candidate["candidate_id"],
            session_id=session["session_id"],
            terminal_status="dismissed",
        )

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn(self.item.id, result["error_message"])

        session_row = self._session_row(session["session_id"])
        self.assertEqual(session_row["status"], "failed")
        self.assertIsNotNone(session_row["ended_at"])
        self.assertEqual(self._evidence_rows(), [])


if __name__ == "__main__":
    unittest.main()
