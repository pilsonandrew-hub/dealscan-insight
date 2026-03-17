import ssl
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urllib_error
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import reconcile_apify_ingest_runs as reconcile


class ReconcileApifyIngestRunsTests(unittest.TestCase):
    def setUp(self):
        reconcile._CURL_SSL_FALLBACK_NOTIFIED = False

    def test_apify_get_json_uses_curl_on_python_ssl_verify_failure(self):
        ssl_error = urllib_error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
        with patch.object(reconcile.urllib_request, "urlopen", side_effect=ssl_error), patch.object(
            reconcile.shutil, "which", return_value="/usr/bin/curl"
        ), patch.object(
            reconcile.subprocess,
            "run",
            return_value=subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout='{"data":{"items":[]}}',
                stderr="",
            ),
        ) as run_mock:
            payload = reconcile.apify_get_json("/acts/actor-123/runs", "token-123", query={"limit": 2, "desc": 1})

        self.assertEqual(payload, {"data": {"items": []}})
        command = run_mock.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/curl")
        self.assertIn("https://api.apify.com/v2/acts/actor-123/runs?limit=2&desc=1", command)
        self.assertIn("Authorization: Bearer token-123", command)

    def test_apify_get_json_reports_missing_curl_for_ssl_fallback(self):
        ssl_error = urllib_error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
        with patch.object(reconcile.urllib_request, "urlopen", side_effect=ssl_error), patch.object(
            reconcile.shutil, "which", return_value=None
        ):
            with self.assertRaises(RuntimeError) as context:
                reconcile.apify_get_json("/acts/actor-123/runs", "token-123")

        self.assertIn("curl is not available", str(context.exception))
        self.assertIn("--runs-json", str(context.exception))

    def test_classify_run_allows_db_only_run_with_clean_success_evidence(self):
        issues = reconcile.classify_run(
            run_id="run-123",
            apify_run=None,
            webhook={"latest_status": "processed"},
            opportunities={"opportunity_rows": 2},
            delivery={"channels": {"db_save": {"statuses": {"saved_supabase": 2}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_flags_db_only_run_without_success_evidence(self):
        issues = reconcile.classify_run(
            run_id="run-456",
            apify_run=None,
            webhook={"latest_status": "processed"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"direct_pg_error": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, ["db_only_run"])

    def test_build_reports_ignores_delivery_only_runs_without_attribution(self):
        reports = reconcile.build_reports(
            apify_runs=[],
            webhook_rows={},
            opportunity_rows={},
            delivery_rows={
                "run-delivery-only": {
                    "channels": {"db_save": {"statuses": {"direct_pg_error": 1}}}
                }
            },
            pending_grace_minutes=30,
        )

        self.assertEqual(reports, [])

    def test_infer_likely_cause_flags_pre_app_webhook_miss(self):
        likely_cause = reconcile.infer_likely_cause(
            apify_run={"run_id": "run-789", "status": "SUCCEEDED"},
            webhook=None,
            opportunities=None,
            delivery=None,
            issues=["missing_webhook", "missing_delivery_log", "missing_db_save_ledger", "no_db_landing"],
        )

        self.assertIn("pre_app_webhook_miss", likely_cause)
        self.assertIn("/api/ingest/apify", likely_cause)

    def test_build_reports_carries_likely_cause_for_missing_webhook(self):
        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "run-999",
                    "actor_name": "ds-publicsurplus",
                    "status": "SUCCEEDED",
                    "dataset_id": "dataset-999",
                    "item_count": 4,
                    "started_at": datetime(2026, 3, 16, 12, 0, tzinfo=timezone.utc),
                    "finished_at": datetime(2026, 3, 16, 12, 5, tzinfo=timezone.utc),
                }
            ],
            webhook_rows={},
            opportunity_rows={},
            delivery_rows={},
            pending_grace_minutes=30,
        )

        self.assertEqual(len(reports), 1)
        self.assertIn("missing_webhook", reports[0]["issues"])
        self.assertIn("pre_app_webhook_miss", reports[0]["likely_cause"])

    def test_classify_run_allows_all_items_skipped_before_save_when_ledger_accounts_for_them(self):
        issues = reconcile.classify_run(
            run_id="run-skip-only",
            apify_run={"run_id": "run-skip-only", "status": "SUCCEEDED", "item_count": 3},
            webhook={"latest_status": "processed"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"skipped_gate": 2, "skipped_margin": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_flags_audit_backfilled_when_webhook_error_marks_fallback(self):
        issues = reconcile.classify_run(
            run_id="run-audit-fallback",
            apify_run={"run_id": "run-audit-fallback", "status": "SUCCEEDED", "item_count": 1},
            webhook={
                "latest_status": "processed",
                "latest_error": "save_outcomes={'saved_direct_pg': 1}; audit_fallbacks=webhook_log_insert_direct_pg,ingest_delivery_log_direct_pg",
            },
            opportunities={"opportunity_rows": 1},
            delivery={"channels": {"db_save": {"statuses": {"saved_direct_pg": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, ["audit_backfilled"])

    def test_fetch_webhook_rows_via_rest_aggregates_rows(self):
        with patch.object(
            reconcile,
            "_fetch_postgrest_rows",
            return_value=[
                {
                    "id": "1",
                    "run_id": "run-1",
                    "received_at": "2026-03-17T01:00:00+00:00",
                    "item_count": 2,
                    "processing_status": "pending",
                    "error_message": "",
                    "actor_id": "actor-1",
                },
                {
                    "id": "2",
                    "run_id": "run-1",
                    "received_at": "2026-03-17T01:05:00+00:00",
                    "item_count": 3,
                    "processing_status": "processed",
                    "error_message": "ok",
                    "actor_id": "actor-1",
                },
                {
                    "id": "3",
                    "run_id": "run-2",
                    "received_at": "2026-03-17T01:10:00+00:00",
                    "item_count": 1,
                    "processing_status": "error",
                    "error_message": "boom",
                    "actor_id": "actor-2",
                },
            ],
        ):
            rows = reconcile.fetch_webhook_rows_via_rest(
                base_url="https://example.supabase.co/rest/v1",
                service_role_key="service-key",
                start=datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 3, 17, 2, 0, tzinfo=timezone.utc),
                actor_ids=["actor-1"],
            )

        self.assertEqual(sorted(rows), ["run-1"])
        self.assertEqual(rows["run-1"]["webhook_entries"], 2)
        self.assertEqual(rows["run-1"]["max_item_count"], 3)
        self.assertEqual(rows["run-1"]["latest_status"], "processed")
        self.assertEqual(rows["run-1"]["latest_error"], "ok")

    def test_load_reconciliation_rows_falls_back_to_rest_when_postgres_fails(self):
        with patch.object(reconcile, "connect", side_effect=RuntimeError("Tenant or user not found")), patch.object(
            reconcile,
            "fetch_webhook_rows_via_rest",
            return_value={"run-1": {"webhook_entries": 1}},
        ) as webhook_mock, patch.object(
            reconcile,
            "fetch_opportunity_rows_via_rest",
            return_value={"run-1": {"opportunity_rows": 1}},
        ) as opportunities_mock, patch.object(
            reconcile,
            "fetch_delivery_rows_via_rest",
            return_value={"run-1": {"channels": {}}},
        ) as delivery_mock:
            webhook_rows, opportunity_rows, delivery_rows, path = reconcile.load_reconciliation_rows(
                dsn="postgresql://example",
                dsn_source="env.SUPABASE_DB_URL",
                rest_base_url="https://example.supabase.co/rest/v1",
                service_role_key="service-key",
                rest_source="env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY",
                start=datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 3, 17, 2, 0, tzinfo=timezone.utc),
                actor_ids=["actor-1"],
                source_names=["govdeals"],
            )

        self.assertEqual(webhook_rows, {"run-1": {"webhook_entries": 1}})
        self.assertEqual(opportunity_rows, {"run-1": {"opportunity_rows": 1}})
        self.assertEqual(delivery_rows, {"run-1": {"channels": {}}})
        self.assertEqual(path, "rest:env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY")
        webhook_mock.assert_called_once()
        opportunities_mock.assert_called_once()
        delivery_mock.assert_called_once()

    def test_main_uses_rest_fallback_when_dsn_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_path = Path(tmpdir) / "runs.json"
            runs_path.write_text(
                '[{"id":"run-1","actId":"actor-1","status":"SUCCEEDED","createdAt":"2026-03-17T00:00:00Z","finishedAt":"2026-03-17T00:05:00Z","defaultDatasetId":"dataset-1","stats":{"itemCount":1}}]',
                encoding="utf-8",
            )
            with patch.object(reconcile, "load_actor_registry", return_value={"ds-govdeals": "actor-1"}), patch.object(
                reconcile,
                "load_reconciliation_rows",
                return_value=(
                    {"run-1": {"latest_status": "processed", "webhook_entries": 1, "last_received_at": "2026-03-17T00:05:00+00:00"}},
                    {"run-1": {"opportunity_rows": 1, "complete_rows": 1, "duplicate_rows": 0, "last_processed_at": "2026-03-17T00:06:00+00:00"}},
                    {"run-1": {"channels": {"db_save": {"statuses": {"saved_supabase": 1}, "total_rows": 1, "total_attempts": 1}}}},
                    "rest:env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY",
                ),
            ), patch.object(
                reconcile,
                "resolve_database_url",
                return_value=(None, None),
            ), patch.dict(
                reconcile.os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
                },
                clear=False,
            ):
                exit_code = reconcile.main(
                    [
                        "--runs-json",
                        str(runs_path),
                        "--actors",
                        "ds-govdeals",
                    ]
                )

        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
