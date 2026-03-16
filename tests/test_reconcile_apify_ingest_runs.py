import ssl
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()
