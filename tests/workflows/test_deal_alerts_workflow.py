from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deal-alerts.yml"


def test_deal_alerts_workflow_runs_active_alert_runner():
    assert WORKFLOW.exists()

    text = WORKFLOW.read_text()
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "scripts/deal-alerts.sh" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "TELEGRAM_BOT_TOKEN" in text
    assert "TELEGRAM_CHAT_ID" in text
