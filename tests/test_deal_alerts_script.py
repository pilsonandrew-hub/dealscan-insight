import re
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deal-alerts.sh"


def test_active_deal_alert_runner_queries_only_active_opportunities():
    text = SCRIPT.read_text()

    assert "is_active=eq.true" in text


def test_active_deal_alert_runner_selects_alert_gate_evidence_fields():
    text = SCRIPT.read_text()
    select_match = re.search(
        r'opportunities\?select=(?P<select>.*?)"\n\s*"&is_active=eq.true"',
        text,
        flags=re.DOTALL,
    )
    assert select_match is not None
    selected_columns = {
        column.strip()
        for column in select_match.group("select").replace('"', "").replace("\n", "").split(",")
        if column.strip()
    }

    for field in (
        "vin",
        "mileage",
        "condition_grade",
        "vehicle_tier",
        "estimated_days_to_sale",
    ):
        assert field in selected_columns


def test_active_deal_alert_runner_fetches_raw_data_only_after_preliminary_gate():
    text = SCRIPT.read_text()

    assert "CANDIDATE_LIMIT = max(ALERT_LIMIT * 2, 10)" in text
    assert "limit={CANDIDATE_LIMIT}" in text
    assert "fetch_raw_data_by_id(raw_data_needed_ids)" in text
    assert "opportunities?select=id,raw_data&id=in." in text


def test_active_deal_alert_runner_uses_tier_satisfaction_not_exact_membership():
    text = SCRIPT.read_text()

    assert "def alert_type_satisfies" in text
    assert "alert_type_satisfies(alert_type, prior)" in text
