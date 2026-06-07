from scripts.vercel_deploy_gate import should_deploy_for_paths


def test_deploys_for_frontend_source_paths():
    assert should_deploy_for_paths(["src/App.tsx"]) is True
    assert should_deploy_for_paths(["public/favicon.ico"]) is True
    assert should_deploy_for_paths(["index.html"]) is True


def test_deploys_for_frontend_build_and_dependency_config():
    deploy_paths = [
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "bun.lockb",
        "vite.config.ts",
        "tsconfig.json",
        "tsconfig.app.json",
        "tailwind.config.ts",
        "postcss.config.js",
        "components.json",
        ".npmrc",
    ]

    for path in deploy_paths:
        assert should_deploy_for_paths([path]) is True, path


def test_deploys_for_vercel_and_gate_config():
    assert should_deploy_for_paths(["vercel.json"]) is True
    assert should_deploy_for_paths([".vercelignore"]) is True
    assert should_deploy_for_paths([".github/workflows/vercel-deploy-gate.yml"]) is True
    assert should_deploy_for_paths(["scripts/vercel_deploy_gate.py"]) is True


def test_deploys_for_mixed_frontend_and_non_frontend_changes():
    assert should_deploy_for_paths(["docs/note.md", "src/App.tsx"]) is True


def test_skips_for_backend_proof_report_and_docs_only_changes():
    skip_paths = [
        "docs/ops.md",
        "reports/external-comp-evidence-proxibid-hyundai-venue-suv-2026-06-07.json",
        "scripts/report_source_yield_proof.py",
        "tests/test_source_yield_proof.py",
        ".github/workflows/source-yield-proof.yml",
        "backend/ingest/score.py",
        "apify/actors/ds-proxibid/main.js",
        "supabase/migrations/20260607_example.sql",
        "requirements.txt",
        "pytest.ini",
    ]

    assert should_deploy_for_paths(skip_paths) is False


def test_deploys_for_unknown_root_level_paths_as_fail_open():
    assert should_deploy_for_paths(["new-root-config.toml"]) is True


def test_deploys_when_path_list_is_empty_or_unknown():
    assert should_deploy_for_paths([]) is True
