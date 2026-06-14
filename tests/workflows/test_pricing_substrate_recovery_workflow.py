from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pricing-substrate-recovery.yml"


def test_pricing_substrate_recovery_workflow_is_manual_and_confirmation_gated():
    text = WORKFLOW.read_text(encoding="utf-8")
    lower = text.lower()

    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "pull_request:" not in text
    assert "apply:" in text
    assert "confirmation:" in text
    assert "REFRESH_MARKET_PRICES_FROM_COMPLETED_SALES" in text
    assert "scripts/refresh_market_prices_from_completed_sales.py" in text
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in text
    assert "SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}" in text
    assert "psycopg2-binary==2.9.9" in text
    assert "set -x" not in lower
