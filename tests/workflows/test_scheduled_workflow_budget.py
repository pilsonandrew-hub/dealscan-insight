from pathlib import Path


WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
MIN_SCHEDULE_INTERVAL_MINUTES = 6 * 60


def _cron_interval_minutes(cron: str) -> int:
    minute, hour, *_ = cron.split()
    if minute.startswith("*/"):
        return int(minute.removeprefix("*/"))
    if hour.startswith("*/"):
        return int(hour.removeprefix("*/")) * 60
    return 24 * 60


def _scheduled_crons(workflow_text: str) -> list[str]:
    crons: list[str] = []
    for line in workflow_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- cron:"):
            crons.append(stripped.split(":", 1)[1].strip().strip("'\""))
    return crons


def test_scheduled_workflows_respect_actions_minute_budget_floor():
    violations: list[str] = []

    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        for cron in _scheduled_crons(path.read_text(encoding="utf-8")):
            interval = _cron_interval_minutes(cron)
            if interval < MIN_SCHEDULE_INTERVAL_MINUTES:
                violations.append(f"{path.name}: {cron} every {interval} minutes")

    assert violations == []
