from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
