import unittest
from unittest.mock import patch

from webapp.routers import lifecycle


class _FakeResult:
    data = [{"id": "one"}, {"id": "two"}]


class _FakeQuery:
    def __init__(self):
        self.updated = None
        self.calls = []

    def update(self, payload):
        self.updated = payload
        self.calls.append(("update", payload))
        return self

    def lt(self, column, value):
        self.calls.append(("lt", column, value))
        return self

    def eq(self, column, value):
        self.calls.append(("eq", column, value))
        return self

    def execute(self):
        self.calls.append(("execute",))
        return _FakeResult()


class _FakeClient:
    def __init__(self):
        self.query = _FakeQuery()

    def table(self, name):
        assert name == "opportunities"
        return self.query


class LifecycleTests(unittest.TestCase):
    def test_expire_stale_deals_deactivates_without_status_column_dependency(self):
        client = _FakeClient()
        with patch.object(lifecycle, "_supabase_client", client):
            result = lifecycle.expire_stale_deals(max_age_days=3)

        self.assertEqual(result["expired"], 2)
        self.assertEqual(client.query.updated, {"is_active": False})
        self.assertIn(("eq", "is_active", True), client.query.calls)
        self.assertNotIn(("neq", "status", "expired"), client.query.calls)


if __name__ == "__main__":
    unittest.main()
