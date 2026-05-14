from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ace.cost_guardrails import (
    CostGuardrailPolicy,
    get_cost_guardrail_status,
    load_cost_guardrail_policy_from_env,
    record_cost_usage,
)
from ace.storage import bootstrap_db, connect


class CostGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "ace.db"
        bootstrap_db(self.db_path)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_record_cost_usage_persists_local_ledger_row(self) -> None:
        record = record_cost_usage(
            self.db_path,
            cost_cents=12,
            tokens=345,
            session_count=1,
            source="unit-test",
            source_session="session-1",
            recorded_at="2026-05-14T00:00:00Z",
        )

        self.assertEqual(record["cost_cents"], 12)
        with connect(self.db_path) as connection:
            row = connection.execute(
                "SELECT recorded_at, cost_cents, tokens, session_count, source, source_session FROM cost_usage"
            ).fetchone()
        self.assertEqual(dict(row), record)

    def test_status_blocks_when_cost_limit_is_reached(self) -> None:
        record_cost_usage(self.db_path, cost_cents=100, tokens=10, session_count=1)

        status = get_cost_guardrail_status(
            self.db_path,
            policy=CostGuardrailPolicy(cost_limit_cents=100, token_limit=0, session_count_limit=0),
        )

        self.assertTrue(status.blocked)
        self.assertEqual(status.reason, "cost_limit_exceeded")
        self.assertEqual(status.used_cost_cents, 100)

    def test_status_blocks_when_token_limit_is_reached(self) -> None:
        record_cost_usage(self.db_path, cost_cents=0, tokens=50, session_count=0)

        status = get_cost_guardrail_status(
            self.db_path,
            policy=CostGuardrailPolicy(cost_limit_cents=0, token_limit=50, session_count_limit=0),
        )

        self.assertTrue(status.blocked)
        self.assertEqual(status.reason, "token_limit_exceeded")

    def test_status_blocks_when_session_limit_is_reached(self) -> None:
        record_cost_usage(self.db_path, cost_cents=0, tokens=0, session_count=2)

        status = get_cost_guardrail_status(
            self.db_path,
            policy=CostGuardrailPolicy(cost_limit_cents=0, token_limit=0, session_count_limit=2),
        )

        self.assertTrue(status.blocked)
        self.assertEqual(status.reason, "session_count_limit_exceeded")

    def test_zero_limits_are_unlimited(self) -> None:
        record_cost_usage(self.db_path, cost_cents=999, tokens=999, session_count=999)

        status = get_cost_guardrail_status(self.db_path, policy=CostGuardrailPolicy())

        self.assertFalse(status.blocked)
        self.assertIsNone(status.reason)

    def test_policy_loads_non_negative_integer_environment(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "ACE_COST_LIMIT_CENTS": "123",
                "ACE_TOKEN_LIMIT": "456",
                "ACE_SESSION_COUNT_LIMIT": "7",
            },
        ):
            policy = load_cost_guardrail_policy_from_env()

        self.assertEqual(policy.cost_limit_cents, 123)
        self.assertEqual(policy.token_limit, 456)
        self.assertEqual(policy.session_count_limit, 7)

    def test_negative_usage_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            record_cost_usage(self.db_path, cost_cents=-1)
