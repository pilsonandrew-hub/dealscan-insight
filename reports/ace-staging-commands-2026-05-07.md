# ACE Staging Commands — 2026-05-07

These commands implement the governed commit-boundary map without changing scope.
They are not V1 claims. They are hygiene and boundary control for the already-proven bounded E1–E6 seam.

## Group 1 — Doctrine / governance
```bash
git -C /Users/andrewpilson/.openclaw/workspace add \
  .gitignore \
  AGENTS.md \
  MEMORY.md \
  SOUL.md \
  NORTH_STAR.md

git -C /Users/andrewpilson/.openclaw/workspace add -f \
  memory/2026-04-27.md \
  reports/ace-foundation-vs-v1-runtime-decision-memo-2026-04-27.md \
  reports/ace-option-a-governed-foundation-decision-2026-04-27.md \
  reports/ace-current-next-steps.md \
  reports/ace-enterprise-status-verdict-2026-05-05.md \
  reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md \
  reports/ace-phase-truth-matrix-2026-05-05.md \
  reports/ace-e1-resident-supervisor-identity-verdict-2026-05-07.md \
  reports/ace-e2-startup-shutdown-ownership-gate-2026-05-07.md \
  reports/ace-e3-active-runtime-inspection-surface-verdict-2026-05-07.md \
  reports/ace-e4-runtime-failure-recovery-contract-verdict-2026-05-07.md \
  reports/ace-e5-anti-inflation-boundary-proof-verdict-2026-05-07.md \
  reports/ace-e6-distinct-minimal-slice-proof-verdict-2026-05-07.md \
  reports/ace-repo-residue-ledger-2026-05-07.md \
  reports/ace-commit-boundary-map-2026-05-07.md \
  reports/ace-staging-commands-2026-05-07.md
```

## Group 2 — ACE operator / authority surface
```bash
git -C /Users/andrewpilson/.openclaw/workspace add \
  ace/README.md \
  ace/__init__.py \
  ace/ace.py
```

## Group 3 — Runtime / storage / phase logic
```bash
git -C /Users/andrewpilson/.openclaw/workspace add \
  ace/action_runtime.py \
  ace/phase1_closed_loop.py \
  ace/storage.py
```

## Group 4 — Tracked runtime tests
```bash
git -C /Users/andrewpilson/.openclaw/workspace add \
  ace/tests/test_action_runtime.py \
  ace/tests/test_owned_recovery_runtime.py \
  ace/tests/test_phase1_closed_loop.py \
  ace/tests/test_resume_recovery_runtime.py \
  ace/tests/test_resume_runtime.py \
  ace/tests/test_runtime_ownership.py
```

## Group 5 — New bounded seams and seam-specific tests
```bash
git -C /Users/andrewpilson/.openclaw/workspace add \
  ace/briefing.py \
  ace/cycle.py \
  ace/governed_run_runtime.py \
  ace/supervisor_runtime.py \
  ace/sweep.py \
  ace/launchd/ai.superace.cycle.plist \
  ace/launchd/run-ace-cycle.sh \
  ace/tests/test_briefing.py \
  ace/tests/test_cycle.py \
  ace/tests/test_governed_run_cli.py \
  ace/tests/test_governed_run_runtime.py \
  ace/tests/test_supervisor_cli.py \
  ace/tests/test_supervisor_runtime.py \
  ace/tests/test_sweep.py
```

## Group 6 — Hygiene / retirement / archive handling
```bash
git -C /Users/andrewpilson/.openclaw/workspace add ace/.gitignore
git -C /Users/andrewpilson/.openclaw/workspace rm \
  reports/ace-closure-bundle-manifest-2026-04-27.md \
  reports/ace-executive-summary-2026-04-27.md \
  reports/ace-operator-handoff-checklist-2026-04-27.md \
  reports/ace-v1-next-program-correction-2026-04-27.md \
  reports/ace-v1-program1-runtime-breadth-charter-2026-04-27.md \
  reports/ace-v1-program2-operational-authority-charter-2026-04-27.md \
  reports/ace-v1-program3-failure-and-recovery-breadth-charter-2026-04-27.md \
  reports/ace-v1-program4-deployment-runtime-reality-charter-2026-04-27.md \
  reports/ace-v1-roadmap-2026-04-27.md

git -C /Users/andrewpilson/.openclaw/workspace add archives/futureACE.MD
```

## Required verification after staging
```bash
git -C /Users/andrewpilson/.openclaw/workspace diff --cached --stat
git -C /Users/andrewpilson/.openclaw/workspace status --short
python3 -m unittest discover ace/tests
```

## Operability note
Some doctrine/history paths are intentionally ignored in this workspace (`memory/*.md`, `reports/`). Where the map includes those paths, staging must use `git add -f` explicitly. Group 1 is structurally incomplete if the governing report chain is omitted.

## Hard rule
Do not open any post-E6 runtime/governance obligation until the above groups are staged and re-verified as deliberate governed boundaries, the governing report chain is present in Group 1 rather than left local-only, and the next obligation is real on disk without inflation.
