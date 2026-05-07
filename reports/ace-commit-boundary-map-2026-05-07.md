# ACE Commit Boundary Map — 2026-05-07

## Purpose
Turn the current dirty tree into explicit governed commit groups before any bounded E2 implementation begins.

## Governing truth
- ACE is a **governed foundation / Phase 0 continuity substrate**.
- ACE is **not V1**.
- Bounded **E1–E6** are real on the resident supervisor seam.
- The next honest move is only a bounded post-E6 runtime/governance obligation that can be made real on disk without inflation.
- No commit group may imply daemon/platform/service/control-plane/V1 semantics.

## Hard stop before any post-E6 move
Do **not** open any post-E6 runtime/governance obligation until:
1. the dirty tree is partitioned into governed commit groups,
2. the 9 retired 2026-04-27 reports remain deleted,
3. `futureACE.MD` remains archived and non-authoritative,
4. only intentional governed source remains visible in status,
5. current authority continues to say **E1–E6 PASS / not V1 / post-E6 only if real on disk without inflation**.

---

## Group 1 — Doctrine / governance
### Files
- `.gitignore`
- `AGENTS.md`
- `MEMORY.md`
- `SOUL.md`
- `NORTH_STAR.md`
- `memory/2026-04-27.md`
- `reports/ace-foundation-vs-v1-runtime-decision-memo-2026-04-27.md`
- `reports/ace-option-a-governed-foundation-decision-2026-04-27.md`
- `reports/ace-current-next-steps.md`
- `reports/ace-enterprise-status-verdict-2026-05-05.md`
- `reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md`
- `reports/ace-phase-truth-matrix-2026-05-05.md`
- `reports/ace-e1-resident-supervisor-identity-verdict-2026-05-07.md`
- `reports/ace-e2-startup-shutdown-ownership-gate-2026-05-07.md`
- `reports/ace-e3-active-runtime-inspection-surface-verdict-2026-05-07.md`
- `reports/ace-e4-runtime-failure-recovery-contract-verdict-2026-05-07.md`
- `reports/ace-e5-anti-inflation-boundary-proof-verdict-2026-05-07.md`
- `reports/ace-e6-distinct-minimal-slice-proof-verdict-2026-05-07.md`
- `reports/ace-repo-residue-ledger-2026-05-07.md`
- `reports/ace-commit-boundary-map-2026-05-07.md`
- `reports/ace-staging-commands-2026-05-07.md`

### Reason
These files define operator discipline, doctrine, truth hierarchy, memory safety, the current E1–E6 governing truth chain, and the commit-boundary control layer itself. They are intentional governance surfaces, not noise.

### Commit test
This group is valid only if its wording remains:
- governed foundation / not V1
- deterministic artifacts over narration
- no maturity inflation
- no reopening of failed V1/runtime-class branches

---

## Group 2 — ACE operator / authority surface
### Files
- `ace/README.md`
- `ace/__init__.py`
- `ace/ace.py`

### Reason
These are the operator-facing truth surfaces for the bounded ACE runtime: package framing, CLI surface, inspection/status commands, and authoritative seam description.

### Commit test
This group is valid only if it preserves:
- bounded surface claims only
- `supervisor-run`, `supervisor-status`, `cycle-status`, `gate4-inspection`
- no daemon/platform/V1 inflation

---

## Group 3 — Runtime / storage / phase logic
### Files
- `ace/action_runtime.py`
- `ace/phase1_closed_loop.py`
- `ace/storage.py`

### Reason
These are real runtime/storage contract changes: durable notification seam, phase normalization tightening, and storage/runtime ledger surfaces.

### Commit test
This group is valid only if it preserves:
- durable `action_queue` semantics
- bounded failure states
- phase1 loud-failure normalization truth
- storage truth without overstating runtime maturity

---

## Group 4 — Tracked runtime tests
### Files
- `ace/tests/test_action_runtime.py`
- `ace/tests/test_owned_recovery_runtime.py`
- `ace/tests/test_phase1_closed_loop.py`
- `ace/tests/test_resume_recovery_runtime.py`
- `ace/tests/test_resume_runtime.py`
- `ace/tests/test_runtime_ownership.py`

### Reason
These are tracked proof surfaces for the bounded runtime/phase changes already in the tree.

### Commit test
This group is valid only if the tests continue proving bounded seams rather than broad maturity claims.

---

## Group 5 — New bounded seams and new seam-specific tests
### Runtime / operator files
- `ace/briefing.py`
- `ace/cycle.py`
- `ace/governed_run_runtime.py`
- `ace/supervisor_runtime.py`
- `ace/sweep.py`
- `ace/launchd/ai.superace.cycle.plist`
- `ace/launchd/run-ace-cycle.sh`

### Tests
- `ace/tests/test_briefing.py`
- `ace/tests/test_cycle.py`
- `ace/tests/test_governed_run_cli.py`
- `ace/tests/test_governed_run_runtime.py`
- `ace/tests/test_supervisor_cli.py`
- `ace/tests/test_supervisor_runtime.py`
- `ace/tests/test_sweep.py`

### Reason
These are the real newly landed bounded seams: sweep, briefing, governed run lifecycle, supervisor identity, cycle orchestration, launchd scheduling, and direct tests.

### Commit test
This group is valid only if it stays bounded to:
- local-only seam truth
- governed run lifecycle truth
- resident supervisor identity/startup-shutdown/inspection/failure-recovery truth
- anti-inflation boundary proof
- distinct minimal slice proof
- no platform/V1 inflation

---

## Group 6 — Retirement / archive / hygiene
### Files
- `ace/.gitignore`
- deleted retired reports:
  - `reports/ace-closure-bundle-manifest-2026-04-27.md`
  - `reports/ace-executive-summary-2026-04-27.md`
  - `reports/ace-operator-handoff-checklist-2026-04-27.md`
  - `reports/ace-v1-next-program-correction-2026-04-27.md`
  - `reports/ace-v1-program1-runtime-breadth-charter-2026-04-27.md`
  - `reports/ace-v1-program2-operational-authority-charter-2026-04-27.md`
  - `reports/ace-v1-program3-failure-and-recovery-breadth-charter-2026-04-27.md`
  - `reports/ace-v1-program4-deployment-runtime-reality-charter-2026-04-27.md`
  - `reports/ace-v1-roadmap-2026-04-27.md`
- `archives/futureACE.MD`

### Reason
This group preserves hygiene decisions:
- generated briefing state stays ignored
- stale V1/closure/roadmap packaging remains retired
- `futureACE.MD` remains archived scratch, not authority

### Commit test
This group is valid only if:
- the 9 deleted reports stay deleted
- `archives/futureACE.MD` is not promoted back into repo root authority
- ignore rules do not hide real governed source

---

## Files intentionally left visible and unresolved
### Keep visible as doctrine
- `NORTH_STAR.md`

### Why
It is active doctrine, not scratch.

---

## Exact next action sequence
1. Preserve the 9 retired reports as deleted.
2. Preserve `archives/futureACE.MD` as archive-only scratch.
3. Keep `NORTH_STAR.md` visible as doctrine.
4. Use the six commit groups above as the only allowed staging map.
5. Force-stage the governing report chain in Group 1 because `reports/` is ignored locally and local-only authority is not acceptable.
6. After those boundaries are real, assess whether any bounded post-E6 runtime/governance obligation still exists on disk without inflation.

## Post-E6 reminder
Anything broader than the currently proven bounded resident supervisor seam is drift unless it produces a new on-disk obligation with direct evidence and fresh verification.
