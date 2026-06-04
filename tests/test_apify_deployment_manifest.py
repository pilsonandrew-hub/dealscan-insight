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

    def test_manual_apify_runner_fails_govdeals_sold_future_date_output(self):
        workflow_path = self.repo_root / ".github" / "workflows" / "run-apify-actor.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn('"future_sold_rows"', workflow)
        self.assertIn("GovDeals sold actor emitted future-dated rows", workflow)
        self.assertIn('raise SystemExit("GovDeals sold actor emitted future-dated rows")', workflow)

    def test_govdeals_sold_actor_uses_safe_json_parse_and_fresh_correlation_ids(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("safeJsonParse", source)
        self.assertIn("randomUUID", source)
        self.assertIn("headersForReplayPage", source)
        self.assertNotIn("json: nodeResp.ok ? JSON.parse(responseText) : null", source)
        self.assertNotIn("'x-api-correlation-id',", source)

    def test_govdeals_sold_actor_targets_approved_comp_models(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        target_scope_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "target_scope.js"
        target_scope_test_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "test" / "target-scope.node.mjs"
        source = source_path.read_text(encoding="utf-8")
        target_scope = target_scope_path.read_text(encoding="utf-8")

        self.assertIn("DEFAULT_TARGET_TERMS", target_scope)
        self.assertIn("targetTerms", source)
        self.assertIn("matchesTargetTerms", source)
        self.assertTrue(target_scope_test_path.exists())
        for target in ["f-150", "f150", "f-250", "silverado 1500", "ram 1500"]:
            self.assertIn(target, target_scope.lower())

    def test_govdeals_sold_actor_actively_searches_target_terms(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        workflow_path = self.repo_root / ".github" / "workflows" / "run-apify-actor.yml"
        source = source_path.read_text(encoding="utf-8")
        workflow = workflow_path.read_text(encoding="utf-8")

        self.assertIn("searchQuery", source)
        self.assertIn("targetSearchQueries", source)
        self.assertIn("searchText", source)
        self.assertIn("buildCompletedSearchPayload", source)
        self.assertIn("remainingPageBudget", source)
        self.assertIn("pagesForQuery", source)
        self.assertIn("completedSaleRejectionReason", source)
        self.assertIn("rows_excluded_not_completed_sale", source)
        self.assertIn("query_diagnostics", source)
        self.assertIn("out_of_scope_examples", source)
        self.assertIn('"query_diagnostics"', workflow)
        self.assertIn('"out_of_scope_examples"', workflow)
        self.assertIn('actor_input["searchQuery"] = search_query', workflow)


if __name__ == "__main__":
    unittest.main()
