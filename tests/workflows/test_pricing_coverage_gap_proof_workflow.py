from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pricing-coverage-gap-proof.yml"


def test_pricing_coverage_gap_proof_uses_supabase_rest():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "SUPABASE_URL" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "scripts/report_pricing_coverage_gaps.py" in text
    assert "--via-rest" in text
    assert "max_age_years" in text
    assert "MAX_AGE_YEARS" in text
    assert "--max-age-years" in text


def test_pricing_coverage_gap_proof_defaults_to_standard_lane():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'default: "100000"' in text
    assert 'default: "10"' in text
    assert 'default: "50000"' not in text
    assert 'default: "4"' not in text


def test_pricing_coverage_gap_proof_can_print_grouped_output():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "grouped:" in text
    assert "GROUPED" in text
    assert "--grouped" in text


def test_pricing_coverage_gap_proof_supports_queue_dry_run():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "sync_queue:" in text
    assert "SYNC_PRICING_RECOVERY_OPERATOR_QUEUE" in text
    assert "--queue-dry-run" in text
    assert "--queue-apply" in text
    assert "scripts/pricing_recovery_operator_queue.py" in text
