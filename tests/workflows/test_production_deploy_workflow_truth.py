from pathlib import Path
import re

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "production-deploy.yml"
TEXT = WORKFLOW.read_text()
LOWER = TEXT.lower()

FORBIDDEN_PHRASES = [
    "deploy-staging",
    "deploy-production",
    "rollback",
    "environment: production",
    "environment: staging",
    "add your production deployment commands here",
    "add your staging deployment commands here",
    "deployed to staging",
    "deployment rolled back",
    "url: https://dealerscope.com",
    "supabase_access_token",
    "supabase_project_id",
    "actions: write",
]


def test_legacy_workflow_is_explicitly_non_authoritative():
    assert "no deployment" in LOWER
    assert "not deploy proof" in LOWER or "not deployment proof" in LOWER
    assert "non-authoritative" in LOWER


def test_legacy_workflow_cannot_use_deploy_authority_semantics():
    assert "environment:" not in LOWER
    for phrase in FORBIDDEN_PHRASES:
        assert phrase not in LOWER


def test_legacy_workflow_does_not_claim_production_deployment():
    misleading_patterns = [
        r"production deploy(?:ment)? (?:completed|succeeded|passed)",
        r"deploy(?:ed|ment) to production",
        r"running legacy production deploy",
        r"staging deploy placeholder",
        r"production deploy placeholder",
    ]
    for pattern in misleading_patterns:
        assert not re.search(pattern, LOWER)


def test_legacy_workflow_keeps_manual_trigger_only():
    assert "workflow_dispatch:" in TEXT
    for trigger in ("push:", "pull_request:", "release:", "schedule:"):
        assert trigger not in TEXT


def test_authoritative_deploy_evidence_is_named_elsewhere_not_here():
    assert "railway and vercel commit statuses" in LOWER
    assert "purpose-built live validation workflows" in LOWER


def test_production_readiness_doc_demotes_legacy_workflow():
    doc = (Path(__file__).resolve().parents[2] / "docs" / "PRODUCTION_READINESS.md").read_text().lower()
    assert "production-deploy.yml" in doc
    assert "non-authoritative" in doc
    assert "must not be cited as production deploy proof" in doc
    assert "railway and vercel commit statuses" in doc


def test_legacy_workflow_has_no_deployment_secrets_or_tokens():
    forbidden_secret_refs = [
        "secrets.",
        "supabase_access_token",
        "supabase_project_id",
        "railway_token",
        "vercel_token",
        "deploy_token",
        "production_api_key",
        "staging_api_key",
    ]
    for phrase in forbidden_secret_refs:
        assert phrase not in LOWER
