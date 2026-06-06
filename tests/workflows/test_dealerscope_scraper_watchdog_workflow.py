import ast
import json
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dealerscope-scraper-watchdog.yml"
DEPLOYMENT_MANIFEST = Path(__file__).resolve().parents[2] / "apify" / "deployment.json"


def _watchdog_actors():
    text = WORKFLOW.read_text()
    marker = "ACTORS = {"
    start = text.index(marker) + len(marker)
    depth = 1
    cursor = start
    while cursor < len(text) and depth:
        if text[cursor] == "{":
            depth += 1
        elif text[cursor] == "}":
            depth -= 1
        cursor += 1
    return ast.literal_eval("{" + text[start:cursor])


def test_watchdog_monitors_active_hibid_v2_actor():
    text = WORKFLOW.read_text()

    assert '"ds-hibid-v2"' in text
    assert '"7s9e0eATTt1kuGGfE"' in text
    assert "ds-hibid intentionally disabled, excluded from monitoring" not in text


def test_watchdog_monitors_every_enabled_live_scheduled_actor():
    payload = json.loads(DEPLOYMENT_MANIFEST.read_text())
    expected = {
        name: actor["id"]
        for name, actor in payload["actors"].items()
        if actor.get("status") == "enabled"
        and actor.get("scheduleStatus") == "enabled_live"
        and actor.get("schedule")
    }

    actual = {name: config["id"] for name, config in _watchdog_actors().items()}

    assert actual == expected


def test_watchdog_stale_thresholds_match_enabled_live_schedules():
    actors = _watchdog_actors()

    assert actors["ds-equipmentfacts"]["max_age_hours"] == 9
    for actor_name, actor in actors.items():
        if actor_name == "ds-equipmentfacts":
            continue
        assert actor["max_age_hours"] == 15
