import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import capture_webhook_secret_proof as proof


class CaptureWebhookSecretProofTests(unittest.TestCase):
    def test_build_artifact_captures_live_checks_without_raw_secrets(self):
        payload = {
            "createdAt": "2026-03-16T12:00:00+00:00",
            "resource": {"id": "run-123", "defaultDatasetId": "dataset-123"},
        }
        runtime_env = {
            "APIFY_WEBHOOK_SECRET": "current-secret-value-1234567890",
            "APIFY_WEBHOOK_SECRET_RETIRED": "retired-secret-value-1234567890",
            "APIFY_WEBHOOK_SECRET_PREVIOUS": "",
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            payload_path = Path(tmpdir) / "payload.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")

            side_effects = [
                {
                    "observed_at": "2026-03-16T12:01:00+00:00",
                    "http_status": 200,
                    "response_body_excerpt": '{"status":"ok","run_id":"run-123"}',
                    "response_json": {"status": "ok", "run_id": "run-123"},
                },
                {
                    "observed_at": "2026-03-16T12:01:05+00:00",
                    "http_status": 200,
                    "response_body_excerpt": '{"status":"ok","replay_ignored":true}',
                    "response_json": {"status": "ok", "replay_ignored": True},
                },
                {
                    "observed_at": "2026-03-16T12:01:10+00:00",
                    "http_status": 401,
                    "response_body_excerpt": '{"detail":"Invalid webhook secret"}',
                    "response_json": {"detail": "Invalid webhook secret"},
                },
            ]

            with patch.object(proof, "post_webhook", side_effect=side_effects), patch.object(
                proof, "resolve_deploy_sha", return_value="abc123def456"
            ):
                artifact, failed = proof.build_artifact(
                    runtime_env,
                    endpoint="https://example.test/api/ingest/apify",
                    payload_path=str(payload_path),
                    expect_previous_absent=True,
                    retired_secret_env="APIFY_WEBHOOK_SECRET_RETIRED",
                    current_secret_env="APIFY_WEBHOOK_SECRET",
                )

        artifact_text = json.dumps(artifact, sort_keys=True)
        self.assertFalse(failed)
        self.assertEqual(artifact["checks"]["current_secret_accepted"]["status"], "passed")
        self.assertEqual(artifact["checks"]["replay_suppressed"]["status"], "passed")
        self.assertEqual(artifact["checks"]["retired_secret_rejected"]["status"], "passed")
        self.assertEqual(artifact["checks"]["previous_secret_absent"]["status"], "passed")
        self.assertEqual(artifact["request_context"]["payload"]["run_id"], "run-123")
        self.assertNotIn(runtime_env["APIFY_WEBHOOK_SECRET"], artifact_text)
        self.assertNotIn(runtime_env["APIFY_WEBHOOK_SECRET_RETIRED"], artifact_text)

    def test_build_artifact_flags_previous_secret_present_when_absence_is_expected(self):
        runtime_env = {
            "APIFY_WEBHOOK_SECRET": "current-secret-value-1234567890",
            "APIFY_WEBHOOK_SECRET_PREVIOUS": "previous-secret-value-1234567890",
        }
        with patch.object(proof, "resolve_deploy_sha", return_value="abc123def456"):
            artifact, failed = proof.build_artifact(
                runtime_env,
                endpoint=None,
                payload_path=None,
                expect_previous_absent=True,
                retired_secret_env="APIFY_WEBHOOK_SECRET_RETIRED",
                current_secret_env="APIFY_WEBHOOK_SECRET",
            )

        self.assertTrue(failed)
        self.assertEqual(artifact["checks"]["previous_secret_absent"]["status"], "failed")
        self.assertEqual(artifact["posture"]["previous"]["state"], "configured")


if __name__ == "__main__":
    unittest.main()
