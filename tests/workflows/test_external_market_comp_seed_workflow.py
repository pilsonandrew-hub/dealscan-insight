from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "external-market-comp-seed.yml"


def test_external_market_comp_seed_workflow_is_manual_and_guarded():
    text = WORKFLOW.read_text()
    lower = text.lower()

    assert "workflow_dispatch:" in text
    for trigger in ("push:", "pull_request:", "schedule:", "release:"):
        assert trigger not in text

    assert "DATABASE_URL:" not in text
    assert "SUPABASE_DB_PASSWORD: ${{ secrets.SUPABASE_DB_PASSWORD }}" in text
    assert "SUPABASE_PROJECT_ID: ${{ secrets.SUPABASE_PROJECT_ID }}" in text
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in text
    assert "scripts/prepare_external_market_comp_seed.py" in text
    assert "scripts/verify_pricing_substrate.py --require-ready" in text
    assert "scripts/report_pricing_blocked_source_candidates.py" in text
    assert "--input" in text
    assert "reports/external-comp-evidence-" in text
    assert "INSERT_EXTERNAL_MARKET_COMP" in text
    assert "APPLY_EXTERNAL_COMP" in text
    assert "--apply" in text
    assert "default: \"false\"" in text
    assert "type: choice" in text
    assert "set -x" not in lower
