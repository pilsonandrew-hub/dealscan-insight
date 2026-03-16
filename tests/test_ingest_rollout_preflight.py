import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import run_ingest_rollout_preflight as preflight


class IngestRolloutPreflightTests(unittest.TestCase):
    def test_build_runtime_env_layers_env_file_under_shell(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env.test"
            env_file.write_text(
                "DATABASE_URL=postgresql://file-user:file-pass@db.example/dealerscope\n"
                "APIFY_TOKEN=file-token\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "DATABASE_URL": "postgresql://shell-user:shell-pass@db.example/dealerscope",
                    "EXTRA_FLAG": "1",
                },
                clear=True,
            ):
                runtime_env = preflight.build_runtime_env(str(env_file))

        self.assertEqual(
            runtime_env["DATABASE_URL"],
            "postgresql://shell-user:shell-pass@db.example/dealerscope",
        )
        self.assertEqual(runtime_env["APIFY_TOKEN"], "file-token")
        self.assertEqual(runtime_env["EXTRA_FLAG"], "1")

    def test_validate_actor_manifest_requires_id_schedule_and_webhook(self):
        with patch(
            "pathlib.Path.read_text",
            return_value='{"actors":{"ds-govdeals":{"id":"actor-1","scheduleId":"schedule-1"}}}',
        ):
            errors = preflight.validate_actor_manifest(["ds-govdeals", "ds-publicsurplus"])

        self.assertIn(
            "actor ds-govdeals missing webhookId in apify/deployment.json",
            errors,
        )
        self.assertIn(
            "actor missing from apify/deployment.json: ds-publicsurplus",
            errors,
        )

    def test_inspect_ingest_schema_flags_missing_columns(self):
        rows = [
            ("public", "webhook_log", "run_id"),
            ("public", "webhook_log", "received_at"),
            ("public", "webhook_log", "processing_status"),
            ("public", "webhook_log", "error_message"),
            ("public", "webhook_log", "item_count"),
            ("public", "webhook_log", "actor_id"),
            ("public", "ingest_delivery_log", "run_id"),
            ("public", "ingest_delivery_log", "listing_id"),
            ("public", "ingest_delivery_log", "channel"),
            ("public", "ingest_delivery_log", "status"),
            ("public", "ingest_delivery_log", "attempt_count"),
            ("public", "ingest_delivery_log", "created_at"),
            ("public", "ingest_delivery_log", "updated_at"),
            ("public", "opportunities", "run_id"),
            ("public", "opportunities", "processed_at"),
            ("public", "opportunities", "step_status"),
        ]

        class _Cursor:
            def execute(self, *_args, **_kwargs):
                return None

            def fetchall(self):
                return rows

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class _Connection:
            def cursor(self):
                return _Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        with patch.object(preflight.psycopg2, "connect", return_value=_Connection()):
            errors, notes = preflight.inspect_ingest_schema("postgresql://example")

        self.assertIn(
            "missing required columns in public.webhook_log: raw_payload",
            errors,
        )
        self.assertIn(
            "missing required columns in public.opportunities: is_duplicate",
            errors,
        )
        self.assertIn("public.ingest_delivery_log: ok", notes)


if __name__ == "__main__":
    unittest.main()
