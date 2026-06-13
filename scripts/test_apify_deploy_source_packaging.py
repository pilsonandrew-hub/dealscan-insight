#!/usr/bin/env python3
"""Regression guard for Apify deploy source packaging.

The GitHub deploy workflow must include every first-level JS module under each
actor's src/ directory. If it only uploads hand-picked files, helper imports can
build green but fail at Apify runtime.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "apify-deploy.yml"


def test_apify_deploy_uploads_all_first_level_src_js_modules() -> None:
    workflow = WORKFLOW.read_text()

    assert 'Path(src_dir, "src").glob("*.js")' in workflow
    assert 'actor_source_name = f"src/{src_file.name}"' in workflow

    # Historical failure mode: runtime_budget.js was imported by main_api.js but
    # omitted by a fixed allow-list, causing Apify runtime ERR_MODULE_NOT_FOUND.
    assert 'for extra in ["src/main_api.js", "src/utils.js", "src/helpers.js"]' not in workflow


def test_apify_deploy_fails_closed_on_apify_api_errors() -> None:
    workflow = WORKFLOW.read_text()

    assert "raise RuntimeError(f\"Apify API {method} {path} failed" in workflow
    assert "return {}" not in workflow
    assert "raise RuntimeError(f\"Upload failed for {actor_dir}" in workflow
    assert "raise RuntimeError(f\"Build trigger failed for {actor_dir}" in workflow
    assert 'build_id = build.get("data", {}).get("id")' in workflow
    assert 'build_id = build.get("data", {}).get("id", "?")' not in workflow
    assert "failures = []" in workflow
    assert "failures.append(failure)" in workflow
    assert "Apify actor deployment failed for {len(failures)} actor(s)" in workflow
    assert "Deploy complete" in workflow


def test_apify_deploy_does_not_keep_dead_main_js_read() -> None:
    workflow = WORKFLOW.read_text()

    assert "main_js = open" not in workflow
