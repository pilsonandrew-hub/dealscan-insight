from __future__ import annotations

import re
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from ace.storage import (
    append_event,
    bootstrap_db,
    compute_event_hash,
    connect,
    new_id,
    utc_now,
    verify_audit_integrity,
    verify_evidence_consistency,
    verify_event_hash_chain,
    verify_governed_run_integrity,
    verify_runtime_instance_integrity,
)


class StorageContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "nested" / "ace.db"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_bootstrap_db_creates_parent_directory_and_db_file(self) -> None:
        returned = bootstrap_db(self.db_path)
        self.assertEqual(returned, self.db_path)
        self.assertTrue(self.db_path.parent.exists())
        self.assertTrue(self.db_path.exists())


    def test_bootstrap_db_creates_local_alert_log_for_transport_proof(self) -> None:
        bootstrap_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(alert_log)").fetchall()}
        self.assertIn("message_id", columns)
        self.assertIn("delivery_state", columns)
        self.assertIn("metadata_json", columns)

    def test_bootstrap_db_enforces_unique_non_null_item_provenance(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            now = utc_now()
            connection.execute(
                """
                INSERT INTO items (
                    id, item_type, title, state, source, source_session, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("item_one", "task", "First", "TRIAGE", "source-a", "session-a", now, now),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    """
                    INSERT INTO items (
                        id, item_type, title, state, source, source_session, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    ("item_two", "task", "Second", "TRIAGE", "source-a", "session-a", now, now),
                )

    def test_bootstrap_db_allows_multiple_items_without_full_provenance(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            now = utc_now()
            connection.execute(
                """
                INSERT INTO items (id, item_type, title, state, source, source_session, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("item_one", "task", "First", "TRIAGE", None, None, now, now),
            )
            connection.execute(
                """
                INSERT INTO items (id, item_type, title, state, source, source_session, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("item_two", "task", "Second", "TRIAGE", None, None, now, now),
            )
            count = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]

        self.assertEqual(count, 2)

    def test_utc_now_returns_zulu_timestamp(self) -> None:
        value = utc_now()
        self.assertTrue(value.endswith("Z"))
        self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

    def test_new_id_uses_prefix_and_hex_suffix(self) -> None:
        one = new_id("evt")
        two = new_id("evt")
        self.assertRegex(one, r"^evt_[0-9a-f]{32}$")
        self.assertRegex(two, r"^evt_[0-9a-f]{32}$")
        self.assertNotEqual(one, two)

    def test_connect_enables_foreign_keys(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(enabled, 1)

    def test_append_event_persists_json_sorted_and_returns_event_id(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(
                connection,
                event_type="item.tested",
                payload={"b": 2, "a": 1},
                actor="tester",
                source="unit-test",
                session_id="sess-1",
            )
            connection.commit()

        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT event_id, event_type, payload_json, actor, source, session_id FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()

        self.assertEqual(row["event_id"], event_id)
        self.assertEqual(row["event_type"], "item.tested")
        self.assertEqual(row["payload_json"], '{"a":1,"b":2}')
        self.assertEqual(row["actor"], "tester")
        self.assertEqual(row["source"], "unit-test")
        self.assertEqual(row["session_id"], "sess-1")

    def test_append_event_honors_explicit_ids_and_created_at(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(
                connection,
                event_type="item.custom",
                payload={"x": "y"},
                event_id="evt_custom",
                created_at="2026-04-25T00:00:00Z",
            )
            connection.commit()

        self.assertEqual(event_id, "evt_custom")
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT created_at, payload_json FROM events WHERE event_id = ?",
                ("evt_custom",),
            ).fetchone()

        self.assertEqual(row["created_at"], "2026-04-25T00:00:00Z")
        self.assertEqual(row["payload_json"], '{"x":"y"}')

    def test_append_event_defaults_to_empty_payload_object(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(connection, event_type="item.empty")
            connection.commit()

        with connect(self.db_path) as connection:
            payload_json = connection.execute(
                "SELECT payload_json FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()[0]

        self.assertEqual(payload_json, "{}")

    def test_append_event_writes_tamper_evident_hash_chain(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            first_id = append_event(connection, event_type="item.first", payload={"n": 1})
            second_id = append_event(connection, event_type="item.second", payload={"n": 2})
            connection.commit()

        with connect(self.db_path) as connection:
            rows = connection.execute(
                """
                SELECT event_id, previous_event_hash, event_hash
                FROM events
                ORDER BY id ASC
                """
            ).fetchall()

        self.assertEqual([row["event_id"] for row in rows], [first_id, second_id])
        self.assertIsNone(rows[0]["previous_event_hash"])
        self.assertRegex(rows[0]["event_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(rows[1]["previous_event_hash"], rows[0]["event_hash"])
        self.assertRegex(rows[1]["event_hash"], r"^[0-9a-f]{64}$")
        self.assertNotEqual(rows[0]["event_hash"], rows[1]["event_hash"])
        self.assertEqual(verify_event_hash_chain(self.db_path), (True, None))

    def test_verify_event_hash_chain_detects_payload_tampering_if_external_trigger_removed(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(connection, event_type="item.first", payload={"n": 1})
            connection.commit()

        # Simulate a hostile filesystem-level actor that bypasses ACE's guarded
        # connection API and removes DB triggers first.
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DROP TRIGGER ace_events_no_update")
            connection.execute(
                "UPDATE events SET payload_json = ? WHERE event_id = ?",
                ('{"n":999}', event_id),
            )
            connection.commit()

        ok, detail = verify_event_hash_chain(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, f"event {event_id} hash mismatch")

    def test_bootstrap_backfills_legacy_event_hashes_without_claiming_external_provenance(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            connection.execute(
                """
                INSERT INTO events (event_id, item_id, event_type, payload_json, actor, source, session_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("evt_legacy", None, "item.legacy", "{}", None, None, None, "2026-05-13T00:00:00Z"),
            )
            connection.commit()

        bootstrap_db(self.db_path)

        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT previous_event_hash, event_hash FROM events WHERE event_id = ?",
                ("evt_legacy",),
            ).fetchone()
        self.assertIsNone(row["previous_event_hash"])
        self.assertRegex(row["event_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(verify_event_hash_chain(self.db_path), (True, None))

    def test_connect_sets_busy_timeout_for_live_supervisor_contention(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            busy_timeout_ms = connection.execute("PRAGMA busy_timeout").fetchone()[0]

        self.assertEqual(busy_timeout_ms, 30000)

    def test_events_table_rejects_direct_update_after_bootstrap(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(connection, event_type="item.first", payload={"n": 1})
            connection.commit()
            with self.assertRaises(sqlite3.DatabaseError) as exc:
                connection.execute(
                    "UPDATE events SET payload_json = ? WHERE event_id = ?",
                    ('{"n":999}', event_id),
                )

        self.assertIn("not authorized", str(exc.exception))

    def test_events_table_rejects_direct_delete_after_bootstrap(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(connection, event_type="item.first", payload={"n": 1})
            connection.commit()
            with self.assertRaises(sqlite3.DatabaseError) as exc:
                connection.execute("DELETE FROM events WHERE event_id = ?", (event_id,))

        self.assertIn("not authorized", str(exc.exception))

    def test_audit_verify_fails_loudly_when_schema_needs_maintenance(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.commit()

        results = verify_audit_integrity(self.db_path)

        self.assertFalse(all(ok for ok, _reason in results.values()))
        for ok, reason in results.values():
            self.assertFalse(ok)
            self.assertIsNotNone(reason)
            self.assertIn("schema maintenance required before audit verify", reason or "")
            self.assertIn("run explicit ACE maintenance migration/bootstrap first", reason or "")


    def test_verify_evidence_consistency_passes_for_valid_evidence(self) -> None:
        from ace.repository import ItemRepository

        repo = ItemRepository(self.db_path)
        item = repo.create_item(item_type="task", title="Evidence consistency")
        repo.add_evidence(item.id, evidence_text="supporting proof")

        self.assertEqual(verify_evidence_consistency(self.db_path), (True, None))

    def test_verify_evidence_consistency_detects_missing_item(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO evidence (id, item_id, evidence_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                ("evidence_orphan_item", "missing_item", "orphan proof", utc_now()),
            )
            connection.commit()

        ok, detail = verify_evidence_consistency(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "evidence evidence_orphan_item references missing item missing_item")

    def test_verify_evidence_consistency_detects_missing_event(self) -> None:
        from ace.repository import ItemRepository

        repo = ItemRepository(self.db_path)
        item = repo.create_item(item_type="task", title="Evidence event consistency")
        with connect(self.db_path) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO evidence (id, item_id, evidence_text, created_at, event_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("evidence_orphan_event", item.id, "orphan event proof", utc_now(), "evt_missing"),
            )
            connection.commit()

        ok, detail = verify_evidence_consistency(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "evidence evidence_orphan_event references missing event evt_missing")

    def test_verify_governed_run_integrity_passes_for_empty_database(self) -> None:
        bootstrap_db(self.db_path)

        self.assertEqual(verify_governed_run_integrity(self.db_path), (True, None))

    def test_verify_governed_run_integrity_detects_invalid_status(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            now = utc_now()
            connection.execute(
                """
                INSERT INTO governed_runs (run_id, run_kind, trigger_kind, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("run_invalid_status", "ace_cycle", "operator", "mystery", now),
            )
            connection.commit()

        ok, detail = verify_governed_run_integrity(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "governed_run run_invalid_status has invalid status mystery")

    def test_verify_governed_run_integrity_detects_completed_without_ended_at(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            now = utc_now()
            connection.execute(
                """
                INSERT INTO governed_runs (run_id, run_kind, trigger_kind, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("run_completed_open", "ace_cycle", "operator", "completed", now),
            )
            connection.commit()

        ok, detail = verify_governed_run_integrity(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "governed_run run_completed_open has terminal status completed without ended_at")

    def test_verify_runtime_instance_integrity_passes_for_empty_database(self) -> None:
        bootstrap_db(self.db_path)

        self.assertEqual(verify_runtime_instance_integrity(self.db_path), (True, None))

    def test_verify_runtime_instance_integrity_detects_invalid_status(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            now = utc_now()
            connection.execute(
                """
                INSERT INTO runtime_instances (
                    runtime_instance_id, runtime_family, status, metadata_json,
                    stale_after_seconds, started_at, last_seen_at,
                    startup_status, shutdown_status, recovery_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "runtime_invalid_status",
                    "single_tenant_local_supervisor",
                    "mystery",
                    "{}",
                    60,
                    now,
                    now,
                    "starting",
                    "not_requested",
                    "not_requested",
                    now,
                    now,
                ),
            )
            connection.commit()

        ok, detail = verify_runtime_instance_integrity(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "runtime_instance runtime_invalid_status has invalid status mystery")

    def test_verify_runtime_instance_integrity_detects_completed_shutdown_without_timestamp(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            now = utc_now()
            connection.execute(
                """
                INSERT INTO runtime_instances (
                    runtime_instance_id, runtime_family, status, metadata_json,
                    stale_after_seconds, started_at, last_seen_at, ended_at,
                    startup_status, startup_completed_at,
                    shutdown_status, shutdown_requested_at, shutdown_completed_at,
                    recovery_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "runtime_bad_shutdown",
                    "single_tenant_local_supervisor",
                    "stopped",
                    "{}",
                    60,
                    now,
                    now,
                    now,
                    "completed",
                    now,
                    "completed",
                    now,
                    None,
                    "not_requested",
                    now,
                    now,
                ),
            )
            connection.commit()

        ok, detail = verify_runtime_instance_integrity(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "runtime_instance runtime_bad_shutdown has completed shutdown without shutdown_completed_at")

    def test_verify_audit_integrity_returns_all_four_checks(self) -> None:
        bootstrap_db(self.db_path)

        results = verify_audit_integrity(self.db_path)

        self.assertEqual(
            set(results),
            {
                "event_hash_chain",
                "evidence_consistency",
                "governed_run_integrity",
                "runtime_instance_integrity",
            },
        )
        self.assertTrue(all(ok for ok, _reason in results.values()))

    def test_append_event_respects_foreign_key_constraint_for_missing_item(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                append_event(
                    connection,
                    event_type="item.bad_ref",
                    item_id="missing-item",
                )


if __name__ == "__main__":
    unittest.main()
