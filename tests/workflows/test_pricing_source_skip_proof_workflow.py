from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pricing-source-skip-proof.yml"


def test_pricing_source_skip_proof_workflow_uses_rest_read_path_only():
    text = WORKFLOW.read_text()
    lower = text.lower()

    assert "workflow_dispatch:" in text
    for trigger in ("push:", "pull_request:", "schedule:", "release:"):
        assert trigger not in text

    assert "DATABASE_URL:" not in text
    assert "SUPABASE_DB_PASSWORD:" not in text
    assert "SUPABASE_USE_POOLER:" not in text
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in text
    assert "SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}" in text
    assert "scripts/report_pricing_blocked_source_candidates.py" in text
    assert "--via-rest" in text
    assert "--lookback-days" in text
    assert "--max-mileage" in text
    assert "set -x" not in lower


def test_pricing_source_skip_proof_defaults_to_standard_lane():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert 'default: "100000"' in text
    assert 'default: "10"' in text
    assert 'default: "50000"' not in text
    assert 'default: "4"' not in text
