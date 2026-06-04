import json
from pathlib import Path
import unittest


class ApifyDeploymentManifestTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_deployment_manifest_does_not_store_webhook_secret(self):
        manifest_path = self.repo_root / "apify" / "deployment.json"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertNotIn("webhookSecret", payload)

    def test_govdeals_sold_actor_is_manifested_and_deployable(self):
        manifest_path = self.repo_root / "apify" / "deployment.json"
        workflow_path = self.repo_root / ".github" / "workflows" / "apify-deploy.yml"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        workflow = workflow_path.read_text(encoding="utf-8")

        actor = payload["actors"].get("ds-govdeals-sold")
        self.assertIsNotNone(actor)
        self.assertEqual(actor["id"], "Ui7FeFY4mIVPnU1fH")
        self.assertEqual(actor["status"], "enabled")
        self.assertIn('"ds-govdeals-sold": "Ui7FeFY4mIVPnU1fH"', workflow)

    def test_manual_apify_runner_supports_govdeals_sold_date_diagnostics(self):
        workflow_path = self.repo_root / ".github" / "workflows" / "run-apify-actor.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn('"ds-govdeals-sold": "Ui7FeFY4mIVPnU1fH"', workflow)
        self.assertIn("GOVDEALS_SOLD_MAX_ITEMS", workflow)
        self.assertIn("${{ inputs.govdeals_sold_max_items }}", workflow)
        self.assertIn('"sold_date_diagnostics"', workflow)
        self.assertIn('"auction_end_time"', workflow)
        self.assertIn('"auction_end_date"', workflow)


if __name__ == "__main__":
    unittest.main()
