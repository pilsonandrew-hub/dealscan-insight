# ACE Repo Residue Ledger — 2026-05-07

## Binary status
- **PASS:** live authority/current-status surfaces now reflect bounded **E1–E6 PASS** on the resident supervisor seam.
- **PASS:** duplicate opening block in `memory/2026-04-27.md` was removed.
- **PASS:** `futureACE.MD` is no longer treated as root authority; archived at `archives/futureACE.MD`.
- **PASS:** noisy local/generated junk was reduced through `.gitignore` and `ace/.gitignore`.
- **FAIL:** the repo is still broadly staged and not yet at an industrial-grade commit boundary split.
- **FAIL:** residue/commit-boundary governance is stale unless it matches the current E1–E6 seam truth exactly.

## Current governing frame
- ACE is a **governed foundation / Phase 0 continuity substrate**.
- ACE is **not V1**.
- Bounded **E1–E6** are real on the resident supervisor seam.
- The next honest move is **only** a bounded post-E6 runtime/governance obligation that can be made real on disk without inflation.
- Do **not** reopen the failed broader current-class ownership/recovery lane.
- Do **not** reopen the failed 2026-05-06 next-runtime-class chain.

## Keep visible as governed doctrine / governance
- `AGENTS.md`
- `MEMORY.md`
- `SOUL.md`
- `NORTH_STAR.md`
- `memory/2026-04-27.md`
- `reports/ace-foundation-vs-v1-runtime-decision-memo-2026-04-27.md`
- `reports/ace-option-a-governed-foundation-decision-2026-04-27.md`

Reason:
These files now encode active doctrine, truth hierarchy, operator rules, and supporting historical decision context. They are not junk.

## Keep visible as governed ACE authority/operator surface
- `ace/README.md`
- `ace/__init__.py`
- `ace/ace.py`

Reason:
These files define the current operator-facing surface and authoritative bounded-runtime framing.

## Keep visible as governed runtime/storage/phase logic
- `ace/action_runtime.py`
- `ace/phase1_closed_loop.py`
- `ace/storage.py`

Reason:
These are core bounded runtime surfaces and supporting storage/phase logic.

## Keep visible as governed tracked tests
- `ace/tests/test_action_runtime.py`
- `ace/tests/test_owned_recovery_runtime.py`
- `ace/tests/test_phase1_closed_loop.py`
- `ace/tests/test_resume_recovery_runtime.py`
- `ace/tests/test_resume_runtime.py`
- `ace/tests/test_runtime_ownership.py`

Reason:
These are substantive proof surfaces for current bounded seams.

## Keep visible as governed new bounded seams and tests
Code / runtime surfaces:
- `ace/briefing.py`
- `ace/cycle.py`
- `ace/governed_run_runtime.py`
- `ace/supervisor_runtime.py`
- `ace/sweep.py`
- `ace/launchd/ai.superace.cycle.plist`
- `ace/launchd/run-ace-cycle.sh`

Tests:
- `ace/tests/test_briefing.py`
- `ace/tests/test_cycle.py`
- `ace/tests/test_governed_run_cli.py`
- `ace/tests/test_governed_run_runtime.py`
- `ace/tests/test_supervisor_cli.py`
- `ace/tests/test_supervisor_runtime.py`
- `ace/tests/test_sweep.py`

Reason:
These are real implementation and proof surfaces for the bounded ACE seams already recognized as substantive.

## Retire and keep deleted
The following deleted files are validated as intentional retirement and should remain deleted:
- `reports/ace-closure-bundle-manifest-2026-04-27.md`
- `reports/ace-executive-summary-2026-04-27.md`
- `reports/ace-operator-handoff-checklist-2026-04-27.md`
- `reports/ace-v1-next-program-correction-2026-04-27.md`
- `reports/ace-v1-program1-runtime-breadth-charter-2026-04-27.md`
- `reports/ace-v1-program2-operational-authority-charter-2026-04-27.md`
- `reports/ace-v1-program3-failure-and-recovery-breadth-charter-2026-04-27.md`
- `reports/ace-v1-program4-deployment-runtime-reality-charter-2026-04-27.md`
- `reports/ace-v1-roadmap-2026-04-27.md`

Reason:
- older V1/closure/roadmap packaging
- stale baselines such as `374 OK`
- no tracked live references found
- superseded by current governed-foundation / hard-gate truth

## Archive, not authority
- `archives/futureACE.MD`

Reason:
Historical scratch/planning only. Not a live authority surface.

## Ignore-only local/generated residue
Already moved out of the status signal path through ignore rules:
- `DREAMS.md`
- `backups/`
- `memory/dreaming/`
- `memory/hot/`
- `tmp/`
- `ace/state/ace_briefing.md`

Reason:
Local/generated residue only. Not governed source.

## Remaining open hygiene fact
The repo is still dirty because the governed files above are not yet separated into explicit commit groups, and the governing report spine under `reports/` must be force-staged into Group 1 rather than left as local-only ignored truth.

## Required next action
Create and execute explicit commit groups:
1. doctrine / governance (including the governing E1–E6 report spine under `reports/`)
2. ACE operator / authority surface
3. runtime / storage / phase logic
4. tracked tests
5. new bounded seams and tests
6. hygiene / retirement / archive handling

## Post-E6 hold line
Do not claim any post-E6 runtime/governance obligation until the visible governed residue is grouped cleanly enough that the repo truth boundary is trustworthy, the governing report chain is present in the staged boundary, and the next obligation is real on disk without inflation.
