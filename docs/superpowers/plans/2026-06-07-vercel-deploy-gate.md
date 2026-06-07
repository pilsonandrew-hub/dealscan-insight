# Vercel Deploy Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop backend/proof/report-only changes from burning Vercel preview deployment quota while keeping Vercel available for frontend-impacting changes.

**Architecture:** Add a repo-owned Python path classifier with tests, then add a GitHub Actions check that always reports the Vercel decision. The workflow includes the future Vercel CLI deployment lane, but locks it behind `ENABLE_GATED_VERCEL_DEPLOY=true` so it cannot replace native Vercel until secrets and branch protection are deliberately switched over.

**Tech Stack:** Python, pytest, GitHub Actions, Vercel CLI later.

---

### Task 1: Path Classifier

**Files:**
- Create: `scripts/vercel_deploy_gate.py`
- Create: `tests/test_vercel_deploy_gate.py`

- [ ] Write tests for deploy paths: `src/**`, `public/**`, `index.html`, package/lock files, Vite/Tailwind/PostCSS/TypeScript config, Vercel config, `.vercelignore`, deployment workflow/script files, and unknown root files.
- [ ] Write tests for skip paths: `docs/**`, `reports/**`, normal `scripts/**`, `tests/**`, normal `.github/workflows/**`, backend/proof/data/evidence paths.
- [ ] Implement `should_deploy_for_paths(paths)` as fail-open: empty/unknown/ambiguous root-level input deploys.
- [ ] Add CLI modes: `--files` for tests/dry-run and `--base/--head` for GitHub Actions diffing.
- [ ] Verify focused tests pass.

### Task 2: Gate Workflow

**Files:**
- Create: `.github/workflows/vercel-deploy-gate.yml`
- Create: `tests/workflows/test_vercel_deploy_gate_workflow.py`

- [ ] Write workflow contract tests: always runs on PR and main push, uses `fetch-depth: 0`, runs the classifier, exposes decision output, does not invoke Vercel CLI yet.
- [ ] Add workflow with a single always-green gate job that logs `deploy=true/false`.
- [ ] Add a Vercel CLI deploy job locked behind `ENABLE_GATED_VERCEL_DEPLOY=true` and `deploy=true`.
- [ ] Verify workflow tests pass.

### Task 3: Verification

- [ ] Run focused tests for classifier/workflow.
- [ ] Run `python3 -m py_compile scripts/vercel_deploy_gate.py`.
- [ ] Run `git diff --check`.
- [ ] Report branch and exact verification status to Andrew.

### Explicit Non-Goals For This PR

- Do not set `git.deploymentEnabled: false` yet.
- Do not add Vercel secrets directly in this PR.
- Do not enable the Vercel CLI deploy job yet.
- Do not update branch protection yet.
