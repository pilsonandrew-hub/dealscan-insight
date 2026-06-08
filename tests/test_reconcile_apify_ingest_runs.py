import json
import io
import ssl
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib import error as urllib_error
from contextlib import redirect_stdout
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import reconcile_apify_ingest_runs as reconcile


class ReconcileApifyIngestRunsTests(unittest.TestCase):
    def setUp(self):
        reconcile._CURL_SSL_FALLBACK_NOTIFIED = False

    def test_load_actor_registry_defaults_to_enabled_sources_only(self):
        manifest = json.dumps(
            {
                "actors": {
                    "ds-active": {"id": "actor-active", "status": "enabled"},
                    "ds-disabled": {"id": "actor-disabled", "status": "DISABLED"},
                    "ds-retired": {"id": "actor-retired", "status": "RETIRED"},
                }
            }
        )
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write(manifest)
            manifest_path = Path(fh.name)
        try:
            with patch.object(reconcile, "DEPLOYMENT_PATH", manifest_path):
                registry = reconcile.load_actor_registry([])
        finally:
            manifest_path.unlink(missing_ok=True)

        self.assertEqual(registry, {"ds-active": "actor-active"})

    def test_load_actor_registry_explicit_filter_can_select_disabled_source(self):
        manifest = json.dumps(
            {
                "actors": {
                    "ds-active": {"id": "actor-active", "status": "enabled"},
                    "ds-disabled": {"id": "actor-disabled", "status": "DISABLED"},
                }
            }
        )
        with tempfile.NamedTemporaryFile("w", delete=False) as fh:
            fh.write(manifest)
            manifest_path = Path(fh.name)
        try:
            with patch.object(reconcile, "DEPLOYMENT_PATH", manifest_path):
                registry = reconcile.load_actor_registry(["ds-disabled"])
        finally:
            manifest_path.unlink(missing_ok=True)

        self.assertEqual(registry, {"ds-disabled": "actor-disabled"})

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

    def test_classify_run_allows_skipped_score_rows_when_ledger_accounts_for_them(self):
        issues = reconcile.classify_run(
            run_id="run-skip-score",
            apify_run={"run_id": "run-skip-score", "status": "SUCCEEDED", "item_count": 2},
            webhook={"latest_status": "processed"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"skipped_score": 2}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_treats_source_quality_proof_skip_as_accounted(self):
        issues = reconcile.classify_run(
            run_id="run-proof-skip",
            apify_run={"run_id": "run-proof-skip", "status": "SUCCEEDED", "item_count": 2},
            webhook={"latest_status": "processed"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"skipped_proof": 1, "skipped_ceiling": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_flags_partial_db_save_ledger_before_generic_no_landing(self):
        issues = reconcile.classify_run(
            run_id="run-partial-ledger",
            apify_run={"run_id": "run-partial-ledger", "status": "SUCCEEDED", "item_count": 2},
            webhook={"latest_status": "processed"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"skipped_ceiling": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertIn("partial_db_save_ledger", issues)
        self.assertIn("no_db_landing", issues)
        likely_cause = reconcile.infer_likely_cause(
            apify_run={"run_id": "run-partial-ledger", "status": "SUCCEEDED", "item_count": 2},
            webhook={"latest_status": "processed"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"skipped_ceiling": 1}}}},
            issues=issues,
        )
        self.assertIn("partial_db_save_ledger", likely_cause)
        self.assertIn("not every source item", likely_cause)

    def test_classify_run_treats_vin_dedup_as_existing_success(self):
        issues = reconcile.classify_run(
            run_id="run-vin-dedup",
            apify_run={"run_id": "run-vin-dedup", "status": "SUCCEEDED", "item_count": 2},
            webhook={"latest_status": "degraded", "latest_error": "failed:1"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"vin_dedup_skipped": 2}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_does_not_flag_pending_webhook_when_db_landing_is_proven(self):
        issues = reconcile.classify_run(
            run_id="run-pending-but-landed",
            apify_run={"run_id": "run-pending-but-landed", "status": "SUCCEEDED", "item_count": 1},
            webhook={
                "latest_status": "pending",
                "last_received_at": "2026-03-17T00:00:00+00:00",
            },
            opportunities={"opportunity_rows": 1},
            delivery={"channels": {"db_save": {"statuses": {"saved_supabase": 1}}}},
            now_utc=datetime(2026, 3, 17, 2, 0, tzinfo=timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_treats_sold_comp_candidate_staging_as_db_landing(self):
        issues = reconcile.classify_run(
            run_id="run-candidate-staged",
            apify_run={"run_id": "run-candidate-staged", "status": "SUCCEEDED", "item_count": 3},
            webhook={"latest_status": "processed"},
            opportunities={"opportunity_rows": 0},
            delivery={"channels": {"db_save": {"statuses": {"candidate_staged": 3}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, [])

    def test_classify_run_flags_save_exception_as_db_save_failure(self):
        issues = reconcile.classify_run(
            run_id="run-save-exception",
            apify_run={"run_id": "run-save-exception", "status": "SUCCEEDED", "item_count": 1},
            webhook={"latest_status": "error", "latest_error": "failed:1"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"save_exception": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertIn("webhook_error", issues)
        self.assertIn("db_save_failures", issues)
        self.assertIn("no_db_landing", issues)

    def test_classify_run_flags_legacy_failed_status_as_db_save_failure(self):
        issues = reconcile.classify_run(
            run_id="run-legacy-failed",
            apify_run={"run_id": "run-legacy-failed", "status": "SUCCEEDED", "item_count": 1},
            webhook={"latest_status": "error", "latest_error": "failed:1"},
            opportunities=None,
            delivery={"channels": {"db_save": {"statuses": {"failed": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertIn("webhook_error", issues)
        self.assertIn("db_save_failures", issues)
        self.assertIn("no_db_landing", issues)

    def test_classify_run_flags_sonar_mirror_failures(self):
        issues = reconcile.classify_run(
            run_id="run-sonar-fail",
            apify_run={"run_id": "run-sonar-fail", "status": "SUCCEEDED", "item_count": 3},
            webhook={"latest_status": "error", "latest_error": "sonar_write_failures:2"},
            opportunities={"opportunity_rows": 3},
            delivery={
                "channels": {
                    "db_save": {"statuses": {"saved_supabase": 3}},
                    "sonar_mirror": {"statuses": {"saved_sonar": 1, "sonar_error": 2}},
                }
            },
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertIn("webhook_error", issues)
        self.assertIn("sonar_mirror_failures", issues)
        self.assertNotIn("db_save_failures", issues)

    def test_infer_likely_cause_flags_sonar_mirror_failures(self):
        likely_cause = reconcile.infer_likely_cause(
            apify_run={"run_id": "run-sonar-fail", "status": "SUCCEEDED"},
            webhook={"latest_status": "error"},
            opportunities={"opportunity_rows": 3},
            delivery={"channels": {"sonar_mirror": {"statuses": {"sonar_error": 2}}}},
            issues=["sonar_mirror_failures"],
        )

        self.assertIn("sonar_mirror_write_failures", likely_cause)
        self.assertIn("sonar_mirror", likely_cause)

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

    def test_classify_run_labels_direct_pg_unavailable_rest_fallback_separately(self):
        issues = reconcile.classify_run(
            run_id="run-rest-fallback",
            apify_run={"run_id": "run-rest-fallback", "status": "SUCCEEDED", "item_count": 1},
            webhook={
                "latest_status": "processed",
                "latest_error": "funnel=items:1; audit_fallbacks=webhook_log_claim_direct_pg_unavailable",
            },
            opportunities={"opportunity_rows": 1},
            delivery={"channels": {"db_save": {"statuses": {"saved_supabase": 1}}}},
            now_utc=datetime.now(timezone.utc),
            pending_grace_minutes=30,
        )

        self.assertEqual(issues, ["direct_pg_claim_rest_fallback"])
        self.assertEqual(reconcile.classify_issue_scope(issues), "historical_artifact")
        likely_cause = reconcile.infer_likely_cause(
            apify_run={"run_id": "run-rest-fallback", "status": "SUCCEEDED"},
            webhook={"latest_status": "processed"},
            opportunities={"opportunity_rows": 1},
            delivery={"channels": {"db_save": {"statuses": {"saved_supabase": 1}}}},
            issues=issues,
        )
        self.assertIn("direct_pg_claim_rest_fallback", likely_cause)
        self.assertIn("500 guard worked", likely_cause)

    def test_build_reports_separates_historical_artifacts_from_current_landing_issues(self):
        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "run-rest-fallback",
                    "actor_name": "ds-govdeals",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "started_at": datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
                },
                {
                    "run_id": "run-missing-webhook",
                    "actor_name": "ds-publicsurplus",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "started_at": datetime(2026, 3, 17, 0, 1, tzinfo=timezone.utc),
                },
            ],
            webhook_rows={
                "run-rest-fallback": {
                    "latest_status": "processed",
                    "latest_error": "audit_fallbacks=webhook_log_claim_direct_pg_unavailable",
                }
            },
            opportunity_rows={"run-rest-fallback": {"opportunity_rows": 1}},
            delivery_rows={
                "run-rest-fallback": {
                    "channels": {"db_save": {"statuses": {"saved_supabase": 1}}}
                }
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertEqual(by_run_id["run-rest-fallback"]["issue_scope"], "historical_artifact")
        self.assertEqual(by_run_id["run-missing-webhook"]["issue_scope"], "current_landing_issue")
        summary = reconcile.summarize(reports)
        self.assertEqual(summary["runs_with_historical_artifacts"], 1)
        self.assertEqual(summary["runs_with_current_landing_issues"], 1)

    def test_build_reports_reclassifies_superseded_source_quality_proof_landing_gap(self):
        older_started = datetime(2026, 6, 4, 19, 0, tzinfo=timezone.utc)
        newer_started = datetime(2026, 6, 4, 23, 44, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "old-proof-run",
                    "actor_name": "ds-govplanet",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "source_quality_proof_count": 1,
                    "started_at": older_started,
                },
                {
                    "run_id": "new-proof-run",
                    "actor_name": "ds-govplanet",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "source_quality_proof_count": 1,
                    "started_at": newer_started,
                },
            ],
            webhook_rows={
                "old-proof-run": {"latest_status": "ignored_replay", "webhook_entries": 2, "max_item_count": 1},
                "new-proof-run": {"latest_status": "ignored_replay", "webhook_entries": 2, "max_item_count": 1},
            },
            opportunity_rows={},
            delivery_rows={
                "new-proof-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"skipped_proof": 1},
                            "total_rows": 1,
                            "total_attempts": 1,
                        }
                    }
                }
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertEqual(
            by_run_id["old-proof-run"]["issues"],
            ["superseded_source_quality_proof_pre_ledger"],
        )
        self.assertEqual(by_run_id["old-proof-run"]["issue_scope"], "historical_artifact")
        self.assertEqual(by_run_id["new-proof-run"]["issues"], [])
        summary = reconcile.summarize(reports)
        self.assertEqual(summary["runs_with_current_landing_issues"], 0)
        self.assertEqual(summary["runs_with_historical_artifacts"], 1)

    def test_build_reports_reclassifies_mixed_dataset_when_only_pre_ledger_proof_row_is_missing(self):
        older_started = datetime(2026, 6, 4, 19, 0, tzinfo=timezone.utc)
        clean_proof_started = datetime(2026, 6, 4, 23, 35, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "old-mixed-run",
                    "actor_name": "ds-gsaauctions",
                    "status": "SUCCEEDED",
                    "item_count": 4,
                    "source_quality_proof_count": 1,
                    "started_at": older_started,
                },
                {
                    "run_id": "clean-proof-run",
                    "actor_name": "ds-proxibid",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "source_quality_proof_count": 1,
                    "started_at": clean_proof_started,
                },
            ],
            webhook_rows={
                "old-mixed-run": {"latest_status": "ignored_replay", "webhook_entries": 2, "max_item_count": 4},
                "clean-proof-run": {"latest_status": "ignored_replay", "webhook_entries": 2, "max_item_count": 1},
            },
            opportunity_rows={},
            delivery_rows={
                "old-mixed-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"skipped_gate": 2, "skipped_margin": 1},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
                "clean-proof-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"skipped_proof": 1},
                            "total_rows": 1,
                            "total_attempts": 1,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertEqual(
            by_run_id["old-mixed-run"]["issues"],
            ["superseded_source_quality_proof_pre_ledger"],
        )
        self.assertEqual(by_run_id["old-mixed-run"]["issue_scope"], "historical_artifact")
        summary = reconcile.summarize(reports)
        self.assertEqual(summary["runs_with_current_landing_issues"], 0)
        self.assertEqual(summary["runs_with_historical_artifacts"], 1)

    def test_build_reports_does_not_reclassify_post_cutover_missing_proof_rows(self):
        clean_proof_started = datetime(2026, 6, 4, 23, 35, tzinfo=timezone.utc)
        later_started = datetime(2026, 6, 4, 23, 45, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "clean-proof-run",
                    "actor_name": "ds-proxibid",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "source_quality_proof_count": 1,
                    "started_at": clean_proof_started,
                },
                {
                    "run_id": "later-missing-proof-run",
                    "actor_name": "ds-gsaauctions",
                    "status": "SUCCEEDED",
                    "item_count": 4,
                    "source_quality_proof_count": 1,
                    "started_at": later_started,
                },
            ],
            webhook_rows={
                "clean-proof-run": {"latest_status": "ignored_replay", "webhook_entries": 2, "max_item_count": 1},
                "later-missing-proof-run": {"latest_status": "ignored_replay", "webhook_entries": 2, "max_item_count": 4},
            },
            opportunity_rows={},
            delivery_rows={
                "clean-proof-run": {
                    "channels": {"db_save": {"statuses": {"skipped_proof": 1}, "total_rows": 1, "total_attempts": 1}}
                },
                "later-missing-proof-run": {
                    "channels": {"db_save": {"statuses": {"skipped_gate": 3}, "total_rows": 3, "total_attempts": 3}}
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertIn("partial_db_save_ledger", by_run_id["later-missing-proof-run"]["issues"])
        self.assertEqual(by_run_id["later-missing-proof-run"]["issue_scope"], "current_landing_issue")

    def test_build_reports_counts_candidate_already_reviewed_as_landed_comp_candidate(self):
        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "reviewed-candidate-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 3,
                    "started_at": datetime(2026, 6, 4, 15, 20, tzinfo=timezone.utc),
                },
            ],
            webhook_rows={
                "reviewed-candidate-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 3,
                }
            },
            opportunity_rows={},
            delivery_rows={
                "reviewed-candidate-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"candidate_already_reviewed": 3},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        self.assertEqual(reports[0]["issues"], [])
        self.assertEqual(reports[0]["issue_scope"], "clean")

    def test_build_reports_reclassifies_pre_ledger_reviewed_candidate_with_missing_proof_row(self):
        older_started = datetime(2026, 6, 4, 15, 20, tzinfo=timezone.utc)
        clean_proof_started = datetime(2026, 6, 4, 23, 35, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "old-reviewed-candidate-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 4,
                    "source_quality_proof_count": 1,
                    "started_at": older_started,
                },
                {
                    "run_id": "clean-proof-run",
                    "actor_name": "ds-proxibid",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "source_quality_proof_count": 1,
                    "started_at": clean_proof_started,
                },
            ],
            webhook_rows={
                "old-reviewed-candidate-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 4,
                    "latest_error": "audit_fallbacks=webhook_log_claim_direct_pg",
                },
                "clean-proof-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 1,
                },
            },
            opportunity_rows={},
            delivery_rows={
                "old-reviewed-candidate-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"candidate_already_reviewed": 3},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
                "clean-proof-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"skipped_proof": 1},
                            "total_rows": 1,
                            "total_attempts": 1,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertEqual(
            by_run_id["old-reviewed-candidate-run"]["issues"],
            ["superseded_source_quality_proof_pre_ledger"],
        )
        self.assertEqual(by_run_id["old-reviewed-candidate-run"]["issue_scope"], "historical_artifact")

    def test_build_reports_reclassifies_superseded_sold_comp_candidate_staging_failures(self):
        failed_started = datetime(2026, 6, 4, 13, 40, tzinfo=timezone.utc)
        clean_started = datetime(2026, 6, 4, 14, 22, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "old-contract-failure-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 4,
                    "started_at": failed_started,
                },
                {
                    "run_id": "clean-candidate-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 3,
                    "started_at": clean_started,
                },
            ],
            webhook_rows={
                "old-contract-failure-run": {
                    "latest_status": "error",
                    "webhook_entries": 1,
                    "max_item_count": 4,
                    "latest_error": "candidate_staging_failed chk_sold_comp_price_basis audit_fallbacks=webhook_log_claim_direct_pg",
                },
                "clean-candidate-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 3,
                },
            },
            opportunity_rows={},
            delivery_rows={
                "old-contract-failure-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"failed": 4},
                            "total_rows": 4,
                            "total_attempts": 4,
                        }
                    }
                },
                "clean-candidate-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"candidate_staged": 3},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertEqual(
            by_run_id["old-contract-failure-run"]["issues"],
            ["superseded_sold_comp_candidate_pre_ledger"],
        )
        self.assertEqual(by_run_id["old-contract-failure-run"]["issue_scope"], "historical_artifact")
        self.assertEqual(by_run_id["clean-candidate-run"]["issues"], [])

    def test_build_reports_reclassifies_superseded_sold_comp_missing_ledger_run(self):
        missing_started = datetime(2026, 6, 4, 14, 0, tzinfo=timezone.utc)
        clean_started = datetime(2026, 6, 4, 14, 22, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "old-missing-ledger-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "started_at": missing_started,
                },
                {
                    "run_id": "clean-candidate-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 3,
                    "started_at": clean_started,
                },
            ],
            webhook_rows={
                "old-missing-ledger-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 1,
                    "latest_error": "audit_fallbacks=webhook_log_claim_direct_pg",
                },
                "clean-candidate-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 3,
                },
            },
            opportunity_rows={},
            delivery_rows={
                "clean-candidate-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"candidate_staged": 3},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertEqual(
            by_run_id["old-missing-ledger-run"]["issues"],
            ["superseded_sold_comp_candidate_pre_ledger"],
        )
        self.assertEqual(by_run_id["old-missing-ledger-run"]["issue_scope"], "historical_artifact")

    def test_build_reports_keeps_post_cutover_sold_comp_candidate_staging_failures_current(self):
        clean_started = datetime(2026, 6, 4, 14, 22, tzinfo=timezone.utc)
        later_failed_started = datetime(2026, 6, 4, 15, 0, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "clean-candidate-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 3,
                    "started_at": clean_started,
                },
                {
                    "run_id": "later-contract-failure-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "started_at": later_failed_started,
                },
            ],
            webhook_rows={
                "clean-candidate-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 3,
                },
                "later-contract-failure-run": {
                    "latest_status": "error",
                    "webhook_entries": 1,
                    "max_item_count": 1,
                    "latest_error": "candidate_staging_failed",
                },
            },
            opportunity_rows={},
            delivery_rows={
                "clean-candidate-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"candidate_staged": 3},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
                "later-contract-failure-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"failed": 1},
                            "total_rows": 1,
                            "total_attempts": 1,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertIn("webhook_error", by_run_id["later-contract-failure-run"]["issues"])
        self.assertEqual(by_run_id["later-contract-failure-run"]["issue_scope"], "current_landing_issue")

    def test_build_reports_keeps_post_cutover_sold_comp_missing_ledger_current(self):
        clean_started = datetime(2026, 6, 4, 14, 22, tzinfo=timezone.utc)
        later_missing_started = datetime(2026, 6, 4, 15, 0, tzinfo=timezone.utc)

        reports = reconcile.build_reports(
            apify_runs=[
                {
                    "run_id": "clean-candidate-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 3,
                    "started_at": clean_started,
                },
                {
                    "run_id": "later-missing-ledger-run",
                    "actor_name": "ds-govdeals-sold",
                    "status": "SUCCEEDED",
                    "item_count": 1,
                    "started_at": later_missing_started,
                },
            ],
            webhook_rows={
                "clean-candidate-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 3,
                },
                "later-missing-ledger-run": {
                    "latest_status": "processed",
                    "webhook_entries": 1,
                    "max_item_count": 1,
                    "latest_error": "audit_fallbacks=webhook_log_claim_direct_pg",
                },
            },
            opportunity_rows={},
            delivery_rows={
                "clean-candidate-run": {
                    "channels": {
                        "db_save": {
                            "statuses": {"candidate_staged": 3},
                            "total_rows": 3,
                            "total_attempts": 3,
                        }
                    }
                },
            },
            pending_grace_minutes=30,
        )

        by_run_id = {report["run_id"]: report for report in reports}
        self.assertIn("missing_delivery_log", by_run_id["later-missing-ledger-run"]["issues"])
        self.assertIn("missing_db_save_ledger", by_run_id["later-missing-ledger-run"]["issues"])
        self.assertEqual(by_run_id["later-missing-ledger-run"]["issue_scope"], "current_landing_issue")

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

    def test_fetch_delivery_rows_via_rest_carries_sanitized_skip_samples(self):
        with patch.object(
            reconcile,
            "_fetch_postgrest_rows",
            return_value=[
                {
                    "run_id": "run-1",
                    "channel": "db_save",
                    "status": "skipped_ceiling",
                    "listing_id": "listing-1",
                    "listing_url": "https://example.com/asset/1",
                    "error_message": "bid_ceiling_exceeded | bid=$35,000 max_bid=$22,000 mmr=$30,000 headroom=$-13,000 tier=core",
                    "attempt_count": 1,
                    "created_at": "2026-03-17T01:00:00+00:00",
                    "updated_at": "2026-03-17T01:00:00+00:00",
                },
                {
                    "run_id": "run-1",
                    "channel": "db_save",
                    "status": "skipped_gate",
                    "listing_id": "listing-2",
                    "listing_url": "https://example.com/asset/2",
                    "error_message": "age_or_mileage_exceeded",
                    "attempt_count": 1,
                    "created_at": "2026-03-17T01:01:00+00:00",
                    "updated_at": "2026-03-17T01:01:00+00:00",
                },
            ],
        ):
            rows = reconcile.fetch_delivery_rows_via_rest(
                base_url="https://example.supabase.co/rest/v1",
                service_role_key="service-key",
                start=datetime(2026, 3, 17, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 3, 17, 2, 0, tzinfo=timezone.utc),
            )

        db_save = rows["run-1"]["channels"]["db_save"]
        self.assertEqual(db_save["statuses"], {"skipped_ceiling": 1, "skipped_gate": 1})
        self.assertEqual(len(db_save["samples"]["skipped_ceiling"]), 1)
        self.assertEqual(
            db_save["samples"]["skipped_ceiling"][0],
            {
                "listing_id": "listing-1",
                "listing_url": "https://example.com/asset/1",
                "error_message": "bid_ceiling_exceeded | bid=$35,000 max_bid=$22,000 mmr=$30,000 headroom=$-13,000 tier=core",
            },
        )

    def test_print_reports_includes_db_save_skip_samples(self):
        report = {
            "run_id": "run-1",
            "apify": {
                "actor_name": "ds-govdeals",
                "status": "SUCCEEDED",
                "dataset_id": "dataset-1",
                "item_count": 1,
            },
            "webhook": {"latest_status": "processed", "webhook_entries": 1},
            "opportunities": {},
            "delivery": {
                "channels": {
                    "db_save": {
                        "statuses": {"skipped_ceiling": 1},
                        "total_rows": 1,
                        "total_attempts": 1,
                        "samples": {
                            "skipped_ceiling": [
                                {
                                    "listing_id": "listing-1",
                                    "listing_url": "https://example.com/asset/1",
                                    "error_message": "bid_ceiling_exceeded | bid=$35,000 max_bid=$22,000 mmr=$30,000 headroom=$-13,000 tier=core",
                                }
                            ]
                        },
                    }
                }
            },
            "issues": [],
            "issue_scope": "clean",
            "likely_cause": None,
        }

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            reconcile.print_reports([report], summary_only=False)

        output = buffer.getvalue()
        self.assertIn("db_save_samples:", output)
        self.assertIn("status=skipped_ceiling", output)
        self.assertIn("listing_id=listing-1", output)
        self.assertIn("bid_ceiling_exceeded", output)

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

    def test_main_fail_on_issues_allows_historical_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_path = Path(tmpdir) / "runs.json"
            runs_path.write_text("[]", encoding="utf-8")
            with patch.object(reconcile, "load_actor_registry", return_value={"ds-equipmentfacts": "actor-1"}), patch.object(
                reconcile,
                "load_reconciliation_rows",
                return_value=({}, {}, {}, "rest:env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY"),
            ), patch.object(
                reconcile,
                "resolve_database_url",
                return_value=(None, None),
            ), patch.object(
                reconcile,
                "build_reports",
                return_value=[
                    {
                        "run_id": "historical-run",
                        "issues": ["superseded_source_quality_proof_pre_ledger"],
                        "issue_scope": "historical_artifact",
                    }
                ],
            ), patch.dict(
                reconcile.os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
                },
                clear=False,
            ), redirect_stdout(io.StringIO()):
                exit_code = reconcile.main(
                    [
                        "--runs-json",
                        str(runs_path),
                        "--actors",
                        "ds-equipmentfacts",
                        "--fail-on-issues",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 0)

    def test_main_fail_on_issues_fails_current_landing_issues(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            runs_path = Path(tmpdir) / "runs.json"
            runs_path.write_text("[]", encoding="utf-8")
            with patch.object(reconcile, "load_actor_registry", return_value={"ds-govdeals": "actor-1"}), patch.object(
                reconcile,
                "load_reconciliation_rows",
                return_value=({}, {}, {}, "rest:env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY"),
            ), patch.object(
                reconcile,
                "resolve_database_url",
                return_value=(None, None),
            ), patch.object(
                reconcile,
                "build_reports",
                return_value=[
                    {
                        "run_id": "missing-webhook-run",
                        "issues": ["missing_webhook"],
                        "issue_scope": "current_landing_issue",
                    }
                ],
            ), patch.dict(
                reconcile.os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SERVICE_ROLE_KEY": "service-key",
                },
                clear=False,
            ), redirect_stdout(io.StringIO()):
                exit_code = reconcile.main(
                    [
                        "--runs-json",
                        str(runs_path),
                        "--actors",
                        "ds-govdeals",
                        "--fail-on-issues",
                        "--json",
                    ]
                )

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
