# ACE E1 Resident Supervisor Identity Verdict — 2026-05-07

> **Current-status authority artifact for E1**
> Canonical status remains: **Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**
>
> This artifact records the present-tense verdict for the resident supervisor identity slice after implementation, tests, and live CLI proof.
>
> This artifact does **not** claim V1.
> This artifact does **not** claim daemon/service/platform/runtime-fabric proof.
> This artifact does **not** authorize worker-pool semantics, scheduler control-plane ownership, multi-command governed runtime rollout, or broader runtime-class promotion by rhetoric.

## Verdict

**E1 PASS**

Blunt meaning:
- ACE now has a real resident supervisor identity slice on disk
- that slice is distinct from governed one-shot cycle-run truth
- the repo can now answer from ACE-owned state whether a bounded resident supervisor runtime exists and what its lifecycle state is
- this is real progress
- this is still not V1

## Evidence standard

The verdict is grounded in:
- live repo truth
- live test truth
- live CLI/runtime truth
- authority updates in `ace/README.md`

## Evidence reviewed

### Code surfaces
- `ace/supervisor_runtime.py`
- `ace/storage.py`
- `ace/ace.py`
- `ace/__init__.py`
- `ace/README.md`

### Test surfaces
- `ace/tests/test_supervisor_runtime.py`
- `ace/tests/test_supervisor_cli.py`
- `ace/tests/test_governed_run_runtime.py`
- `ace/tests/test_governed_run_cli.py`
- full ACE test suite under `ace/tests`

### Execution proof
- targeted supervisor/runtime sweep: **15/15 OK**
- full ACE suite: **412/412 OK**
- live CLI proof:
  - `supervisor-run` returned a real `runtime_instance_id`
  - `runtime_status=stopped`
  - `heartbeat_count=1`
  - `duplicate_start=false`
  - `auto_stopped=true`
  - `supervisor-status` returned `inspection_family=resident_supervisor_runtime`
  - `current_runtime_present=false`
  - `last_terminal_runtime_present=true`
  - `cycle-status` on the same DB returned `current_run_present=false` and `last_terminal_run_present=false`

## Section-by-section result

### 1. Distinct resident runtime entrypoint — PASS
Current disk truth:
- `ace/ace.py` exposes `supervisor-run`
- `supervisor-run` is distinct from `cycle`
- runtime identity no longer bottoms out at one-shot governed cycle execution

Why this passes:
- ACE now has a distinct resident supervisor entry surface
- this entry surface owns resident-runtime lifecycle semantics instead of cosmetically wrapping `cycle`

### 2. ACE-owned runtime existence/state persistence — PASS
Current disk truth:
- `ace/storage.py` defines `runtime_instances`
- `ace/supervisor_runtime.py` persists runtime existence and lifecycle state in that ledger
- runtime state is distinct from `governed_runs`

Why this passes:
- ACE-owned persisted state now answers runtime-existence questions directly
- runtime truth no longer collapses into bounded governed-run history

### 3. Operator-readable current-runtime inspection — PASS
Current disk truth:
- `ace/ace.py` exposes `supervisor-status`
- `ace/supervisor_runtime.py` returns `inspection_family=resident_supervisor_runtime`, `current_runtime`, and `last_terminal_runtime`
- inspection can classify stale runtime rows via ACE-owned persisted liveness data

Why this passes:
- operator-visible inspection now reports resident-runtime truth directly
- `supervisor-status` is not interchangeable with `cycle-status`

### 4. Tests proving independent runtime truth — PASS
Current disk truth:
- `ace/tests/test_supervisor_runtime.py` proves runtime-instance lifecycle semantics, duplicate-start behavior, stale classification, explicit failure/stop paths, and independence from `governed_runs`
- `ace/tests/test_supervisor_cli.py` proves CLI/runtime inspection separation from governed-run inspection
- full suite passes with the new surfaces included

Why this passes:
- resident-runtime truth is now test-backed and independent from governed-run rows

## Hard limits that still remain

This verdict does **not** mean:
- V1
- daemon proof
- service/platform proof
- generalized runtime fabric
- worker pool
- scheduler control-plane ownership
- multi-family runtime orchestration
- broad recovery/program completion

Those claims would be false.

## Authority correction

The following artifacts remain useful but are now historical for present-tense E1 truth:
- `reports/ace-next-runtime-e1-audit-verdict-2026-05-06.md`
- `reports/ace-next-runtime-evidence-requirements-2026-05-06.md`
- `reports/ace-supervised-runtime-hidden-evidence-scan-verdict-2026-05-06.md`
- `reports/ace-runtime-class-candidate-single-tenant-supervised-local-runtime-adversarial-verdict-2026-05-06.md`

They describe pre-implementation blocker state.
They do not override live repo + live test + live CLI truth after the landed resident supervisor slice.

## Bottom line

**E1 PASS is real.**

The narrow resident supervisor identity slice is now honest repo truth.
The broader program is still below V1.
The next work must build forward from that truth instead of leaving contradictory authority artifacts in place.
