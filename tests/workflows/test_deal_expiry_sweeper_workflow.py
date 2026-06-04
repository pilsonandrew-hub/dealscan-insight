from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "deal-expiry-sweeper.yml"


def test_deal_expiry_sweeper_workflow_uses_tested_script():
    text = WORKFLOW.read_text()
    lower = text.lower()

    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert "dry_run:" in text
    assert 'DEAL_EXPIRY_SWEEPER_DRY_RUN: ${{ github.event_name == ' in text
    for trigger in ("push:", "pull_request:", "release:"):
        assert trigger not in text

    assert "timeout-minutes: 10" in text
    assert "contents: read" in text
    assert "git config --global init.defaultBranch main" in text
    assert "uses: actions/checkout@v6" in text
    assert "python3 scripts/deal_expiry_sweeper.py" in text
    assert "python3 -m pip install --disable-pip-version-check --no-cache-dir supabase==2.30.0" in text
    assert "SUPABASE_SERVICE_ROLE_KEY" in text
    assert "TELEGRAM_BOT_TOKEN" in text
    assert "DATABASE_URL:" not in text
    assert "SUPABASE_DB_PASSWORD:" not in text
    assert "SUPABASE_USE_POOLER:" not in text
    assert "from public.opportunities" not in lower
    assert "update public.opportunities" not in lower
    assert "set -x" not in lower
