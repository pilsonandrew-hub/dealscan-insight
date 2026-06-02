from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deal-expiry-sweeper.yml"


def test_deal_expiry_sweeper_workflow_uses_tested_script():
    text = WORKFLOW.read_text()

    assert "python3 scripts/deal_expiry_sweeper.py" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "TELEGRAM_BOT_TOKEN" in text
