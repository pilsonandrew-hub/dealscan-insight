from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "external-market-comp-seed.yml"


def test_external_market_comp_seed_workflow_is_manual_and_guarded():
    text = WORKFLOW.read_text()
    lower = text.lower()

    assert "workflow_dispatch:" in text
    for trigger in ("push:", "pull_request:", "schedule:", "release:"):
        assert trigger not in text

    assert "DATABASE_URL:" not in text
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in text
    assert "SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}" in text
    assert "SUPABASE_DB_PASSWORD:" not in text
    assert "SUPABASE_USE_POOLER:" not in text
    assert "scripts/prepare_external_market_comp_seed.py" in text
    assert "--apply-via-rest" in text
    assert "scripts/verify_pricing_substrate.py --require-ready" not in text
    assert "--input" in text
    assert "reports/external-comp-evidence-" in text
    assert "INSERT_EXTERNAL_MARKET_COMP" in text
    assert "APPLY_EXTERNAL_COMP" in text
    assert "--apply" in text
    assert "default: \"false\"" in text
    assert "type: choice" in text
    assert "set -x" not in lower
