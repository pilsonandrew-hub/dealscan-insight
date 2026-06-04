from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "reconcile-condition-blocked-scores.yml"
)


def test_reconcile_workflow_supports_single_opportunity_source_trace_mode():
    text = WORKFLOW.read_text()

    assert "opportunity_id:" in text
    assert "APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}" in text
    assert "OPPORTUNITY_ID: ${{ github.event.inputs.opportunity_id }}" in text
    assert '--opportunity-id "${OPPORTUNITY_ID}"' in text
    assert "scripts/reconcile_condition_blocked_scores.py" in text
