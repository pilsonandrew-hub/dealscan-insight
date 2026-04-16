import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone

os.environ.setdefault("SECRET_KEY", "test-secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from webapp.routers import analytics

# This module uses fakes for Supabase, auth, and source-health so the unit
# suite stays hermetic. Live backend integration coverage still depends on a
# real deployment environment, which is intentionally out of scope here.


class _QueryResult:
    def __init__(self, data=None, count=None):
        self.data = data or []
        self.count = count

    def execute(self):
        return self


class _TableQuery:
    def __init__(self, table_name: str, payloads: dict[str, dict[str, object]]):
        self.table_name = table_name
        self.payloads = payloads

    def select(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    @property
    def not_(self):
        return self

    def is_(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def gte(self, *_args, **_kwargs):
        return self

    def ilike(self, *_args, **_kwargs):
        return self

    def execute(self):
        payload = self.payloads.get(self.table_name, {})
        return _QueryResult(data=payload.get("data"), count=payload.get("count"))


class _RaisingTableQuery(_TableQuery):
    def __init__(self, table_name: str, payloads: dict[str, dict[str, object]], raise_on_execute: bool = False):
        super().__init__(table_name, payloads)
        self.raise_on_execute = raise_on_execute

    def execute(self):
        if self.raise_on_execute:
            raise RuntimeError(f"{self.table_name} query failed")
        return super().execute()


class _FakeSupabase:
    def __init__(self, payloads: dict[str, dict[str, object]]):
        self.payloads = payloads

    def table(self, table_name: str):
        return _TableQuery(table_name, self.payloads)


class _FakeSupabaseWithFailures(_FakeSupabase):
    def __init__(self, payloads: dict[str, dict[str, object]], failing_tables: set[str]):
        super().__init__(payloads)
        self.failing_tables = failing_tables

    def table(self, table_name: str):
        return _RaisingTableQuery(
            table_name,
            self.payloads,
            raise_on_execute=table_name in self.failing_tables,
        )


class BaseAnalyticsTrustModelTests(unittest.TestCase):
    def setUp(self):
        self._orig_datetime = analytics.datetime
        self._orig_supa = analytics.supa
        self._orig_supabase_client = analytics.supabase_client
        self._orig_source_health = analytics.source_health
        self._orig_verify_auth = analytics._verify_auth
        self._orig_maybe_escalate = analytics._maybe_escalate_to_paperclip
        analytics._maybe_escalate_to_paperclip = lambda **kwargs: None
        analytics._verify_auth = lambda authorization: "user-123"
        analytics.supabase_client = None

    def tearDown(self):
        analytics.datetime = self._orig_datetime
        analytics.supa = self._orig_supa
        analytics.supabase_client = self._orig_supabase_client
        analytics.source_health = self._orig_source_health
        analytics._verify_auth = self._orig_verify_auth
        analytics._maybe_escalate_to_paperclip = self._orig_maybe_escalate


def _run(coro):
    return asyncio.run(coro)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 4, 15, 18, 0, 0, tzinfo=tz or timezone.utc)


class AnalyticsTrustModelTests(BaseAnalyticsTrustModelTests):
    def test_summary_includes_mixed_scope_freshness_and_preserves_legacy_trust_fields(self):
        now = datetime(2026, 4, 15, 18, 0, 0, tzinfo=timezone.utc)
        analytics.datetime = _FixedDatetime

        async def _fake_source_health(authorization=None):
            return {
                "sources": [{"source_site": "govdeals", "last_webhook_at": now.isoformat()}],
                "generated_at": now.isoformat(),
            }

        analytics.source_health = _fake_source_health
        analytics.supa = _FakeSupabase({
            "opportunities": {"data": [
                {"created_at": now.isoformat(), "dos_score": 88, "source_site": "govdeals", "state": "CA"}
            ]},
            "dealer_sales": {"data": [], "count": 0},
            "alert_log": {"data": [], "count": 0},
        })

        summary = _run(analytics.analytics_summary("Bearer token"))

        self.assertEqual(summary["freshness"]["pipeline"]["status"], "fresh")
        self.assertEqual(summary["freshness"]["source_health"]["status"], "fresh")
        self.assertEqual(summary["freshness"]["execution"]["status"], "empty")
        self.assertEqual(summary["freshness"]["outcomes"]["status"], "empty")
        self.assertIn("summary_refreshed_at", summary["trust"])
        self.assertIn("degraded_sections", summary["trust"])
        self.assertEqual(summary["trust"]["status"], "degraded")
        self.assertEqual(summary["trust"]["rule_ids"], ["fresh_source_health_with_stale_execution_or_outcomes"])
        self.assertIn("System and source signals are current while execution/outcomes freshness is stale or empty", summary["trust"]["notes"])

    def test_source_health_freshness_uses_generated_at_when_source_timestamps_are_missing(self):
        now = datetime(2026, 4, 15, 18, 0, 0, tzinfo=timezone.utc)
        analytics.datetime = _FixedDatetime

        async def _fake_source_health(authorization=None):
            return {
                "generated_at": now.isoformat(),
                "sources": [
                    {"source_site": "govdeals", "health": "green"},
                    {"source_site": "publicsurplus", "health": "yellow"},
                ],
            }

        analytics.source_health = _fake_source_health
        analytics.supa = _FakeSupabase({
            "opportunities": {"data": [
                {"created_at": now.isoformat(), "dos_score": 88, "source_site": "govdeals", "state": "CA"}
            ]},
            "dealer_sales": {"data": [], "count": 0},
            "alert_log": {"data": [], "count": 0},
        })

        summary = _run(analytics.analytics_summary("Bearer token"))

        self.assertEqual(summary["freshness"]["source_health"]["updated_at"], now.isoformat())
        self.assertEqual(summary["freshness"]["source_health"]["age_seconds"], 0)
        self.assertEqual(summary["freshness"]["source_health"]["status"], "fresh")

    def test_recent_trust_events_include_freshness_context(self):
        analytics.supabase_client = _FakeSupabase({
            "system_logs": {
                "data": [
                    {
                        "id": "evt-1",
                        "level": "warning",
                        "message": "Analytics trust event: analytics_summary_rule_violation",
                        "context": {
                            "event": "analytics_summary_rule_violation",
                            "trustSeverity": "medium",
                            "trustRuleIds": ["fresh_source_health_with_stale_execution_or_outcomes"],
                            "trustNotes": ["Analytics trust is mixed"],
                            "degradedSections": ["trust", "execution", "outcomes"],
                            "completenessScore": 0.5,
                            "summaryRefreshedAt": "2026-04-15T18:00:00+00:00",
                            "freshnessAge": 3600,
                            "freshness": {
                                "pipeline": {"updated_at": "2026-04-15T17:00:00+00:00", "age_seconds": 3600, "status": "fresh"},
                                "source_health": {"updated_at": "2026-04-15T17:00:00+00:00", "age_seconds": 3600, "status": "fresh"},
                                "execution": {"updated_at": None, "age_seconds": None, "status": "empty"},
                                "outcomes": {"updated_at": None, "age_seconds": None, "status": "empty"},
                            },
                            "paperclip": {"status": "skipped_missing_env"},
                        },
                        "timestamp": "2026-04-15T18:01:00+00:00",
                        "created_at": "2026-04-15T18:01:00+00:00",
                    }
                ],
                "count": 1,
            }
        })

        payload = _run(analytics.recent_trust_events(limit=25, authorization="Bearer token"))

        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["freshness"]["execution"]["status"], "empty")
        self.assertEqual(payload["events"][0]["freshness"]["pipeline"]["status"], "fresh")
        self.assertEqual(payload["events"][0]["severity"], "medium")

    def test_no_database_path_keeps_execution_and_outcomes_freshness_empty(self):
        analytics.supa = None

        summary = _run(analytics.analytics_summary("Bearer token"))

        self.assertEqual(summary["freshness"]["execution"]["status"], "empty")
        self.assertEqual(summary["freshness"]["outcomes"]["status"], "empty")
        self.assertEqual(summary["trust"]["status"], "degraded")

    def test_query_failures_do_not_override_empty_execution_and_outcomes_freshness(self):
        now = datetime(2026, 4, 15, 18, 0, 0, tzinfo=timezone.utc)
        analytics.datetime = _FixedDatetime

        async def _fake_source_health(authorization=None):
            return {
                "sources": [{"source_site": "govdeals", "last_webhook_at": now.isoformat()}],
                "generated_at": now.isoformat(),
            }

        analytics.source_health = _fake_source_health
        analytics.supa = _FakeSupabaseWithFailures(
            {
                "opportunities": {
                    "data": [
                        {"created_at": now.isoformat(), "dos_score": 88, "source_site": "govdeals", "state": "CA"}
                    ],
                    "count": 1,
                },
                "dealer_sales": {"data": [], "count": 0},
                "alert_log": {"data": [], "count": 0},
            },
            failing_tables={"dealer_sales"},
        )

        summary = _run(analytics.analytics_summary("Bearer token"))

        self.assertEqual(summary["execution"]["status"], "empty")
        self.assertEqual(summary["freshness"]["execution"]["status"], "empty")
        self.assertEqual(summary["outcomes"]["status"], "empty")
        self.assertEqual(summary["freshness"]["outcomes"]["status"], "empty")


if __name__ == "__main__":
    unittest.main()
