import json
from pathlib import Path
import re
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
        self.assertEqual(actor["webhookId"], "OqpMiGHSE8BIgtXP2")
        self.assertEqual(actor["status"], "enabled")
        self.assertIn('"ds-govdeals-sold": "Ui7FeFY4mIVPnU1fH"', workflow)

    def test_usgovbid_actor_is_manifested_and_deployable(self):
        manifest_path = self.repo_root / "apify" / "deployment.json"
        workflow_path = self.repo_root / ".github" / "workflows" / "apify-deploy.yml"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        workflow = workflow_path.read_text(encoding="utf-8")

        actor = payload["actors"].get("ds-usgovbid")
        self.assertIsNotNone(actor)
        self.assertEqual(actor["id"], "6XO9La81aEmtsCT3g")
        self.assertEqual(actor["status"], "enabled")
        self.assertRegex(workflow, r'"ds-usgovbid":\s+"6XO9La81aEmtsCT3g"')

    def test_equipmentfacts_actor_is_manifested_deployable_and_enabled(self):
        manifest_path = self.repo_root / "apify" / "deployment.json"
        workflow_path = self.repo_root / ".github" / "workflows" / "apify-deploy.yml"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        workflow = workflow_path.read_text(encoding="utf-8")

        actor = payload["actors"].get("ds-equipmentfacts")
        self.assertIsNotNone(actor)
        self.assertEqual(actor["id"], "0XjoegYZVcPldLstl")
        self.assertEqual(actor["scheduleId"], "uJyfnyv7p5UmTzPmn")
        self.assertEqual(actor["status"], "enabled")
        self.assertEqual(actor["scheduleStatus"], "enabled_live")
        self.assertRegex(workflow, r'"ds-equipmentfacts":\s+"0XjoegYZVcPldLstl"')

    def test_bidspotter_actor_is_enabled_on_github_actions_schedule(self):
        manifest_path = self.repo_root / "apify" / "deployment.json"
        workflow_path = self.repo_root / ".github" / "workflows" / "configure-bidspotter-apify-schedule.yml"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        workflow = workflow_path.read_text(encoding="utf-8")

        actor = payload["actors"].get("ds-bidspotter")
        self.assertIsNotNone(actor)
        self.assertEqual(actor["id"], "5Eu3hfCcBBdzp6I1u")
        self.assertEqual(actor["webhookId"], "N699FBbtfzjjhHshJ")
        self.assertEqual(actor["status"], "enabled")
        self.assertEqual(actor["scheduleId"], "JFLFznTEe1kLYXM34")
        self.assertEqual(actor["schedule"], "5 11,23 * * *")
        self.assertEqual(actor["scheduleName"], "ds-bidspotter-12hr-apify-native")
        self.assertEqual(actor["scheduleStatus"], "enabled_live")
        self.assertIn("ds-bidspotter-12hr-apify-native", workflow)
        self.assertIn("FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}", workflow)

    def test_hibid_v2_actor_is_enabled_on_secret_managed_apify_schedule(self):
        manifest_path = self.repo_root / "apify" / "deployment.json"
        workflow_path = self.repo_root / ".github" / "workflows" / "configure-hibid-v2-apify-schedule.yml"
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        workflow = workflow_path.read_text(encoding="utf-8")

        actor = payload["actors"].get("ds-hibid-v2")
        self.assertIsNotNone(actor)
        self.assertEqual(actor["id"], "7s9e0eATTt1kuGGfE")
        self.assertEqual(actor["scheduleId"], "1tLdDDBUL2Kb6cBzl")
        self.assertEqual(actor["status"], "enabled")
        self.assertEqual(actor["schedule"], "0 */12 * * *")
        self.assertEqual(actor["scheduleName"], "ds-hibid-v2-every-12h")
        self.assertEqual(actor["scheduleStatus"], "enabled_live")
        self.assertIn("WEBHOOK_SECRET: ${{ secrets.APIFY_WEBHOOK_SECRET }}", workflow)
        self.assertIn('"minYear": CURRENT_YEAR - 4', workflow)
        self.assertIn('"maxMileage": 50000', workflow)
        self.assertNotIn('"webhookSecret"', workflow)
        self.assertNotIn("rDyApg2UUIMl0a8ZUz_swOqsHX7HbjN-gly3xHNwiyA", workflow)

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
        self.assertIn("DEFAULT_TARGET_TERMS", source)
        self.assertIn("DEFAULT_MAX_SEARCH_QUERIES = DEFAULT_TARGET_TERMS.length", source)

    def test_govdeals_sold_actor_actively_searches_target_terms(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        workflow_path = self.repo_root / ".github" / "workflows" / "run-apify-actor.yml"
        target_scope_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "target_scope.js"
        source = source_path.read_text(encoding="utf-8")
        workflow = workflow_path.read_text(encoding="utf-8")
        target_scope = target_scope_path.read_text(encoding="utf-8")
        default_target_terms = re.findall(r"'([^']+)'", target_scope.split("];", 1)[0])
        default_target_count = len(default_target_terms)

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
        self.assertIn('"out_of_scope_examples_by_query"', workflow)
        self.assertIn('actor_input["searchQuery"] = search_query', workflow)
        self.assertIn("govdeals_sold_max_pages", workflow)
        self.assertIn("govdeals_sold_seo_asset_urls", workflow)
        self.assertIn(f'default: "{default_target_count}"', workflow)
        self.assertIn(f'"maxPages": int(os.environ.get("GOVDEALS_SOLD_MAX_PAGES") or "{default_target_count}")', workflow)
        self.assertIn("max_search_queries", workflow)
        self.assertIn("MAX_SEARCH_QUERIES", workflow)
        self.assertIn('if max_search_queries:', workflow)
        self.assertIn('actor_input["maxSearchQueries"] = int(max_search_queries)', workflow)
        self.assertIn('actor_input["seoAssetUrls"] = seo_asset_urls', workflow)
        govdeals_branch = workflow.split('if actor_name == "ds-govdeals":', 1)[1].split('elif actor_name == "ds-govdeals-sold":', 1)[0]
        sold_branch = workflow.split('elif actor_name == "ds-govdeals-sold":', 1)[1].split("else:", 1)[0]
        self.assertNotIn('actor_input["seoAssetUrls"] = seo_asset_urls', govdeals_branch)
        self.assertIn('actor_input["seoAssetUrls"] = seo_asset_urls', sold_branch)
        self.assertIn('"seo_diagnostics"', workflow)
        self.assertIn('"discovery_surfaces"', workflow)
        self.assertNotIn('"maxSearchQueries": int(os.environ.get("MAX_SEARCH_QUERIES") or "10")', workflow)

    def test_govdeals_sold_actor_does_not_force_passenger_vehicle_category(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("categoryIds = input.govdealsCategoryIds ?? input.categoryIds ?? null", source)
        self.assertIn("delete payload.categoryIds", source)
        self.assertIn("payload.categoryIds = categoryScope", source)
        self.assertNotIn("payload.categoryIds = payload.categoryIds || '4100'", source)

    def test_hibid_v2_defaults_match_dealerscope_age_mileage_gate(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-hibid-v2" / "src" / "main.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("const DEFAULT_MIN_YEAR = new Date().getFullYear() - 4", source)
        self.assertIn("const DEFAULT_MAX_MILEAGE = 50000", source)
        self.assertIn("minYear = DEFAULT_MIN_YEAR", source)
        self.assertIn("maxMileage = DEFAULT_MAX_MILEAGE", source)
        self.assertNotIn("minYear = new Date().getFullYear() - 10", source)
        self.assertNotIn("maxMileage = 100000", source)

    def test_hibid_v2_clamps_loose_runtime_inputs_to_dealerscope_gate(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-hibid-v2" / "src" / "main.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("const DEFAULT_MIN_YEAR = new Date().getFullYear() - 4", source)
        self.assertIn("const DEFAULT_MAX_MILEAGE = 50000", source)
        self.assertIn("const EFFECTIVE_MIN_YEAR = Math.max(Number(minYear) || DEFAULT_MIN_YEAR, DEFAULT_MIN_YEAR)", source)
        self.assertIn("const EFFECTIVE_MAX_MILEAGE = Math.min(Number(maxMileage) || DEFAULT_MAX_MILEAGE, DEFAULT_MAX_MILEAGE)", source)
        self.assertIn("listing.year < EFFECTIVE_MIN_YEAR", source)
        self.assertIn("listing.mileage > EFFECTIVE_MAX_MILEAGE", source)
        self.assertIn("effective_min_year: EFFECTIVE_MIN_YEAR", source)
        self.assertIn("effective_max_mileage: EFFECTIVE_MAX_MILEAGE", source)

    def test_hibid_v2_excludes_quad_atv_inventory_even_with_passenger_make(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-hibid-v2" / "src" / "main.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("quad", source)
        self.assertIn("rancher", source)
        self.assertIn("foreman", source)
        self.assertIn("fourtrax", source)
        self.assertIn("recon", source)

    def test_hibid_v2_requires_mileage_before_pushing_rows(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-hibid-v2" / "src" / "main.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("listing.mileage === null", source)
        self.assertIn("[SKIP-MILES-MISSING]", source)

    def test_govdeals_sold_actor_supports_explicit_seo_asset_urls_without_enabling_search(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("seoAssetUrls = input.govdealsSeoAssetUrls ?? input.seoAssetUrls ?? []", source)
        self.assertIn("normalizeSeoAssetUrls", source)
        self.assertIn("explicit_asset_urls", source)
        self.assertIn("'seo: explicit_asset_urls'", source)
        self.assertIn("useSeoSearch = false", source)
        self.assertIn("if (!useSeoSearch) return", source)
        self.assertIn("(useSeoSearch || explicitSeoAssetUrls.length > 0)", source)

    def test_govdeals_sold_seo_fetch_uses_browser_headers_and_retries(self):
        source_path = self.repo_root / "apify" / "actors" / "ds-govdeals-sold" / "src" / "main_api.js"
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("SEO_FETCH_ATTEMPTS", source)
        self.assertIn("Chrome/125.0 Safari/537.36", source)
        self.assertIn("'sec-fetch-site': 'none'", source)
        self.assertIn("attempt < SEO_FETCH_ATTEMPTS", source)


if __name__ == "__main__":
    unittest.main()
