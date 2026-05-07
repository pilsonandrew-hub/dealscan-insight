# ACE E4 Runtime Failure/Recovery Contract Verdict — 2026-05-07

## Scope

This artifact governs only the **bounded resident supervisor seam** in `ace/supervisor_runtime.py`.
It does **not** justify V1, daemon/service/platform semantics, generalized runtime fabric, worker-pool/control-plane ownership, or broader runtime-class promotion.

## Verdict

> **E4 PASS for the bounded resident supervisor seam.**

ACE now owns explicit resident-runtime failure truth **and** ACE-owned recovery/restart attempt/result truth on disk for the resident supervisor seam, distinctly from governed one-shot run failure/interruption.

## What E4 now honestly proves

On the bounded resident supervisor seam only, ACE now has:

- explicit resident-runtime failure states on disk
- explicit failure phase truth (`startup`, `runtime`, `shutdown`)
- explicit ACE-owned recovery request truth on disk
- explicit ACE-owned recovery completion/failure result truth on disk
- append-only recovery event history on the same resident supervisor ledger
- operator-visible inspection of that recovery history through `supervisor-status`
- explicit distinction from governed one-shot `cycle` / `governed_runs` failure-interruption semantics

## Evidence on disk

### Code

- `ace/supervisor_runtime.py`
- `ace/storage.py`
- `ace/ace.py`
- `ace/__init__.py`

### Tests

- `ace/tests/test_supervisor_runtime.py`
- `ace/tests/test_supervisor_cli.py`

### Verification

- targeted bounded supervisor slice: **18/18 OK**
- current live suite: **422/422 OK**
- staged-tree/main-tree verification rerun: **422/422 OK**

## What this still does not prove

E4 on this seam does **not** prove:

- V1 runtime breadth
- daemon/service/platform semantics
- generalized recovery across all ACE runtime families
- worker-pool or scheduler control-plane ownership
- continuity-source write authority
- broad production/runtime rollout truth

## Next honest gate

Because E4 is now real on disk for the bounded resident supervisor seam, the next honest runtime obligation is **E5 anti-inflation boundary proof**, still bounded and evidence-first per the execution-order artifact.

## Short verdict

**E1 PASS, E2 PASS, E3 PASS, E4 PASS on the bounded resident supervisor seam. ACE is still not V1. The next honest runtime gate is E5.**
