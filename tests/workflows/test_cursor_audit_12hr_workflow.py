from pathlib import Path
import re
import textwrap
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "cursor-audit-12hr.yml"
)


class CursorAudit12hrWorkflowTest(unittest.TestCase):
    def test_gemini_audit_failure_is_not_swallowed_as_green(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Gemini audit unavailable after", workflow)
        self.assertIn("raise SystemExit(1)", workflow)
        self.assertNotIn('print(f"Gemini audit error: {e}")', workflow)

    def test_gemini_audit_retries_rate_limits_before_degrading(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("urllib.error", workflow)
        self.assertIn("time.sleep", workflow)
        self.assertIn("GEMINI_AUDIT_MAX_ATTEMPTS", workflow)
        self.assertIn("GEMINI_AUDIT_RETRY_DELAY_SECONDS", workflow)

    def test_gemini_audit_has_openrouter_gemini_fallback(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("OPENROUTER_KEY", workflow)
        self.assertIn("GEMINI_OPENROUTER_MODEL", workflow)
        self.assertIn("https://openrouter.ai/api/v1/chat/completions", workflow)
        self.assertIn("fetch_openrouter_gemini_audit", workflow)
        self.assertIn("Direct Gemini audit unavailable", workflow)

    def test_gemini_audit_suppresses_deterministically_false_business_rule_findings(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("business_rule_proof", workflow)
        self.assertIn("rust_state_oh", workflow)
        self.assertIn("standard_miles_per_year_over_18000", workflow)
        self.assertIn("Missing Rust State Rejection", workflow)
        self.assertIn("Mileage-per-year Rejection Bypass", workflow)
        self.assertIn("Incomplete Bid Ceiling Enforcement", workflow)

    def test_gemini_audit_escapes_telegram_html_and_names_alert_delivery_failures(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("send_telegram_html_message", workflow)
        self.assertIn("html.escape(findings)", workflow)
        self.assertIn("DealerScope audit alert delivery failed", workflow)
        self.assertIn("raise RuntimeError(\"DealerScope audit alert delivery failed", workflow)

    def test_gemini_audit_filters_unsupported_or_contradicted_findings(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("audit_evidence_proof", workflow)
        self.assertIn("suppress_unsupported_or_contradicted_findings", workflow)
        self.assertIn("Insecure Direct Object Reference", workflow)
        self.assertIn("SQL Injection Vulnerability", workflow)
        self.assertIn("Potential for Race Condition", workflow)
        self.assertIn("Suppressed unsupported or contradicted audit finding", workflow)
        self.assertIn("coerce_float_normalizes_formatted_numeric_strings", workflow)
        self.assertIn("_gates_coerce_float", workflow)
        self.assertIn("_rover_coerce_float", workflow)
        self.assertIn("critical_audit_write_errors_handled_upstream", workflow)
        self.assertIn("dealer_sales_errors_logged_and_http_500", workflow)
        self.assertIn("is_outcomes_configuration_speculation", workflow)
        self.assertIn("is_ingest_error_handling_speculation", workflow)
        self.assertIn("is_dealer_sales_error_handling_false_positive", workflow)
        self.assertIn("is_operator_privilege_authorization_false_positive", workflow)
        self.assertIn("is_outcome_update_zero_row_semantics_false_positive", workflow)
        self.assertIn("is_rover_redis_affinity_operational_posture", workflow)
        self.assertIn("business rule application", workflow)
        self.assertIn("only applies a penalty", workflow)
        self.assertIn("missing authorization for opportunity update", workflow)
        self.assertIn("redis affinity failure mode", workflow)
        self.assertIn("mileage-per-year\" in normalized and \"rejection logic\" in normalized", workflow)
        self.assertIn("zero row conflict not handled", workflow)
        self.assertIn("logging it as a warning", workflow)
        self.assertIn("expired_auction_velocity_matches_nonurgent_floor", workflow)
        self.assertIn("not particularly low", workflow)
        self.assertIn("outcomes_non_sale_price_zero", workflow)
        self.assertIn("duplicate_missing_listing_url_uses_canonical_id", workflow)
        self.assertIn("webhook_log_direct_pg_fallback_is_durable_and_labelled", workflow)
        self.assertIn("high_demand_model_list_is_curated_scorer_policy", workflow)
        self.assertIn("rust_state_new_vehicle_exception_and_source_risk_policy", workflow)
        self.assertIn("operator_privilege_uses_authenticated_user_id", workflow)
        self.assertIn("dealer_sales_empty_upsert_fails_closed", workflow)
        self.assertIn("score_uses_dynamic_current_year_for_age", workflow)
        self.assertIn("score_deal_wrapper_selects_vehicle_tier", workflow)
        self.assertIn("rover_numeric_defaults_are_serialization_fallbacks", workflow)
        self.assertIn("rover_heuristic_import_debug_visible", workflow)
        self.assertIn("is_outcome_non_sale_price_fixed", workflow)
        self.assertIn("is_dealer_sales_empty_upsert_fixed", workflow)
        self.assertIn("is_duplicate_missing_url_canonical_fallback_false_positive", workflow)
        self.assertIn("is_webhook_direct_pg_durability_false_positive", workflow)
        self.assertIn("is_current_year_staleness_false_positive", workflow)
        self.assertIn("is_score_deal_premium_tier_helper_opinion", workflow)
        self.assertIn("is_high_demand_dynamic_policy_opinion", workflow)
        self.assertIn("is_rust_state_penalty_policy_opinion", workflow)
        self.assertIn("is_rover_numeric_default_serialization_policy", workflow)
        self.assertIn("is_rover_heuristic_import_debug_posture", workflow)
        self.assertNotIn(
            'any(term in normalized for term in ("generic 500", "empty", "zero rows", "inconsistent error handling"))',
            workflow,
        )
        self.assertIn("starts_pipe_finding", workflow)
        self.assertIn('stripped.startswith(("critical |", "high |"))', workflow)
        self.assertIn("stripped.count(\"|\") < 3", workflow)
        self.assertNotIn(
            'or stripped.startswith("**high** | webapp/routers/rover.")',
            workflow,
        )
        self.assertNotIn('"(implied)" in normalized', workflow)

    def test_deterministic_suppression_keeps_next_pipe_formatted_finding(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        function_match = re.search(
            r"          def suppress_deterministically_false_findings"
            r"\(findings: str\) -> str:\n"
            r"(?P<body>.*?)(?=\n          def suppress_unsupported_or_contradicted_findings)",
            workflow,
            re.S,
        )
        self.assertIsNotNone(function_match)

        namespace = {
            "re": re,
            "bid_ceiling_gate_passed": True,
            "business_rule_gate_passed": True,
        }
        exec(
            textwrap.dedent(
                "def suppress_deterministically_false_findings(findings: str) -> str:\n"
                + function_match.group("body")
            ),
            namespace,
        )

        filtered = namespace["suppress_deterministically_false_findings"](
            "\n".join(
                [
                    "HIGH | backend/ingest/score.py | Mileage-per-year rejection logic | contradicted",
                    "continued stale detail",
                    "CRITICAL | backend/ingest/score.py | Real parser crash | keep this",
                    "real detail must stay",
                ]
            )
        )

        self.assertNotIn("Mileage-per-year rejection logic", filtered)
        self.assertNotIn("continued stale detail", filtered)
        self.assertIn("CRITICAL | backend/ingest/score.py | Real parser crash | keep this", filtered)
        self.assertIn("real detail must stay", filtered)

    def test_unsupported_suppression_filters_live_proof_contradicted_findings(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        function_match = re.search(
            r"          def suppress_unsupported_or_contradicted_findings"
            r"\(findings: str\) -> str:\n"
            r"(?P<body>.*?)(?=\n          prompt = )",
            workflow,
            re.S,
        )
        self.assertIsNotNone(function_match)

        namespace = {
            "re": re,
            "audit_evidence_proof": {
                "outcomes_non_sale_price_zero": True,
                "duplicate_missing_listing_url_uses_canonical_id": True,
                "webhook_log_direct_pg_fallback_is_durable_and_labelled": True,
                "high_demand_model_list_is_curated_scorer_policy": True,
                "rust_state_new_vehicle_exception_and_source_risk_policy": True,
                "operator_privileged_outcome_write_documented": True,
                "operator_privilege_uses_authenticated_user_id": True,
                "dealer_sales_empty_upsert_fails_closed": True,
                "score_uses_dynamic_current_year_for_age": True,
                "score_deal_wrapper_selects_vehicle_tier": True,
                "expired_auction_velocity_matches_nonurgent_floor": True,
                "rover_numeric_defaults_are_serialization_fallbacks": True,
                "rover_heuristic_import_debug_visible": True,
            },
        }
        exec(
            textwrap.dedent(
                "def suppress_unsupported_or_contradicted_findings(findings: str) -> str:\n"
                + function_match.group("body")
            ),
            namespace,
        )

        filtered = namespace["suppress_unsupported_or_contradicted_findings"](
            "\n".join(
                [
                    "CRITICAL | backend/ingest/score.py | Hardcoded `HIGH_DEMAND_MODELS` list is not dynamic and can lead to missed opportunities for new popular models. | **FIX:** Implement a mechanism to dynamically update `HIGH_DEMAND_MODELS` from a database or external API.",
                    "CRITICAL | webapp/routers/ingest.py | `check_and_handle_duplicate` function's `listing_url` check can be bypassed if the `listing_url` is missing, leading to duplicate entries. | **FIX:** If missing, fall back to `canonical_id` check immediately.",
                    "CRITICAL | webapp/routers/ingest.py | The `_insert_webhook_log_direct_pg` function is called as a fallback for `insert_webhook_log` without proper error handling for the primary `supabase_client` failure, potentially masking critical issues; require_durable should raise primary_error. | **FIX:** Modify `insert_webhook_log`.",
                    "HIGH | backend/ingest/score.py | The `_auction_velocity_score` function returns a fixed `25.0` for expired auctions. This might not align with business rules if expired auctions should be rejected or scored differently. | **FIX:** Clarify business rules.",
                    "HIGH | backend/ingest/score.py | The `_risk_penalty_score` function applies a fixed penalty for \"rust_state_source\" regardless of the vehicle's age. For newer vehicles this penalty might be overly harsh. | **FIX:** Introduce a conditional penalty.",
                    "HIGH | webapp/routers/outcomes.py | In `patch_outcome`, the `sale_price` is recorded as `current_bid` for lost or passed outcomes, which is misleading as no sale occurred. | **FIX:** set sale_price to 0.",
                    "HIGH | webapp/routers/rover.py | The `_coerce_number` function uses a default value of `0.0` for `dos_score` and `current_bid`. If these values are missing or invalid, consider using None. | **FIX:** Handle None.",
                    "HIGH | webapp/routers/rover.py | The `_rover_debug_snapshot` function logs a warning if `heuristic_scorer` import fails but does not prevent the application from starting, potentially leading to silent failures. | **FIX:** Treat as critical error.",
                    "CRITICAL | webapp/routers/outcomes.py | Privilege Escalation via `DEALERSCOPE_OPERATOR_USER_ID` | The `_is_operator_user` function and its usage in `patch_outcome` allow any authenticated user to bypass ownership checks on opportunities if they set their `user_id` to match `DEALERSCOPE_OPERATOR_USER_ID`. | **FIX:** restrict operator use.",
                    "CRITICAL | webapp/routers/outcomes.py | Missing Zero-Row Conflict Handling for `dealer_sales` Upsert | The `_upsert_dealer_sales_outcome` function does not explicitly check for zero rows after an `upsert` operation on the `dealer_sales` table. | **FIX:** check result.data.",
                    "HIGH | backend/ingest/score.py | Inconsistent `_current_year()` Usage Leading to Potential Stale Data | The `CURRENT_YEAR` constant is initialized once at module load time using `_current_year()`, so calculations may become stale across a year boundary. | **FIX:** use dynamic year calls.",
                    "HIGH | backend/ingest/score.py | Inconsistent Application of `determine_vehicle_tier` | `score_deal_premium` does not call `determine_vehicle_tier`, which could lead to subtle inconsistencies and does not future-proof premium scoring. | **FIX:** call determine_vehicle_tier inside premium helper.",
                    "CRITICAL | webapp/routers/ingest.py | `check_and_handle_duplicate` still has a duplicate race after canonical lookup during concurrent inserts. | **FIX:** enforce a transactional insert.",
                    "HIGH | webapp/routers/ingest.py | `_insert_webhook_log_direct_pg` fallback can lose webhook metadata after `supabase_client` timeout. | **FIX:** preserve metadata in fallback payload.",
                    "HIGH | webapp/routers/outcomes.py | `_upsert_dealer_sales_outcome` can write the wrong `dealer_sales` row because `on_conflict` omits source. | **FIX:** revisit conflict target.",
                    "HIGH | webapp/routers/outcomes.py | `_upsert_dealer_sales_outcome` accepts an empty payload for `dealer_sales`. | **FIX:** validate required payload fields.",
                    "HIGH | backend/ingest/score.py | `CURRENT_YEAR` export is stale in tests that import it. | **FIX:** update tests to call the calendar helper.",
                    "HIGH | webapp/routers/rover.py | The `_coerce_number` default for buyer_premium can hide missing fee data. | **FIX:** require explicit fee inputs.",
                ]
            )
        )

        self.assertNotIn("HIGH_DEMAND_MODELS", filtered)
        self.assertNotIn("listing_url check can be bypassed", filtered)
        self.assertNotIn("masking critical issues", filtered)
        self.assertNotIn("_auction_velocity_score", filtered)
        self.assertNotIn("rust_state_source", filtered)
        self.assertNotIn("sale_price", filtered)
        self.assertNotIn("default value of `0.0` for `dos_score` and `current_bid`", filtered)
        self.assertNotIn("_rover_debug_snapshot", filtered)
        self.assertNotIn("Privilege Escalation via `DEALERSCOPE_OPERATOR_USER_ID`", filtered)
        self.assertNotIn("Missing Zero-Row Conflict Handling", filtered)
        self.assertNotIn("Leading to Potential Stale Data", filtered)
        self.assertNotIn("Inconsistent Application of `determine_vehicle_tier`", filtered)
        self.assertIn("duplicate race after canonical lookup", filtered)
        self.assertIn("fallback can lose webhook metadata", filtered)
        self.assertIn("on_conflict", filtered)
        self.assertIn("empty payload", filtered)
        self.assertIn("CURRENT_YEAR` export is stale in tests", filtered)
        self.assertIn("buyer_premium", filtered)
        self.assertIn("Suppressed unsupported or contradicted audit finding", filtered)


if __name__ == "__main__":
    unittest.main()
