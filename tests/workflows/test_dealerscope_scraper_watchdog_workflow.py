from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dealerscope-scraper-watchdog.yml"


def test_watchdog_monitors_active_hibid_v2_actor():
    text = WORKFLOW.read_text()

    assert '"ds-hibid-v2"' in text
    assert '"7s9e0eATTt1kuGGfE"' in text
    assert "ds-hibid intentionally disabled, excluded from monitoring" not in text
