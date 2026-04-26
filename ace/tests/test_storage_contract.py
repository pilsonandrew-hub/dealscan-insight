from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from ace.storage import append_event, bootstrap_db, connect, new_id, utc_now


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
