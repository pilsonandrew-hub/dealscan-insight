from __future__ import annotations

import re
import sqlite3
import json
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

from ace.storage import (
    CUTOVER_EVENT_TYPE,
    CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
    _disable_event_insert,
    _enable_event_insert,
    DESIGN_COMMIT_HASH,
    LEGACY_KNOWN_DEFECT_COUNTS,
    POST_CUTOVER_CHAIN_POLICY,
    REQUIRED_CUTOVER_PAYLOAD_FIELDS,
    append_cutover_genesis_event,
    append_event,
    bootstrap_db,
    compute_event_hash,
    compute_event_hash_from_mapping,
    connect,
    new_id,
    utc_now,
    legacy_chain_inventory,
    post_cutover_event_hash_chain,
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

    def test_bootstrap_db_creates_semantic_event_lookup_index(self) -> None:
        bootstrap_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            indexes = {row[1] for row in connection.execute("PRAGMA index_list(events)").fetchall()}
        self.assertIn("idx_events_item_type_payload", indexes)

    def test_compute_event_hash_mapping_adapter_matches_public_api(self) -> None:
        event = {
            "event_id": "evt_hash_contract",
            "item_id": None,
            "event_type": "item.hash_contract",
            "payload_json": '{"a":1}',
            "actor": "tester",
            "source": "unit-test",
            "session_id": "sess-1",
            "created_at": "2026-05-23T00:00:00Z",
            "previous_event_hash": None,
        }
        self.assertEqual(compute_event_hash_from_mapping(event), compute_event_hash(**event))

    def test_append_event_joins_existing_caller_owned_transaction(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            connection.execute("BEGIN")
            event_id = append_event(connection, event_type="item.caller_transaction")
            connection.commit()

        self.assertEqual(verify_event_hash_chain(self.db_path), (True, None))
        with connect(self.db_path) as connection:
            row = connection.execute("SELECT event_type FROM events WHERE event_id = ?", (event_id,)).fetchone()
        self.assertEqual(row["event_type"], "item.caller_transaction")


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
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    item_id TEXT,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    actor TEXT,
                    source TEXT,
                    session_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
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

    def test_bootstrap_adds_nullable_event_sequence_without_mutating_legacy_rows(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE events (
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
                    event_hash TEXT
                )
                """
            )
            connection.execute(
                "INSERT INTO events (event_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)",
                ("evt_legacy", "item.legacy", "{}", "2026-05-13T00:00:00Z"),
            )
            connection.commit()

        bootstrap_db(self.db_path)

        with connect(self.db_path) as connection:
            column = next(row for row in connection.execute("PRAGMA table_info(events)") if row["name"] == "event_sequence")
            row = connection.execute("SELECT event_sequence FROM events WHERE event_id = ?", ("evt_legacy",)).fetchone()
        self.assertEqual(column["notnull"], 0)
        self.assertIsNone(row["event_sequence"])

    def test_bootstrap_preserves_b1_residue_event_sequence_values_as_inert_legacy(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                CREATE TABLE events (
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
                    event_sequence INTEGER NOT NULL
                )
                """
            )
            connection.execute("CREATE UNIQUE INDEX idx_events_event_sequence ON events(event_sequence)")
            connection.execute(
                "INSERT INTO events (event_id, event_type, payload_json, created_at, event_sequence) VALUES (?, ?, ?, ?, ?)",
                ("evt_b1_residue", "item.legacy", "{}", "2026-05-13T00:00:00Z", 99),
            )
            connection.commit()

        bootstrap_db(self.db_path)

        with connect(self.db_path) as connection:
            column = next(row for row in connection.execute("PRAGMA table_info(events)") if row["name"] == "event_sequence")
            row = connection.execute("SELECT event_sequence FROM events WHERE event_id = ?", ("evt_b1_residue",)).fetchone()
            unique_sequence_indexes = [
                row["name"]
                for row in connection.execute("PRAGMA index_list(events)")
                if row["unique"] and any(
                    info["name"] == "event_sequence"
                    for info in connection.execute(f"PRAGMA index_info({row['name']})")
                )
            ]
        self.assertEqual(column["notnull"], 0)
        self.assertEqual(row["event_sequence"], 99)
        self.assertEqual(unique_sequence_indexes, [])

    def test_append_event_transition_window_leaves_event_sequence_null_before_cutover(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            event_id = append_event(connection, event_type="item.transition", payload={"phase": "pre-cutover"})
            connection.commit()

        with connect(self.db_path) as connection:
            row = connection.execute("SELECT event_sequence FROM events WHERE event_id = ?", (event_id,)).fetchone()
        self.assertIsNone(row["event_sequence"])

    def test_append_event_rejects_cutover_event_type_on_normal_path(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            with self.assertRaises(ValueError):
                append_event(connection, event_type=CUTOVER_EVENT_TYPE, payload={"cutover_version": "v1.1"})

    def test_append_cutover_genesis_event_creates_boundary_and_segment_scoped_sequence(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            legacy_id = append_event(connection, event_type="item.legacy", payload={"legacy": True})
            connection.commit()

        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("DROP TRIGGER ace_events_no_update")
            connection.execute("UPDATE events SET event_sequence = 42 WHERE event_id = ?", (legacy_id,))
            connection.commit()

        with connect(self.db_path) as connection:
            cutover_id = append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_storage_contract.py",
                session_id="v1.1-cutover:test",
            )
            post_id = append_event(connection, event_type="item.post_cutover", payload={"post": True})
            connection.commit()

        with connect(self.db_path) as connection:
            rows = connection.execute(
                "SELECT event_id, event_sequence, previous_event_hash, payload_json, created_at FROM events ORDER BY id ASC"
            ).fetchall()
        self.assertEqual([row["event_id"] for row in rows], [legacy_id, cutover_id, post_id])
        self.assertEqual(rows[0]["event_sequence"], 42)
        self.assertEqual(rows[1]["event_sequence"], 1)
        self.assertIsNone(rows[1]["previous_event_hash"])
        self.assertEqual(rows[2]["event_sequence"], 2)
        cutover_payload = json.loads(rows[1]["payload_json"])
        self.assertEqual(set(cutover_payload), REQUIRED_CUTOVER_PAYLOAD_FIELDS)
        self.assertEqual(rows[1]["created_at"], cutover_payload["cutover_timestamp"])
        self.assertEqual(DESIGN_COMMIT_HASH, cutover_payload["design_commit_hash"])
        self.assertEqual(1, cutover_payload["legacy_event_count"])
        self.assertEqual(LEGACY_KNOWN_DEFECT_COUNTS, cutover_payload["legacy_known_defect_counts"])
        self.assertEqual(POST_CUTOVER_CHAIN_POLICY, cutover_payload["post_cutover_chain_policy"])
        self.assertEqual(post_cutover_event_hash_chain(self.db_path), (True, None))

    def test_append_cutover_genesis_event_overrides_caller_supplied_live_fields(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            legacy_id = append_event(connection, event_type="item.legacy", payload={"legacy": True})
            legacy_head = connection.execute("SELECT id, event_hash FROM events WHERE event_id = ?", (legacy_id,)).fetchone()
            cutover_id = append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_storage_contract.py",
                session_id="v1.1-cutover:test",
                payload={
                    "legacy_chain_head_row_id": -1,
                    "legacy_chain_head_event_id": "stale",
                    "legacy_chain_head_hash": "stale",
                    "legacy_event_count": -1,
                    "cutover_timestamp": "stale",
                    "design_commit_hash": "stale",
                },
            )
            row = connection.execute("SELECT payload_json, created_at FROM events WHERE event_id = ?", (cutover_id,)).fetchone()
            connection.commit()

        payload = json.loads(row["payload_json"])
        self.assertEqual(legacy_head["id"], payload["legacy_chain_head_row_id"])
        self.assertEqual(legacy_id, payload["legacy_chain_head_event_id"])
        self.assertEqual(legacy_head["event_hash"], payload["legacy_chain_head_hash"])
        self.assertEqual(1, payload["legacy_event_count"])
        self.assertEqual(row["created_at"], payload["cutover_timestamp"])
        self.assertEqual(DESIGN_COMMIT_HASH, payload["design_commit_hash"])

    def test_append_cutover_genesis_event_rejects_empty_payload_and_unauthorized_call(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            append_event(connection, event_type="item.legacy", payload={"legacy": True})
            with self.assertRaises(ValueError):
                append_cutover_genesis_event(
                    connection,
                    authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                    governing_decision_reference="test approval",
                    actor="test",
                    source="ace/tests/test_storage_contract.py",
                    session_id="v1.1-cutover:test",
                    payload={},
                )
            with self.assertRaises(PermissionError):
                append_cutover_genesis_event(
                    connection,
                    authorization_token="wrong",
                    governing_decision_reference="test approval",
                    actor="test",
                    source="ace/tests/test_storage_contract.py",
                    session_id="v1.1-cutover:test",
                )

    def test_post_cutover_verifier_fails_loudly_on_null_sequence_after_boundary(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            append_event(connection, event_type="item.legacy", payload={"legacy": True})
            cutover_id = append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_storage_contract.py",
                session_id="v1.1-cutover:test",
            )
            connection.commit()

        bad_created_at = utc_now()
        bad_hash = compute_event_hash(
            event_id="evt_bad",
            item_id=None,
            event_type="item.bad",
            payload_json="{}",
            actor=None,
            source=None,
            session_id=None,
            created_at=bad_created_at,
            previous_event_hash="0" * 64,
        )
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                """
                INSERT INTO events (event_id, event_type, payload_json, created_at, previous_event_hash, event_hash)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("evt_bad", "item.bad", "{}", bad_created_at, "0" * 64, bad_hash),
            )
            connection.commit()

        ok, detail = post_cutover_event_hash_chain(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "post-cutover event evt_bad has NULL event_sequence")

    def test_post_cutover_verifier_fails_loudly_on_duplicate_sequence(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            append_event(connection, event_type="item.legacy", payload={"legacy": True})
            append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_storage_contract.py",
                session_id="v1.1-cutover:test",
            )
            post_id = append_event(connection, event_type="item.post", payload={"post": True})
            connection.commit()
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("DROP TRIGGER ace_events_no_update")
            connection.execute("UPDATE events SET event_sequence = 1 WHERE event_id = ?", (post_id,))
            connection.commit()

        ok, detail = post_cutover_event_hash_chain(self.db_path)
        self.assertFalse(ok)
        self.assertEqual(detail, "duplicate post-cutover event_sequence 1")

    def test_append_cutover_genesis_event_insert_marker_removed_after_duplicate_failure(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            append_event(connection, event_type="item.legacy", payload={"legacy": True})
            append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_storage_contract.py",
                session_id="v1.1-cutover:test",
            )
            with self.assertRaises(ValueError):
                append_cutover_genesis_event(
                    connection,
                    authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                    governing_decision_reference="test approval",
                    actor="test",
                    source="ace/tests/test_storage_contract.py",
                    session_id="v1.1-cutover:test-second",
                )
            with self.assertRaises(sqlite3.DatabaseError) as exc:
                connection.execute(
                    """
                    INSERT INTO events (event_id, event_type, payload_json, created_at, event_hash, event_sequence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    ("evt_after_failed_cutover", "item.direct", "{}", utc_now(), "0" * 64, 2),
                )

        self.assertIn("not authorized", str(exc.exception))

    def test_append_event_post_cutover_positive_sequence_still_works_under_insert_guard(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            append_event(connection, event_type="item.legacy", payload={"legacy": True})
            append_cutover_genesis_event(
                connection,
                authorization_token=CUTOVER_EXECUTE_AUTHORIZATION_TOKEN,
                governing_decision_reference="test approval",
                actor="test",
                source="ace/tests/test_storage_contract.py",
                session_id="v1.1-cutover:test",
            )
            event_id = append_event(connection, event_type="item.after_cutover", payload={"after": True})
            connection.commit()

        with connect(self.db_path) as connection:
            row = connection.execute("SELECT event_sequence FROM events WHERE event_id = ?", (event_id,)).fetchone()

        self.assertEqual(row["event_sequence"], 2)
        self.assertEqual(post_cutover_event_hash_chain(self.db_path), (True, None))

    def test_installing_insert_guard_does_not_mutate_existing_event_rows(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            first = append_event(connection, event_type="item.first", payload={"n": 1})
            second = append_event(connection, event_type="item.second", payload={"n": 2})
            connection.commit()

        with closing(sqlite3.connect(self.db_path)) as connection:
            before = [tuple(row) for row in connection.execute("SELECT * FROM events ORDER BY id ASC").fetchall()]

        bootstrap_db(self.db_path)

        with closing(sqlite3.connect(self.db_path)) as connection:
            after = [tuple(row) for row in connection.execute("SELECT * FROM events ORDER BY id ASC").fetchall()]

        self.assertEqual(before, after)
        self.assertEqual([row[1] for row in after], [first, second])

    def test_legacy_chain_inventory_requires_disclosure_file(self) -> None:
        bootstrap_db(self.db_path)

        ok, detail = legacy_chain_inventory(self.db_path)

        self.assertTrue(ok)
        self.assertIn("disclosure_present=true", detail or "")

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

    def test_events_table_rejects_direct_insert_through_connect_after_bootstrap(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            with self.assertRaises(sqlite3.DatabaseError) as exc:
                connection.execute(
                    """
                    INSERT INTO events (event_id, event_type, payload_json, created_at, event_hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("evt_direct", "item.direct", "{}", utc_now(), "0" * 64),
                )

        self.assertIn("not authorized", str(exc.exception))

    def test_events_table_rejects_raw_insert_without_append_metadata_after_bootstrap(self) -> None:
        bootstrap_db(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection:
            with self.assertRaises(sqlite3.IntegrityError) as exc:
                connection.execute(
                    """
                    INSERT INTO events (event_id, event_type, payload_json, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    ("evt_raw", "item.raw", "{}", utc_now()),
                )

        self.assertIn("events table append requires append_event metadata", str(exc.exception))

    def test_event_insert_marker_is_removed_when_append_event_insert_fails(self) -> None:
        bootstrap_db(self.db_path)
        with connect(self.db_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                append_event(connection, event_type="item.bad_ref", item_id="missing-item")
            with self.assertRaises(sqlite3.DatabaseError) as exc:
                connection.execute(
                    """
                    INSERT INTO events (event_id, event_type, payload_json, created_at, event_hash)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("evt_after_failed_append", "item.direct", "{}", utc_now(), "0" * 64),
                )

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
        with closing(sqlite3.connect(self.db_path)) as connection:
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
        with closing(sqlite3.connect(self.db_path)) as connection:
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
                "legacy_chain_inventory",
                "event_hash_chain",
                "post_cutover_event_hash_chain",
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
