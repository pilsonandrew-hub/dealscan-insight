from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deal-alerts.sh"


def test_active_deal_alert_runner_queries_only_active_opportunities():
    text = SCRIPT.read_text()

    assert "is_active=eq.true" in text
