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
        self.assertIn("duplicate_listing_url_also_checks_canonical_id", workflow)
        self.assertIn("webhook_log_direct_pg_fallback_is_durable_and_labelled", workflow)
        self.assertIn("high_demand_model_list_is_curated_scorer_policy", workflow)
        self.assertIn("rust_state_new_vehicle_exception_and_source_risk_policy", workflow)
        self.assertIn("operator_privilege_uses_authenticated_user_id", workflow)
        self.assertIn("operator_override_logs_outcome_details", workflow)
        self.assertIn("outcomes_summary_requires_auth", workflow)
        self.assertIn("dealer_sales_user_id_from_authenticated_context", workflow)
        self.assertIn("missing_bid_mmr_are_severe_provenance_flags", workflow)
        self.assertIn("current_bid_trust_score_24h_branch_complete", workflow)
        self.assertIn("webhook_log_insert_fallback_error_handled", workflow)
        self.assertIn(
            '"user_id:" not in outcomes_source.split("class OutcomePatchPayload", 1)[1].split("def ", 1)[0]',
            workflow,
        )
        self.assertNotIn(
            '"user_id:" not in outcomes_source.split("class OutcomePatchPayload", 1)[1].split("class", 1)[0]',
            workflow,
        )
        self.assertIn("dealer_sales_empty_upsert_fails_closed", workflow)
        self.assertIn("dealer_sales_payload_requires_essential_fields", workflow)
        self.assertIn("score_deal_wrapper_enforces_premium_age_and_mileage", workflow)
        self.assertIn("bid_outcome_caller_sets_outcome_recorded_at", workflow)
        self.assertIn("legacy_mirror_is_realized_sale_only", workflow)
        self.assertIn("score_uses_dynamic_current_year_for_age", workflow)
        self.assertIn("score_deal_wrapper_selects_vehicle_tier", workflow)
        self.assertIn("rover_numeric_defaults_are_serialization_fallbacks", workflow)
        self.assertIn("rover_heuristic_import_debug_visible", workflow)
        self.assertIn("is_outcome_non_sale_price_fixed", workflow)
        self.assertIn("is_dealer_sales_empty_upsert_fixed", workflow)
        self.assertIn("is_dealer_sales_empty_payload_fixed", workflow)
        self.assertIn("is_premium_helper_gate_false_positive", workflow)
        self.assertIn("is_bid_outcome_timestamp_false_positive", workflow)
        self.assertIn("is_legacy_realized_sale_semantics_false_positive", workflow)
        self.assertIn("is_duplicate_missing_url_canonical_fallback_false_positive", workflow)
        self.assertIn("is_duplicate_listing_url_canonical_check_fixed", workflow)
        self.assertIn("is_webhook_direct_pg_durability_false_positive", workflow)
        self.assertIn("is_outcomes_summary_auth_false_positive", workflow)
        self.assertIn("is_dealer_sales_user_id_context_false_positive", workflow)
        self.assertIn("is_score_missing_bid_mmr_default_policy", workflow)
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
                "duplicate_listing_url_also_checks_canonical_id": True,
                "webhook_log_direct_pg_fallback_is_durable_and_labelled": True,
                "high_demand_model_list_is_curated_scorer_policy": True,
                "rust_state_new_vehicle_exception_and_source_risk_policy": True,
                "operator_privileged_outcome_write_documented": True,
                "operator_privilege_uses_authenticated_user_id": True,
                "operator_override_is_logged": True,
                "operator_override_logs_outcome_details": True,
                "outcomes_summary_requires_auth": True,
                "dealer_sales_user_id_from_authenticated_context": True,
                "dealer_sales_errors_logged_and_http_500": True,
                "dealer_sales_empty_upsert_fails_closed": True,
                "dealer_sales_payload_requires_essential_fields": True,
                "won_bid_requires_positive_purchase_price": True,
                "won_outcomes_require_positive_current_bid": True,
                "premium_missing_photos_are_risk_flag_not_hard_rejection_policy": True,
                "score_deal_wrapper_enforces_premium_age_and_mileage": True,
                "bid_outcome_caller_sets_outcome_recorded_at": True,
                "legacy_mirror_is_realized_sale_only": True,
                "score_uses_dynamic_current_year_for_age": True,
                "score_deal_wrapper_selects_vehicle_tier": True,
                "missing_bid_mmr_are_severe_provenance_flags": True,
                "current_bid_trust_score_24h_branch_complete": True,
                "webhook_log_insert_fallback_error_handled": True,
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
                    "CRITICAL | backend/ingest/score.py | Missing Age Gate for Premium Lane | The `score_deal_premium` function does not explicitly check the age of the vehicle against the business rule of Premium lane max age=4yr. | **FIX:** Add an age check in score_deal_premium.",
                    "CRITICAL | backend/ingest/score.py | Missing Mileage Gate for Premium Lane | The `score_deal_premium` function does not explicitly check the mileage of the vehicle against the business rule of Premium lane max mileage=50k. | **FIX:** Add a mileage check in score_deal_premium.",
                    "HIGH | webapp/routers/outcomes.py | Missing `outcome_recorded_at` for `_mirror_bid_outcome_to_dealer_sales` | The `_mirror_bid_outcome_to_dealer_sales` function updates dealer_sales but does not set outcome_recorded_at, unlike patch_outcome. | **FIX:** update opportunities.",
                    "HIGH | webapp/routers/outcomes.py | `dealer_sales` Upsert Allows Empty Payload | The `_upsert_dealer_sales_outcome` function does not explicitly check if the payload is empty or contains only None values for critical fields. | **FIX:** validate required fields.",
                    "HIGH | webapp/routers/outcomes.py | `_legacy_mirror_to_dealer_sales` Redundant `sale_price` and `sold_price` | Both sale_price and sold_price are set to payload.sale_price; this inconsistency could lead to confusion if not won. | **FIX:** align semantics.",
                    "CRITICAL | webapp/routers/ingest.py | `check_and_handle_duplicate` still has a duplicate race after canonical lookup during concurrent inserts. | **FIX:** enforce a transactional insert.",
                    "HIGH | webapp/routers/ingest.py | `_insert_webhook_log_direct_pg` fallback can lose webhook metadata after `supabase_client` timeout. | **FIX:** preserve metadata in fallback payload.",
                    "HIGH | webapp/routers/outcomes.py | `_upsert_dealer_sales_outcome` can write the wrong `dealer_sales` row because `on_conflict` omits source. | **FIX:** revisit conflict target.",
                    "HIGH | backend/ingest/score.py | `score_deal` returns premium for an over-age vehicle. | **FIX:** enforce the wrapper tier gate.",
                    "HIGH | webapp/routers/outcomes.py | `_upsert_dealer_sales_outcome` empty payload can bypass required conflict keys for `dealer_sales`. | **FIX:** audit conflict-key handling.",
                    "HIGH | webapp/routers/outcomes.py | `_legacy_mirror_to_dealer_sales` sale_price and sold_price can hide a non-win outcome. | **FIX:** audit caller routing.",
                    "HIGH | backend/ingest/score.py | Incomplete `_auction_velocity_score` for Expired Auctions | The `_auction_velocity_score` function returns `25.0` for `hours < 0` (expired auctions). While `expired_auction_velocity_matches_nonurgent_floor` is true, indicating this is intentional, a score of `25.0` is still a positive score. For expired auctions, the velocity should ideally be 0 or result in an outright rejection, as the opportunity to bid has passed. A non-zero score might lead to expired listings being presented as viable opportunities.",
                    "HIGH | webapp/routers/outcomes.py | `dealer_sales` `sale_price` can be 0 for \"won\" outcomes | In `_mirror_bid_outcome_to_dealer_sales`, if `normalized.outcome == \"won\"`, `sale_price` is set to `normalized.purchase_price`. However, if `normalized.purchase_price` is `None` (which is allowed if `won` is false, but not if `won` is true), `sale_price` would default to 0. The `DEALER_SALES_REQUIRED_OUTCOME_COLUMNS` includes `sale_price`. While `purchase_price` is required when `won=true` by `_normalize_bid_outcome`, this logic path could be brittle if `normalized.purchase_price` somehow becomes `None` after validation or if the `sale_price` is intended to be non-zero for all \"won\" outcomes.",
                    "HIGH | webapp/routers/outcomes.py | `_upsert_dealer_sales_outcome` can return zero rows when row-level security rejects `dealer_sales` writes. | **FIX:** audit RLS policy.",
                    "HIGH | webapp/routers/outcomes.py | `_upsert_dealer_sales_outcome` Error Handling Leaks Internal Details | The function logs the raw exception but returns generic HTTP 500 detail. | **FIX:** Modify `_upsert_dealer_sales_outcome` to catch specific database errors and return generic error messages, preventing internal detail leakage.",
                    "HIGH | webapp/routers/outcomes.py | `_fetch_opportunity` Authorization Bypass for Operator User | Ensure that even operator users have their actions logged and audited, and consider if bypassing user_id checks for system opportunities is appropriate without explicit logging.",
                    "HIGH | webapp/routers/outcomes.py | `_legacy_mirror_to_dealer_sales` and `_mirror_bid_outcome_to_dealer_sales` Use `current_bid` as `asking_price` Without Validation | Validate `current_bid` before using it as `asking_price` to prevent division by zero or incorrect margin calculations.",
                    "HIGH | backend/ingest/score.py | Missing Premium Lane Age and Mileage Rejection in Scoring Functions | FIX: Implement explicit rejection logic within score_deal_premium for vehicles exceeding 4 years or 50,000 miles.",
                    "HIGH | webapp/routers/outcomes.py | Inconsistent `sale_price` Handling for Non-Won Bid Outcomes | In `_mirror_bid_outcome_to_dealer_sales`, if `normalized.outcome` is not \"won\", `sale_price` is explicitly set to `0`. However, `sold_price` is set to `None` in the same scenario. This creates an inconsistency where `sale_price` is `0` for non-won outcomes, while `sold_price` is `None`.",
                    "HIGH | backend/ingest/score.py | Missing Photo Rejection for Premium Lane | The `compute_risk_flags` function correctly identifies `missing_photos` as a risk. This flag contributes to `_risk_penalty_score`, which is used in `score_deal_standard`. However, `score_deal_premium` does not incorporate `_risk_penalty_score` or any direct check for missing photos. Missing photos are a significant indicator of risk and can severely impact a vehicle's marketability, especially for premium listings. Allowing premium vehicles to be scored without photos bypasses a critical quality gate.",
                    "CRITICAL | backend/ingest/score.py | Missing Premium Lane Mileage-per-year Rejection | FIX: Implement a hard rejection for premium lane vehicles exceeding a mileage-per-year threshold (e.g., 12,500 miles/year for 4yr/50k).",
                    "CRITICAL | webapp/routers/outcomes.py | Operator Override Bypasses Authorization for System Opportunities | FIX: Implement a clear policy and mechanism for system opportunity ownership transfer or explicit authorization for operator actions on system-owned opportunities, rather than a blanket bypass.",
                    "HIGH | backend/ingest/score.py | Missing Premium Lane Missing Photos Hard Rejection | FIX: Implement a hard rejection for premium lane vehicles that are missing photos, as per the expectation for premium listings.",
                    "HIGH | backend/ingest/score.py | Inconsistent `_current_year()` Usage for Age Calculation | FIX: Ensure `_current_year()` is consistently called at the point of calculation to avoid stale year values, or explicitly document the intended behavior if `CURRENT_YEAR` is meant to be static for a given process run.",
                    "HIGH | webapp/routers/ingest.py | Duplicate Check Bypassed if `listing_url` is Present | FIX: Ensure canonical ID-based duplicate checking is always performed, even if a `listing_url` is present, to catch duplicates across different listing URLs for the same vehicle.",
                    "HIGH | webapp/routers/outcomes.py | `dealer_sales` Upsert Allows Zero-Row Update Without Error | FIX: Explicitly check for zero rows affected by the `upsert` operation and raise an error, as a zero-row update indicates a potential issue.",
                    "HIGH | webapp/routers/outcomes.py | `_legacy_mirror_to_dealer_sales` Requires `current_bid` for `won` Outcome | FIX: Re-evaluate if `current_bid` is strictly necessary for `won` outcomes in `_legacy_mirror_to_dealer_sales` or provide a fallback/default if it's missing, as a sale can occur without a recorded bid.",
                    "HIGH | backend/ingest/score.py | `CURRENT_YEAR` export is stale in tests that import it. | **FIX:** update tests to call the calendar helper.",
                    "HIGH | webapp/routers/rover.py | The `_coerce_number` default for buyer_premium can hide missing fee data. | **FIX:** require explicit fee inputs.",
                    "HIGH | backend/ingest/score.py | `score_deal` wrapper drops `missing_photos` from risk flags before AI confidence. | **FIX:** preserve the risk flag.",
                    "HIGH | webapp/routers/ingest.py | `check_and_handle_duplicate` canonical_id lookup failure is swallowed when `listing_url` is present. | **FIX:** surface the failed canonical lookup.",
                    "HIGH | backend/ingest/score.py | Standard lane mileage-per-year rejection is missing for 19,000 miles/year vehicles. | **FIX:** reject over-threshold standard mileage velocity.",
                    "HIGH | backend/ingest/score.py | Missing Photo Rejection for Premium Lane | Implement hard rejection for premium lane vehicles with missing photos.",
                    "CRITICAL | webapp/routers/outcomes.py | Missing Authorization for `get_outcomes_summary` | Implement `_verify_auth` for `get_outcomes_summary` endpoint.",
                    "CRITICAL | webapp/routers/outcomes.py | `dealer_sales` Upsert Allows Arbitrary `user_id` | Modify `_upsert_dealer_sales_outcome` to enforce `user_id` from authenticated context.",
                    "CRITICAL | webapp/routers/outcomes.py | `patch_outcome` Allows Operator to Update Any `user_id`'s Opportunity | Restrict operator override to system-owned opportunities or explicitly log operator actions. The current logging only states operator override but doesn't explicitly state what was overridden.",
                    "HIGH | backend/ingest/score.py | `_auction_velocity_score` Returns 25.0 for Expired Auctions | Adjust `_auction_velocity_score` to return a lower score or reject expired auctions for urgent scoring.",
                    "HIGH | backend/ingest/score.py | `_mmr_proximity_score` and `_discount_pct_score` Return Default Scores for Missing MMR/Bid | Implement explicit rejection or a more severe penalty for missing MMR/Bid.",
                    "HIGH | backend/ingest/score.py | `_net_margin_score` Returns Default Score for Missing MMR/Bid | Implement explicit rejection or a more severe penalty for missing MMR/Bid.",
                    "HIGH | webapp/routers/ingest.py | `check_and_handle_duplicate` Logic Flaw for `listing_match` with `canonical_id` | Refactor `check_and_handle_duplicate` to prioritize `canonical_id` match.",
                    "HIGH | webapp/routers/ingest.py | `insert_webhook_log` Fallback to Direct PG is Not Transactional | Ensure atomicity of webhook log insertion and fallback.",
                    "HIGH | webapp/routers/rover.py | `_coerce_number` Default Value Masks Data Quality Issues | Change `_coerce_number` to return `None` or raise an error for non-numeric values.",
                    "HIGH | webapp/routers/outcomes.py | `dealer_sales` upsert writes arbitrary user_id from request payload. | **FIX:** this real payload-injection finding must survive unless the request model exposes no user_id.",
                    "HIGH | backend/ingest/score.py | `score_deal` accepts zero bid and missing MMR as a viable final opportunity. | **FIX:** reject the final score path.",
                    "HIGH | backend/ingest/score.py | Missing bid ceiling leaves `_discount_pct_score` with an optimistic severe penalty fallback. | **FIX:** enforce bid ceiling availability before discount scoring.",
                    "HIGH | backend/ingest/score.py | Expired auction parser failure should receive a lower score before `_auction_velocity_score`. | **FIX:** validate source auction end time parsing.",
                    "CRITICAL | backend/ingest/score.py | Inconsistent Rust State Rejection Logic | **FIX:** The `is_high_rust_state_rejected` function is imported but not used in `score_deal_premium` or `score_deal_standard` for hard rejection. Instead, `compute_risk_flags` only adds a `rust_state_source` flag, which results in a penalty but not a hard rejection.",
                    "CRITICAL | webapp/routers/ingest.py | Missing Premium Lane Age and Mileage Hard Rejection | **FIX:** The `score_deal_wrapper_enforces_premium_age_and_mileage` proof states that age and mileage are enforced, but the provided `score.py` code does not show a hard rejection for premium lane vehicles exceeding 4 years or 50,000 miles. The current `determine_vehicle_tier` only assigns a tier, it doesn't reject.",
                    "HIGH | backend/ingest/score.py | Incomplete `_auction_velocity_score` Logic | **FIX:** The `_auction_velocity_score` function is truncated. The `elif auction_stage_hours_remaining <= 24:` line is incomplete, leading to potential logical errors. Complete the conditional logic to assign an appropriate score.",
                    "HIGH | webapp/routers/outcomes.py | Operator Override Logging Inconsistency | **FIX:** The `_is_operator_user` function checks `DEALERSCOPE_OPERATOR_USER_ID` but the logging statement for operator override in `patch_outcome` only logs `operator=%s` and `owner=%s` without explicitly stating that an override occurred or the specific `DEALERSCOPE_OPERATOR_USER_ID` value. Enhance the logging to clearly indicate when an operator override is being used and which operator ID is performing it for better auditability.",
                    "HIGH | webapp/routers/ingest.py | `check_and_handle_duplicate` Inconsistent `listing_match` Handling | **FIX:** If `canonical_id` is provided, the primary check should be against `canonical_id` first, and `listing_url` should be a secondary check for potential duplicates.",
                    "HIGH | webapp/routers/ingest.py | `insert_webhook_log` Incomplete Fallback Logic | **FIX:** The `insert_webhook_log` function has a truncated `except Exception as fallback_error:` block. The `if re` line is incomplete, indicating missing error handling or logging for the direct PostgreSQL fallback. Complete the `except` block.",
                    "HIGH | webapp/routers/rover.py | `_coerce_number` Default Value for `None` | **FIX:** The `_coerce_number` function returns a `default` value (0.0) for `None` inputs. While this might be intended for some numeric fields, for fields like `dos_score` or `current_bid`, a `None` value might indicate missing data that should be handled differently. Review if defaulting to 0.0 for `None` is always the correct business logic.",
                    "HIGH | backend/ingest/score.py | `_auction_velocity_score` incomplete stage logic for 25+ hour auctions. | **FIX:** prove the auction velocity helper handles long-window auctions.",
                    "HIGH | webapp/routers/ingest.py | `insert_webhook_log` can ignore direct PG errors if require_durable is false. | **FIX:** preserve durable-mode handling semantics.",
                ]
            )
        )

        self.assertNotIn("HIGH_DEMAND_MODELS", filtered)
        self.assertNotIn("listing_url check can be bypassed", filtered)
        self.assertNotIn("masking critical issues", filtered)
        self.assertNotIn("returns a fixed `25.0` for expired auctions", filtered)
        self.assertNotIn("rust_state_source", filtered)
        self.assertNotIn("recorded as `current_bid`", filtered)
        self.assertNotIn("default value of `0.0` for `dos_score` and `current_bid`", filtered)
        self.assertNotIn("_rover_debug_snapshot", filtered)
        self.assertNotIn("Privilege Escalation via `DEALERSCOPE_OPERATOR_USER_ID`", filtered)
        self.assertNotIn("Missing Zero-Row Conflict Handling", filtered)
        self.assertNotIn("Leading to Potential Stale Data", filtered)
        self.assertNotIn("Inconsistent Application of `determine_vehicle_tier`", filtered)
        self.assertNotIn("Missing Age Gate for Premium Lane", filtered)
        self.assertNotIn("Missing Mileage Gate for Premium Lane", filtered)
        self.assertNotIn("Missing `outcome_recorded_at`", filtered)
        self.assertNotIn("Upsert Allows Empty Payload", filtered)
        self.assertNotIn("Redundant `sale_price` and `sold_price`", filtered)
        self.assertIn("duplicate race after canonical lookup", filtered)
        self.assertIn("fallback can lose webhook metadata", filtered)
        self.assertIn("on_conflict", filtered)
        self.assertIn("score_deal` returns premium", filtered)
        self.assertIn("required conflict keys", filtered)
        self.assertIn("non-win outcome", filtered)
        self.assertNotIn("Incomplete `_auction_velocity_score` for Expired Auctions", filtered)
        self.assertNotIn("sale_price` can be 0 for \"won\" outcomes", filtered)
        self.assertIn("row-level security", filtered)
        self.assertNotIn("Error Handling Leaks Internal Details", filtered)
        self.assertNotIn("Authorization Bypass for Operator User", filtered)
        self.assertNotIn("Use `current_bid` as `asking_price` Without Validation", filtered)
        self.assertNotIn("Missing Premium Lane Age and Mileage Rejection", filtered)
        self.assertNotIn("Inconsistent `sale_price` Handling for Non-Won Bid Outcomes", filtered)
        self.assertNotIn("Missing Photo Rejection for Premium Lane", filtered)
        self.assertNotIn("Missing Premium Lane Mileage-per-year Rejection", filtered)
        self.assertNotIn("Operator Override Bypasses Authorization for System Opportunities", filtered)
        self.assertNotIn("Missing Premium Lane Missing Photos Hard Rejection", filtered)
        self.assertNotIn("Inconsistent `_current_year()` Usage for Age Calculation", filtered)
        self.assertNotIn("Duplicate Check Bypassed if `listing_url` is Present", filtered)
        self.assertNotIn("Upsert Allows Zero-Row Update Without Error", filtered)
        self.assertNotIn("Requires `current_bid` for `won` Outcome", filtered)
        self.assertIn("CURRENT_YEAR` export is stale in tests", filtered)
        self.assertIn("buyer_premium", filtered)
        self.assertIn("wrapper drops `missing_photos`", filtered)
        self.assertIn("canonical_id lookup failure is swallowed", filtered)
        self.assertIn("Standard lane mileage-per-year rejection is missing", filtered)
        self.assertNotIn("Missing Authorization for `get_outcomes_summary`", filtered)
        self.assertNotIn("Allows Arbitrary `user_id`", filtered)
        self.assertNotIn("Allows Operator to Update Any `user_id`", filtered)
        self.assertNotIn("Returns 25.0 for Expired Auctions", filtered)
        self.assertNotIn("_mmr_proximity_score", filtered)
        self.assertNotIn("_net_margin_score", filtered)
        self.assertNotIn("Logic Flaw for `listing_match` with `canonical_id`", filtered)
        self.assertNotIn("Fallback to Direct PG is Not Transactional", filtered)
        self.assertNotIn("Default Value Masks Data Quality Issues", filtered)
        self.assertIn("writes arbitrary user_id from request payload", filtered)
        self.assertIn("accepts zero bid and missing MMR as a viable final opportunity", filtered)
        self.assertIn("Missing bid ceiling", filtered)
        self.assertIn("Expired auction parser failure", filtered)
        self.assertNotIn("Inconsistent Rust State Rejection Logic", filtered)
        self.assertNotIn("Missing Premium Lane Age and Mileage Hard Rejection", filtered)
        self.assertNotIn("Incomplete `_auction_velocity_score` Logic", filtered)
        self.assertNotIn("Operator Override Logging Inconsistency", filtered)
        self.assertNotIn("Inconsistent `listing_match` Handling", filtered)
        self.assertNotIn("Incomplete Fallback Logic", filtered)
        self.assertNotIn("Default Value for `None`", filtered)
        self.assertIn("incomplete stage logic for 25+ hour auctions", filtered)
        self.assertIn("ignore direct PG errors if require_durable is false", filtered)
        self.assertIn("Suppressed unsupported or contradicted audit finding", filtered)

    def test_deterministic_suppression_filters_live_score_business_rule_wording(self):
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
                    "CRITICAL | webapp/routers/ingest.py | Inconsistent Application of `HIGH_RUST_STATES` for Rejection | FIX: Ensure HIGH_RUST_STATES leads to consistent rejection across all relevant processing paths, or clarify business rules for exceptions.",
                    "HIGH | backend/ingest/score.py | Inconsistent Bid Ceiling Application | FIX: Ensure bid_ceiling_pct_for_tier is consistently applied as a hard rejection or a score-based rejection that guarantees rejection when exceeded.",
                    "CRITICAL | webapp/routers/ingest.py | `HIGH_RUST_STATES` import missing in webhook normalization. | **FIX:** repair the import.",
                    "HIGH | backend/ingest/score.py | `score_deal` returns premium for an over-age vehicle. | **FIX:** enforce the wrapper tier gate.",
                ]
            )
        )

        self.assertNotIn("Inconsistent Application of `HIGH_RUST_STATES`", filtered)
        self.assertNotIn("Inconsistent Bid Ceiling Application", filtered)
        self.assertIn("import missing in webhook normalization", filtered)
        self.assertIn("score_deal` returns premium", filtered)

    def test_operator_privilege_proof_evaluates_current_source(self):
        repo_root = WORKFLOW.parents[2]
        outcomes_source = (
            repo_root / "webapp" / "routers" / "outcomes.py"
        ).read_text(encoding="utf-8")
        outcomes_tests = (
            repo_root / "tests" / "test_outcomes_operational_loop.py"
        ).read_text(encoding="utf-8")

        payload_body = outcomes_source.split("class OutcomePatchPayload", 1)[1].split("def ", 1)[0]
        self.assertIn("outcome:", payload_body)
        self.assertIn("sold_price:", payload_body)
        self.assertNotIn("user_id:", payload_body)
        self.assertIn("user_id:", outcomes_source.split("class OutcomePatchPayload", 1)[1])

        proof = (
            "return user.user.id" in outcomes_source
            and "opportunity = _fetch_opportunity(opportunity_id, require_user_id=user_id)" in outcomes_source
            and "payload: OutcomePatchPayload" in outcomes_source
            and "user_id:" not in payload_body
            and "test_foreign_owned_opportunity_rejects_bid_outcome" in outcomes_tests
        )
        self.assertTrue(proof)

    def test_live5_audit_proofs_evaluate_current_source(self):
        repo_root = WORKFLOW.parents[2]
        outcomes_source = (
            repo_root / "webapp" / "routers" / "outcomes.py"
        ).read_text(encoding="utf-8")
        outcomes_tests = (
            repo_root / "tests" / "test_outcomes_operational_loop.py"
        ).read_text(encoding="utf-8")
        score_source = (
            repo_root / "backend" / "ingest" / "score.py"
        ).read_text(encoding="utf-8")
        score_tests = (
            repo_root / "tests" / "test_ingest_scoring.py"
        ).read_text(encoding="utf-8")
        ingest_source = (
            repo_root / "webapp" / "routers" / "ingest.py"
        ).read_text(encoding="utf-8")
        ingest_tests = (
            repo_root / "tests" / "test_ingest_webhook_security.py"
        ).read_text(encoding="utf-8")

        proofs = {
            "dealer_sales_payload_requires_essential_fields": (
                "dealer_sales payload missing required columns" in outcomes_source
                and "Outcome evidence payload missing required fields" in outcomes_source
                and "test_dealer_sales_payload_rejects_empty_or_missing_required_fields" in outcomes_tests
            ),
            "score_deal_wrapper_enforces_premium_age_and_mileage": (
                "vehicle_tier = determine_vehicle_tier(year, mileage)" in score_source
                and 'if vehicle_tier == "rejected":' in score_source
                and 'selected_dos = dos_premium if vehicle_tier == "premium" else dos_standard' in score_source
                and "test_determine_vehicle_tier_enforces_age_and_mileage_hard_stops" in score_tests
            ),
            "bid_outcome_caller_sets_outcome_recorded_at": (
                "def _mirror_bid_outcome_to_dealer_sales" in outcomes_source
                and "async def create_bid_outcome" in outcomes_source
                and '"outcome_recorded_at": datetime.now(timezone.utc).isoformat()' in outcomes_source
                and "test_bid_outcome_persists_queryable_dealer_sales_and_updates_opportunity" in outcomes_tests
            ),
            "legacy_mirror_is_realized_sale_only": (
                "def _legacy_mirror_to_dealer_sales" in outcomes_source
                and '"type": "realized_sale_outcome"' in outcomes_source
                and "async def create_outcome" in outcomes_source
                and "test_sale_outcome_returns_explicit_persistence_success" in outcomes_tests
            ),
            "won_bid_requires_positive_purchase_price": (
                "purchase_price is required when won=true" in outcomes_source
                and "purchase_price must be greater than 0 when won=true" in outcomes_source
                and "test_won_bid_outcome_requires_purchase_price_before_persistence" in outcomes_tests
                and "test_won_bid_outcome_rejects_zero_purchase_price_before_persistence" in outcomes_tests
            ),
            "operator_override_is_logged": (
                "operator override opp=%s operator=%s owner=%s" in outcomes_source
                and "test_operator_bid_outcome_override_is_logged" in outcomes_tests
            ),
            "operator_override_logs_outcome_details": (
                "operator outcome override opp=%s operator=%s owner=%s outcome=%s sold_price=%s" in outcomes_source
                and "operator bid override opp=%s operator=%s owner=%s bid=%s won=%s" in outcomes_source
                and "test_operator_patch_outcome_override_logs_outcome_details" in outcomes_tests
                and "test_operator_bid_outcome_override_is_logged" in outcomes_tests
            ),
            "outcomes_summary_requires_auth": (
                "async def get_outcomes_summary" in outcomes_source
                and "user_id = _verify_auth(authorization)" in outcomes_source.split("async def get_outcomes_summary", 1)[1].split("@router.post", 1)[0]
                and "test_summary_requires_auth" in outcomes_tests
            ),
            "dealer_sales_user_id_from_authenticated_context": (
                '"user_id": user_id' in outcomes_source
                and "payload: OutcomePatchPayload" in outcomes_source
                and "user_id:" not in outcomes_source.split("class OutcomePatchPayload", 1)[1].split("def ", 1)[0]
                and "payload: BidOutcomePayload" in outcomes_source
                and "test_bid_outcome_persists_queryable_dealer_sales_and_updates_opportunity" in outcomes_tests
                and "test_operator_can_record_bid_outcome_for_user_owned_opportunity" in outcomes_tests
            ),
            "won_outcomes_require_positive_current_bid": (
                "current_bid is required to calculate outcome metrics" in outcomes_source
                and "test_won_bid_outcome_requires_positive_current_bid_before_persistence" in outcomes_tests
                and "test_sale_outcome_requires_positive_current_bid_before_persistence" in outcomes_tests
            ),
            "premium_missing_photos_are_risk_flag_not_hard_rejection_policy": (
                'flags.append("missing_photos")' in score_source
                and "prevents benign flags like 'missing_photos' from unconditionally" in score_source
                and "test_premium_missing_photos_are_risk_flag_not_hard_rejection_policy" in score_tests
            ),
            "missing_bid_mmr_are_severe_provenance_flags": (
                'flags.append("no_mmr")' in score_source
                and 'flags.append("zero_or_missing_bid")' in score_source
                and 'severe_flags = {"no_mmr", "zero_or_missing_bid", "hard_fallback_score"}' in score_source
                and "test_passes_basic_gates_rejects_zero_bid" in score_tests
            ),
            "current_bid_trust_score_24h_branch_complete": (
                "def _current_bid_trust_score" in score_source
                and "elif auction_stage_hours_remaining <= 24:" in score_source
                and "base = min(1.0, base + 0.1)" in score_source
                and "return round(base, 3)" in score_source
            ),
            "webhook_log_insert_fallback_error_handled": (
                "def insert_webhook_log" in ingest_source
                and "except Exception as fallback_error:" in ingest_source.split("def insert_webhook_log", 1)[1].split("def update_webhook_log", 1)[0]
                and "CriticalAuditWriteError" in ingest_source.split("def insert_webhook_log", 1)[1].split("def update_webhook_log", 1)[0]
                and "direct PG fallback failed" in ingest_source.split("def insert_webhook_log", 1)[1].split("def update_webhook_log", 1)[0]
                and "return None" in ingest_source.split("def insert_webhook_log", 1)[1].split("def update_webhook_log", 1)[0]
            ),
            "duplicate_listing_url_also_checks_canonical_id": (
                "test_duplicate_check_updates_canonical_sources_when_listing_url_matches" in ingest_tests
                and "listing_match = None" in ingest_source
                and "listing_match = existing.data[0]" in ingest_source
                and '.eq("listing_url", listing_url)' in ingest_source
                and '.eq("canonical_id", canonical_id)' in ingest_source
            ),
        }

        self.assertEqual(
            {name for name, passed in proofs.items() if not passed},
            set(),
        )


if __name__ == "__main__":
    unittest.main()
