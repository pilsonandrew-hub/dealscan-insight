from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ace.storage import (
    append_event,
    bootstrap_db,
    compute_event_hash,
    connect,
    new_id,
    repair_event_hash_chain_for_legacy_races,
    utc_now,
    verify_event_hash_chain,
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

    def test_verify_event_hash_chain_detects_payload_tampering(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(connection, event_type="item.first", payload={"n": 1})
            connection.commit()
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

    def test_repair_event_hash_chain_repairs_legacy_concurrent_tail_race_only(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            first_id = append_event(
                connection,
                event_type="item.first",
                payload={"n": 1},
                created_at="2026-05-13T00:00:00Z",
            )
            connection.commit()
            first_hash = connection.execute(
                "SELECT event_hash FROM events WHERE event_id = ?",
                (first_id,),
            ).fetchone()["event_hash"]
            second_hash = compute_event_hash(
                event_id="evt_second",
                item_id=None,
                event_type="item.second",
                payload_json='{"n":2}',
                actor=None,
                source=None,
                session_id=None,
                created_at="2026-05-13T00:00:01Z",
                previous_event_hash=first_hash,
            )
            third_hash = compute_event_hash(
                event_id="evt_third",
                item_id=None,
                event_type="item.third",
                payload_json='{"n":3}',
                actor=None,
                source=None,
                session_id=None,
                created_at="2026-05-13T00:00:02Z",
                previous_event_hash=first_hash,
            )
            connection.execute(
                """
                INSERT INTO events (
                    event_id, item_id, event_type, payload_json, actor, source, session_id,
                    created_at, previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("evt_second", None, "item.second", '{"n":2}', None, None, None, "2026-05-13T00:00:01Z", first_hash, second_hash),
            )
            connection.execute(
                """
                INSERT INTO events (
                    event_id, item_id, event_type, payload_json, actor, source, session_id,
                    created_at, previous_event_hash, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("evt_third", None, "item.third", '{"n":3}', None, None, None, "2026-05-13T00:00:02Z", first_hash, third_hash),
            )
            connection.commit()

        ok, detail = verify_event_hash_chain(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "event evt_third has broken previous_event_hash")

        with connect(self.db_path) as connection:
            repaired = repair_event_hash_chain_for_legacy_races(connection)
            connection.commit()

        self.assertEqual(repaired, 1)
        self.assertEqual(verify_event_hash_chain(self.db_path), (True, None))

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
