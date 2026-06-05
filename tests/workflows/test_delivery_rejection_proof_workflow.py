from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "delivery-rejection-proof.yml"


def test_delivery_rejection_proof_workflow_uses_rest_read_path_only():
    text = WORKFLOW.read_text()
    lower = text.lower()

    assert "workflow_dispatch:" in text
    for trigger in ("push:", "pull_request:", "schedule:", "release:"):
        assert trigger not in text

    assert "DATABASE_URL:" not in text
    assert "SUPABASE_DB_PASSWORD:" not in text
    assert "SUPABASE_USE_POOLER:" not in text
    assert "SUPABASE_URL: ${{ secrets.SUPABASE_URL }}" in text
    assert "SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}" in text
    assert "psycopg2-binary==2.9.9" in text
    assert "scripts/report_delivery_rejection_candidates.py" in text
    assert "--via-rest" in text
    assert "--lookback-hours" in text
    assert "--max-mileage" in text
    assert "set -x" not in lower
