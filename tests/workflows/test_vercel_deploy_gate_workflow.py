from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "vercel-deploy-gate.yml"


def test_vercel_deploy_gate_workflow_has_safe_gate():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "name: Vercel Deploy Gate" in text
    assert "pull_request:" in text
    assert "push:" in text
    assert "branches: [main]" in text
    assert "fetch-depth: 0" in text
    assert "scripts/vercel_deploy_gate.py" in text
    assert "Vercel deploy is controlled by the gate decision" in text


def test_vercel_deploy_gate_workflow_always_reports_a_decision():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "id: decision" in text
    assert "deploy=${DEPLOY}" in text
    assert "Vercel deploy decision: ${DEPLOY}" in text


def test_vercel_deploy_job_is_locked_behind_explicit_repo_variable():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "vercel-deploy:" in text
    assert "needs: gate" in text
    assert "needs.gate.outputs.deploy == 'true'" in text
    assert "vars.ENABLE_GATED_VERCEL_DEPLOY == 'true'" in text
    assert "VERCEL_TOKEN: ${{ secrets.VERCEL_TOKEN }}" in text
    assert "VERCEL_ORG_ID: ${{ secrets.VERCEL_ORG_ID }}" in text
    assert "VERCEL_PROJECT_ID: ${{ secrets.VERCEL_PROJECT_ID }}" in text
    assert "vercel pull --yes" in text
    assert "vercel build" in text
    assert "vercel deploy --prebuilt" in text
