from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository, ValidationError
from ace.storage import bootstrap_db, connect


class OwnedRecoveryRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)
        self.item = self.repo.create_item(item_type="note", title="Owned recovery target")

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

    def _ownership_row(self, ownership_id: str) -> dict[str, object]:
        with connect(self.db_path) as connection:
            row = connection.execute(
                """
                SELECT id, item_id, action_type, payload_json, status, claimed_at, completed_at, error_message
                FROM action_queue
                WHERE id = ?
                """,
                (ownership_id,),
            ).fetchone()
        self.assertIsNotNone(row)
        return dict(row)

    def _evidence_rows(self) -> list[dict[str, object]]:
        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT item_id, evidence_text, evidence_uri, created_by
                FROM evidence
                ORDER BY created_at ASC, id ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def test_connected_lifecycle_happy_path_is_replay_safe_and_non_duplicative(self) -> None:
        from ace.owned_recovery_runtime import (
            finalize_owned_recovery_lifecycle,
            start_owned_recovery_lifecycle,
        )

        started = start_owned_recovery_lifecycle(
            self.db_path,
            item_id=self.item.id,
            owner="owner-a",
            ownership_metadata={"kind": "owned-recovery", "note": "phase7a"},
            session_key="phase7a.session",
            session_metadata={"source": "unit-test"},
            candidate_score=0.75,
            candidate_reason={"kind": "resume", "detail": "phase7a owned recovery"},
        )

        self.assertEqual(started["ownership_status"], "claimed")
        self.assertEqual(started["recovery_status"], "selected")
        session_row = self._session_row(started["session_id"])
        self.assertEqual(session_row["status"], "selected")
        session_metadata = json.loads(session_row["metadata_json"])
        self.assertEqual(session_metadata["phase7a_item_id"], self.item.id)
        self.assertEqual(session_metadata["phase7a_ownership_id"], started["ownership_id"])
        self.assertEqual(session_metadata["selected_candidate_id"], started["candidate_id"])

        first = finalize_owned_recovery_lifecycle(
            self.db_path,
            ownership_id=started["ownership_id"],
            session_id=started["session_id"],
            candidate_id=started["candidate_id"],
            owner="owner-a",
        )
        second = finalize_owned_recovery_lifecycle(
            self.db_path,
            ownership_id=started["ownership_id"],
            session_id=started["session_id"],
            candidate_id=started["candidate_id"],
            owner="owner-a",
        )

        self.assertEqual(first["recovery_status"], "dismissed")
        self.assertEqual(first["ownership_status"], "completed")
        self.assertTrue(first["recovery_evidence_written"])
        self.assertTrue(first["ownership_evidence_written"])
        self.assertEqual(second["recovery_status"], "dismissed")
        self.assertEqual(second["ownership_status"], "completed")
        self.assertFalse(second["recovery_evidence_written"])
        self.assertFalse(second["ownership_evidence_written"])
        self.assertEqual(first["recovery_evidence_id"], second["recovery_evidence_id"])
        self.assertEqual(first["ownership_evidence_id"], second["ownership_evidence_id"])

        ownership_row = self._ownership_row(started["ownership_id"])
        self.assertEqual(ownership_row["status"], "completed")
        self.assertIsNotNone(ownership_row["completed_at"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 2)
        self.assertEqual(
            {row["evidence_uri"] for row in evidence_rows},
            {"ace://phase3b/recovery-outcome", "ace://phase4/runtime-ownership-outcome"},
        )

    def test_finalize_rejects_cross_seam_item_mismatch(self) -> None:
        from ace.owned_recovery_runtime import (
            finalize_owned_recovery_lifecycle,
            start_owned_recovery_lifecycle,
        )
        from ace.resume_recovery_runtime import (
            register_resume_candidate,
            register_resume_session,
            select_resume_candidate,
        )

        started = start_owned_recovery_lifecycle(
            self.db_path,
            item_id=self.item.id,
            owner="owner-a",
            ownership_metadata={"kind": "owned-recovery", "note": "phase7a"},
            session_key="phase7a.session",
            session_metadata={"source": "unit-test"},
            candidate_score=0.75,
            candidate_reason={"kind": "resume", "detail": "phase7a owned recovery"},
        )
        other_item = self.repo.create_item(item_type="note", title="Other target")
        other_session = register_resume_session(
            self.db_path,
            session_key="phase7a.other-session",
            metadata={"source": "unit-test"},
        )
        other_candidate = register_resume_candidate(
            self.db_path,
            item_id=other_item.id,
            score=0.5,
            reason={"kind": "resume", "detail": "other candidate"},
        )
        select_resume_candidate(
            self.db_path,
            other_candidate["candidate_id"],
            session_id=other_session["session_id"],
        )

        with self.assertRaises(ValidationError):
            finalize_owned_recovery_lifecycle(
                self.db_path,
                ownership_id=started["ownership_id"],
                session_id=other_session["session_id"],
                candidate_id=other_candidate["candidate_id"],
                owner="owner-a",
            )

        self.assertEqual(self._evidence_rows(), [])

    def test_connected_failure_preserves_claimed_ownership_and_no_success_artifacts(self) -> None:
        from ace.owned_recovery_runtime import (
            finalize_owned_recovery_lifecycle,
            start_owned_recovery_lifecycle,
        )

        started = start_owned_recovery_lifecycle(
            self.db_path,
            item_id=self.item.id,
            owner="owner-a",
            ownership_metadata={"kind": "owned-recovery", "note": "phase7a"},
            session_key="phase7a.session",
            session_metadata={"source": "unit-test"},
            candidate_score=0.75,
            candidate_reason={"kind": "resume", "detail": "phase7a owned recovery"},
        )

        raw_connection = sqlite3.connect(self.db_path)
        try:
            raw_connection.execute("PRAGMA foreign_keys = OFF")
            raw_connection.execute("DELETE FROM items WHERE id = ?", (self.item.id,))
            raw_connection.commit()
        finally:
            raw_connection.close()

        result = finalize_owned_recovery_lifecycle(
            self.db_path,
            ownership_id=started["ownership_id"],
            session_id=started["session_id"],
            candidate_id=started["candidate_id"],
            owner="owner-a",
        )

        self.assertEqual(result["recovery_status"], "failed")
        self.assertEqual(result["ownership_status"], "claimed")
        self.assertFalse(result["recovery_evidence_written"])
        self.assertFalse(result["ownership_evidence_written"])
        self.assertIsNone(result["recovery_evidence_id"])
        self.assertIsNone(result["ownership_evidence_id"])
        self.assertIn(self.item.id, result["error_message"])

        ownership_row = self._ownership_row(started["ownership_id"])
        self.assertEqual(ownership_row["status"], "claimed")
        session_row = self._session_row(started["session_id"])
        self.assertEqual(session_row["status"], "failed")
        self.assertEqual(self._evidence_rows(), [])


    def test_finalize_heals_interrupted_cross_surface_success_without_duplicate_evidence(self) -> None:
        from ace.owned_recovery_runtime import (
            finalize_owned_recovery_lifecycle,
            start_owned_recovery_lifecycle,
        )
        from ace.resume_recovery_runtime import RECOVERY_CREATED_BY, RECOVERY_EVIDENCE_URI

        started = start_owned_recovery_lifecycle(
            self.db_path,
            item_id=self.item.id,
            owner="owner-a",
            ownership_metadata={"kind": "owned-recovery", "note": "phase11"},
            session_key="phase11.session",
            session_metadata={"source": "unit-test"},
            candidate_score=0.75,
            candidate_reason={"kind": "resume", "detail": "phase11 ordered recovery"},
        )

        recovery_evidence_text = json.dumps(
            {
                "candidate_id": started["candidate_id"],
                "item_id": self.item.id,
                "outcome": "resume_recovery_dismissed",
                "session_id": started["session_id"],
                "session_key": "phase11.session",
                "terminal_status": "dismissed",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        recovery_evidence_id = self.repo.add_evidence(
            self.item.id,
            evidence_text=recovery_evidence_text,
            evidence_uri=RECOVERY_EVIDENCE_URI,
            created_by=RECOVERY_CREATED_BY,
        )

        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE sessions SET status = ?, ended_at = ? WHERE id = ?",
                ("dismissed", "2026-04-27T00:00:00+00:00", started["session_id"]),
            )
            connection.commit()

        ownership_before = self._ownership_row(started["ownership_id"])
        self.assertEqual(ownership_before["status"], "claimed")
        session_before = self._session_row(started["session_id"])
        self.assertEqual(session_before["status"], "dismissed")
        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)

        first = finalize_owned_recovery_lifecycle(
            self.db_path,
            ownership_id=started["ownership_id"],
            session_id=started["session_id"],
            candidate_id=started["candidate_id"],
            owner="owner-a",
        )
        second = finalize_owned_recovery_lifecycle(
            self.db_path,
            ownership_id=started["ownership_id"],
            session_id=started["session_id"],
            candidate_id=started["candidate_id"],
            owner="owner-a",
        )

        self.assertEqual(first["recovery_status"], "dismissed")
        self.assertEqual(first["ownership_status"], "completed")
        self.assertFalse(first["recovery_evidence_written"])
        self.assertTrue(first["ownership_evidence_written"])
        self.assertEqual(first["recovery_evidence_id"], recovery_evidence_id)

        self.assertEqual(second["recovery_status"], "dismissed")
        self.assertEqual(second["ownership_status"], "completed")
        self.assertFalse(second["recovery_evidence_written"])
        self.assertFalse(second["ownership_evidence_written"])
        self.assertEqual(second["recovery_evidence_id"], recovery_evidence_id)
        self.assertEqual(first["ownership_evidence_id"], second["ownership_evidence_id"])

        ownership_after = self._ownership_row(started["ownership_id"])
        self.assertEqual(ownership_after["status"], "completed")
        self.assertIsNotNone(ownership_after["completed_at"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 2)
        self.assertEqual(
            {row["evidence_uri"] for row in evidence_rows},
            {"ace://phase3b/recovery-outcome", "ace://phase4/runtime-ownership-outcome"},
        )


if __name__ == "__main__":
    unittest.main()
