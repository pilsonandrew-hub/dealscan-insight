from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "sold-comp-verifier.yml"


def test_sold_comp_verifier_workflow_is_manual_and_defaults_to_dry_run():
    text = WORKFLOW.read_text()
    lower = text.lower()

    assert "workflow_dispatch:" in text
    assert "dry_run:" in text
    assert 'default: "true"' in text
    assert "schedule:" not in text
    for trigger in ("push:", "pull_request:", "release:"):
        assert trigger not in text

    assert "timeout-minutes: 10" in text
    assert "contents: read" in text
    assert "python3 scripts/run_sold_comp_verifier.py" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "DATABASE_URL:" not in text
    assert "SUPABASE_DB_PASSWORD:" not in text
    assert "set -x" not in lower
