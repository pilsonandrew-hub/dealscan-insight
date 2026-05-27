from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ace.filter_health import (
    build_filter_health_rows,
    drift_warnings,
    propose_filter_rows,
    run_filter_health_command,
)
from ace.storage import bootstrap_db


class FilterHealthTests(unittest.TestCase):
    def test_propose_filter_signal_noise_ratio(self) -> None:
        records = [
            {
                "decided_at": "2026-05-10T12:00:00Z",
                "parser_rule": "commitment_i_will",
                "decision": "accept",
            },
            {
                "decided_at": "2026-05-11T12:00:00Z",
                "parser_rule": "commitment_i_will",
                "decision": "reject",
            },
            {
                "decided_at": "2026-05-12T12:00:00Z",
                "parser_rule": "commitment_i_will",
                "decision": "reject",
            },
            {
                "decided_at": "2026-06-01T12:00:00Z",
                "parser_rule": "commitment_i_will",
                "decision": "accept",
            },
        ]
        rows = propose_filter_rows(records, month="2026-05")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.filter_id, "propose:commitment_i_will")
        self.assertEqual(row.signal, 1)
        self.assertEqual(row.noise, 2)
        self.assertEqual(row.ratio, 0.33)
        self.assertEqual(row.status, "watch:weak_signal")

    def test_drift_warning_for_low_ratio(self) -> None:
        records = [
            {"decided_at": "2026-05-01T00:00:00Z", "parser_rule": "commitment_let_me", "decision": "reject"},
            {"decided_at": "2026-05-02T00:00:00Z", "parser_rule": "commitment_let_me", "decision": "reject"},
        ]
        rows = propose_filter_rows(records, month="2026-05")
        warnings = drift_warnings(rows)
        self.assertEqual(len(warnings), 1)
        self.assertIn("drifting", warnings[0])

    def test_telegram_direct_work_outcomes_in_month(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "ace.db"
            bootstrap_db(db_path)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    INSERT INTO items (
                        id, item_type, title, state, source, source_session,
                        created_at, updated_at, last_event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "item_tg_signal",
                        "work",
                        "approved work",
                        "APPROVED",
                        "telegram/direct",
                        "telegram:1:1",
                        "2026-05-15T00:00:00Z",
                        "2026-05-15T00:00:00Z",
                        "evt_tg_signal",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO events (
                        event_id, item_id, event_type, payload_json, created_at, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "evt_tg_signal",
                        "item_tg_signal",
                        "item.created",
                        json.dumps({"parser_rule": "bounded_direct_work_rule"}),
                        "2026-05-15T00:00:00Z",
                        "0" * 64,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO items (
                        id, item_type, title, state, source, source_session,
                        created_at, updated_at, last_event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "item_tg_noise",
                        "work",
                        "dropped work",
                        "DROPPED",
                        "telegram/direct",
                        "telegram:1:2",
                        "2026-05-16T00:00:00Z",
                        "2026-05-16T00:00:00Z",
                        "evt_tg_noise",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO events (
                        event_id, item_id, event_type, payload_json, created_at, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "evt_tg_noise",
                        "item_tg_noise",
                        "item.created",
                        json.dumps({"parser_rule": "bounded_direct_work_rule"}),
                        "2026-05-16T00:00:00Z",
                        "0" * 64,
                    ),
                )
                connection.commit()

            log_path = Path(tmpdir) / "decisions.jsonl"
            rows = build_filter_health_rows(db_path=db_path, month="2026-05", decisions_log=log_path)
            telegram_rows = [row for row in rows if row.filter_id.startswith("telegram:")]
            self.assertEqual(len(telegram_rows), 1)
            self.assertEqual(telegram_rows[0].signal, 1)
            self.assertEqual(telegram_rows[0].noise, 1)
            self.assertEqual(telegram_rows[0].ratio, 0.5)

    def test_invalid_month_returns_error(self) -> None:
        code = run_filter_health_command(month="2026-13")
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
