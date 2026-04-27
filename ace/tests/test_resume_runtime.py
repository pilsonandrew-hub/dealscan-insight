from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository, ValidationError
from ace.storage import bootstrap_db, connect


class ResumeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)
        self.item = self.repo.create_item(item_type="note", title="Resume runtime target")

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

    def test_register_session_candidate_claim_and_complete_writes_one_recovery_evidence_row(self) -> None:
        from ace.resume_runtime import (
            RECOVERY_CREATED_BY,
            RECOVERY_EVIDENCE_URI,
            claim_resume_candidate,
            complete_resume_candidate,
            register_resume_candidate,
            register_resume_session,
        )

        session = register_resume_session(self.db_path, session_key="phase3.session")
        self.assertEqual(session["status"], "registered")

        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "stale_followup", "detail": "operator session expired"},
        )
        self.assertEqual(candidate["item_id"], self.item.id)

        claimed = claim_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])
        self.assertEqual(claimed["status"], "claimed")
        self.assertEqual(claimed["session_id"], session["session_id"])

        completed = complete_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(completed["evidence_written"])
        self.assertIsInstance(completed["evidence_id"], str)

        session_row = self._session_row(session["session_id"])
        self.assertEqual(session_row["status"], "completed")
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
                "outcome": "resume_recovery_completed",
                "session_id": session["session_id"],
                "session_key": "phase3.session",
            },
        )

    def test_register_session_is_deterministic_and_reuses_existing_row(self) -> None:
        from ace.resume_runtime import register_resume_session

        first = register_resume_session(self.db_path, session_key="phase3.session")
        second = register_resume_session(self.db_path, session_key="phase3.session")

        self.assertEqual(first["session_id"], second["session_id"])
        self.assertEqual(first["status"], "registered")
        self.assertEqual(second["status"], "registered")

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM sessions WHERE session_key = ?",
                ("phase3.session",),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_register_candidate_is_deterministic_and_reuses_existing_row(self) -> None:
        from ace.resume_runtime import register_resume_candidate

        reason = {"kind": "stale_followup", "detail": "operator session expired"}
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

    def test_register_candidate_rejects_malformed_reason_with_zero_partial_writes(self) -> None:
        from ace.resume_runtime import register_resume_candidate

        with self.assertRaises(ValidationError):
            register_resume_candidate(self.db_path, item_id=self.item.id, score=0.75, reason="not-a-mapping")

        with connect(self.db_path) as connection:
            count = connection.execute("SELECT COUNT(*) FROM resume_candidates").fetchone()[0]
        self.assertEqual(count, 0)

    def test_claim_is_replay_safe_and_does_not_reassign_session(self) -> None:
        from ace.resume_runtime import claim_resume_candidate, register_resume_candidate, register_resume_session

        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "stale_followup", "detail": "operator session expired"},
        )
        session = register_resume_session(self.db_path, session_key="phase3.session")

        first = claim_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])
        second = claim_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])

        self.assertEqual(first["status"], "claimed")
        self.assertEqual(second["status"], "claimed")
        self.assertEqual(first["session_id"], session["session_id"])
        self.assertEqual(second["session_id"], session["session_id"])

    def test_complete_heals_interrupted_success_without_duplicate_evidence(self) -> None:
        from ace.resume_runtime import (
            RECOVERY_CREATED_BY,
            RECOVERY_EVIDENCE_URI,
            claim_resume_candidate,
            complete_resume_candidate,
            register_resume_candidate,
            register_resume_session,
        )

        session = register_resume_session(self.db_path, session_key="phase3.session")
        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "stale_followup", "detail": "operator session expired"},
        )
        claim_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])

        evidence_text = json.dumps(
            {
                "candidate_id": candidate["candidate_id"],
                "item_id": self.item.id,
                "outcome": "resume_recovery_completed",
                "session_id": session["session_id"],
                "session_key": "phase3.session",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence_id = self.repo.add_evidence(
            self.item.id,
            evidence_text=evidence_text,
            evidence_uri=RECOVERY_EVIDENCE_URI,
            created_by=RECOVERY_CREATED_BY,
        )

        session_row = self._session_row(session["session_id"])
        self.assertEqual(session_row["status"], "claimed")
        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)

        result = complete_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["evidence_written"])
        self.assertEqual(result["evidence_id"], evidence_id)

        session_row = self._session_row(session["session_id"])
        self.assertEqual(session_row["status"], "completed")
        self.assertIsNotNone(session_row["ended_at"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["evidence_uri"], RECOVERY_EVIDENCE_URI)

    def test_complete_rejects_stale_missing_target_without_writing_success_artifact(self) -> None:
        from ace.resume_runtime import claim_resume_candidate, complete_resume_candidate, register_resume_candidate, register_resume_session

        candidate = register_resume_candidate(
            self.db_path,
            item_id=self.item.id,
            score=0.75,
            reason={"kind": "stale_followup", "detail": "operator session expired"},
        )
        session = register_resume_session(self.db_path, session_key="phase3.session")
        claim_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])

        with sqlite3.connect(self.db_path) as raw_connection:
            raw_connection.execute("PRAGMA foreign_keys = OFF")
            raw_connection.execute("DELETE FROM items WHERE id = ?", (self.item.id,))
            raw_connection.commit()

        result = complete_resume_candidate(self.db_path, candidate["candidate_id"], session_id=session["session_id"])
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn(self.item.id, result["error_message"])

        session_row = self._session_row(session["session_id"])
        self.assertEqual(session_row["status"], "failed")
        self.assertIsNotNone(session_row["ended_at"])
        self.assertEqual(self._evidence_rows(), [])
