from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ace.repository import ItemRepository, ValidationError
from ace.storage import bootstrap_db, connect


class RuntimeOwnershipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)
        self.repo = ItemRepository(self.db_path)
        self.item = self.repo.create_item(item_type="note", title="Runtime ownership target")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

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
                WHERE item_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (self.item.id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def test_register_claim_and_release_writes_one_outcome_evidence_row(self) -> None:
        from ace.runtime_ownership import (
            OWNERSHIP_CREATED_BY,
            OWNERSHIP_EVIDENCE_URI,
            claim_runtime_ownership,
            register_runtime_ownership,
            release_runtime_ownership,
        )

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )
        self.assertEqual(registration["status"], "queued")
        self.assertEqual(registration["item_id"], self.item.id)

        claimed = claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")
        self.assertEqual(claimed["status"], "claimed")

        released = release_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")
        self.assertEqual(released["status"], "completed")
        self.assertTrue(released["evidence_written"])
        self.assertIsInstance(released["evidence_id"], str)

        ownership_row = self._ownership_row(registration["ownership_id"])
        self.assertEqual(ownership_row["status"], "completed")
        self.assertIsNotNone(ownership_row["claimed_at"])
        self.assertIsNotNone(ownership_row["completed_at"])
        self.assertIsNone(ownership_row["error_message"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["evidence_uri"], OWNERSHIP_EVIDENCE_URI)
        self.assertEqual(evidence_rows[0]["created_by"], OWNERSHIP_CREATED_BY)
        self.assertEqual(
            json.loads(evidence_rows[0]["evidence_text"]),
            {
                "item_id": self.item.id,
                "metadata": {"kind": "bounded-work", "note": "phase4 ownership proof"},
                "outcome": "ownership_released_completed",
                "ownership_id": registration["ownership_id"],
                "owner": "owner-a",
            },
        )

    def test_register_is_deterministic_and_reuses_existing_row(self) -> None:
        from ace.runtime_ownership import register_runtime_ownership

        first = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )
        second = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )

        self.assertEqual(first["ownership_id"], second["ownership_id"])
        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM action_queue WHERE id = ?",
                (first["ownership_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_claim_is_replay_safe_for_the_same_owner(self) -> None:
        from ace.runtime_ownership import claim_runtime_ownership, register_runtime_ownership

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )

        first = claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")
        second = claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        self.assertEqual(first["status"], "claimed")
        self.assertEqual(second["status"], "claimed")
        self.assertEqual(first["claimed_at"], second["claimed_at"])

    def test_claim_rejects_conflicting_owner(self) -> None:
        from ace.runtime_ownership import claim_runtime_ownership, register_runtime_ownership

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )
        claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        with self.assertRaises(ValidationError):
            claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-b")

    def test_register_rejects_malformed_metadata_with_zero_partial_writes(self) -> None:
        from ace.runtime_ownership import register_runtime_ownership

        with self.assertRaises(ValidationError):
            register_runtime_ownership(self.db_path, self.item.id, owner="owner-a", metadata="not-a-mapping")

        with connect(self.db_path) as connection:
            action_count = connection.execute("SELECT COUNT(*) FROM action_queue").fetchone()[0]
            evidence_count = connection.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            item_row = connection.execute(
                "SELECT owner FROM items WHERE id = ?",
                (self.item.id,),
            ).fetchone()
        self.assertEqual(action_count, 0)
        self.assertEqual(evidence_count, 0)
        self.assertIsNotNone(item_row)
        self.assertIsNone(item_row["owner"])

    def test_release_is_replay_safe_and_reuses_outcome_artifact(self) -> None:
        from ace.runtime_ownership import (
            claim_runtime_ownership,
            register_runtime_ownership,
            release_runtime_ownership,
        )

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )
        claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        first = release_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")
        second = release_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        self.assertEqual(first["status"], "completed")
        self.assertEqual(second["status"], "completed")
        self.assertEqual(first["evidence_id"], second["evidence_id"])
        self.assertTrue(first["evidence_written"])
        self.assertFalse(second["evidence_written"])

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE item_id = ? AND evidence_uri = ? AND created_by = ?",
                (self.item.id, "ace://phase4/runtime-ownership-outcome", "ace.phase4.runtime_ownership"),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_release_rejects_missing_target_with_explicit_failure(self) -> None:
        from ace.runtime_ownership import claim_runtime_ownership, register_runtime_ownership, release_runtime_ownership

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )
        claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        with sqlite3.connect(self.db_path) as raw_connection:
            raw_connection.execute("PRAGMA foreign_keys = OFF")
            raw_connection.execute("DELETE FROM items WHERE id = ?", (self.item.id,))
            raw_connection.commit()

        result = release_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn(self.item.id, result["error_message"])

        ownership_row = self._ownership_row(registration["ownership_id"])
        self.assertEqual(ownership_row["status"], "failed")
        self.assertIsNotNone(ownership_row["completed_at"])
        self.assertIsNotNone(ownership_row["error_message"])
        self.assertEqual(self._evidence_rows(), [])

    def test_release_rejects_malformed_persisted_payload_with_explicit_failure(self) -> None:
        from ace.runtime_ownership import claim_runtime_ownership, register_runtime_ownership, release_runtime_ownership

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )
        claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        with connect(self.db_path) as connection:
            connection.execute(
                "UPDATE action_queue SET payload_json = ? WHERE id = ?",
                ('{"broken":', registration["ownership_id"]),
            )
            connection.commit()

        result = release_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["evidence_written"])
        self.assertIsNone(result["evidence_id"])
        self.assertIn("ownership payload", result["error_message"])

        ownership_row = self._ownership_row(registration["ownership_id"])
        self.assertEqual(ownership_row["status"], "failed")
        self.assertIsNotNone(ownership_row["completed_at"])
        self.assertIsNotNone(ownership_row["error_message"])
        self.assertEqual(self._evidence_rows(), [])

    def test_register_rejects_conflicting_owner_for_same_work_item(self) -> None:
        from ace.runtime_ownership import register_runtime_ownership

        first = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
        )

        with self.assertRaises(ValidationError):
            register_runtime_ownership(
                self.db_path,
                self.item.id,
                owner="owner-b",
                metadata={"kind": "bounded-work", "note": "phase4 ownership proof"},
            )

        with connect(self.db_path) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM action_queue WHERE id = ?",
                (first["ownership_id"],),
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_release_heals_interrupted_success_without_duplicate_evidence(self) -> None:
        from ace.runtime_ownership import (
            OWNERSHIP_CREATED_BY,
            OWNERSHIP_EVIDENCE_URI,
            claim_runtime_ownership,
            register_runtime_ownership,
            release_runtime_ownership,
        )

        registration = register_runtime_ownership(
            self.db_path,
            self.item.id,
            owner="owner-a",
            metadata={"kind": "bounded-work", "note": "phase9 durability proof"},
        )
        claim_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        interrupted_evidence = {
            "item_id": self.item.id,
            "metadata": {"kind": "bounded-work", "note": "phase9 durability proof"},
            "outcome": "ownership_released_completed",
            "ownership_id": registration["ownership_id"],
            "owner": "owner-a",
        }
        evidence_id = self.repo.add_evidence(
            self.item.id,
            evidence_text=json.dumps(interrupted_evidence, sort_keys=True, separators=(",", ":")),
            evidence_uri=OWNERSHIP_EVIDENCE_URI,
            created_by=OWNERSHIP_CREATED_BY,
        )

        interrupted_row = self._ownership_row(registration["ownership_id"])
        self.assertEqual(interrupted_row["status"], "claimed")
        self.assertEqual(len(self._evidence_rows()), 1)

        result = release_runtime_ownership(self.db_path, registration["ownership_id"], owner="owner-a")

        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["evidence_written"])
        self.assertEqual(result["evidence_id"], evidence_id)

        ownership_row = self._ownership_row(registration["ownership_id"])
        self.assertEqual(ownership_row["status"], "completed")
        self.assertIsNotNone(ownership_row["completed_at"])
        self.assertIsNone(ownership_row["error_message"])

        evidence_rows = self._evidence_rows()
        self.assertEqual(len(evidence_rows), 1)
        self.assertEqual(evidence_rows[0]["evidence_uri"], OWNERSHIP_EVIDENCE_URI)
        self.assertEqual(result["evidence_id"], evidence_id)


if __name__ == "__main__":
    unittest.main()
