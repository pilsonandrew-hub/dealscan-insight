from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pricing-coverage-gap-proof.yml"


def test_pricing_coverage_gap_proof_uses_supabase_rest():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "SUPABASE_URL" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "scripts/report_pricing_coverage_gaps.py" in text
    assert "--via-rest" in text
