from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "vercel-deploy-gate.yml"


def test_vercel_deploy_gate_workflow_is_dry_run_only():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Vercel Deploy Gate" in text
    assert "pull_request:" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "fetch-depth: 0" in text
    assert "scripts/vercel_deploy_gate.py" in text
    assert "vercel deploy" not in text
    assert "VERCEL_TOKEN" not in text


def test_vercel_deploy_gate_workflow_always_reports_a_decision():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "id: decision" in text
    assert "deploy=${DEPLOY}" in text
    assert "Vercel deploy decision: ${DEPLOY}" in text
