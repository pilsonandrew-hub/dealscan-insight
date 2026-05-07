# ACE E2 Startup/Shutdown Ownership Gate — 2026-05-07

> **Current gating artifact for the next bounded runtime step**
> Canonical status remains: **Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**
>
> This gate opens only because **E1 resident supervisor identity now passes**.
> It does **not** imply V1.
> It does **not** authorize daemon/service/platform inflation.
>
> Governing upstream authorities:
> - `ace/README.md`
> - `reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md`
> - `reports/ace-enterprise-status-verdict-2026-05-05.md`
> - `reports/ace-phase-truth-matrix-2026-05-05.md`
> - `reports/ace-e1-resident-supervisor-identity-verdict-2026-05-07.md`
> - `reports/ace-next-runtime-evidence-execution-order-2026-05-06.md`

## Binary purpose

This artifact defines the next bounded gate after E1:

**Can ACE own startup and shutdown truth for the resident supervisor slice in its own durable state?**

If not, the runtime-class advance stops here.

## Current status

**E2 PASS — bounded resident supervisor startup/shutdown ownership is now real on disk.**

Blunt meaning:
- ACE now owns explicit startup truth for the resident supervisor slice in durable state
- ACE now owns explicit shutdown request/completion truth for the resident supervisor slice in durable state
- ACE now records explicit startup/runtime/shutdown failure-phase truth
- `supervisor-status` now exposes that lifecycle truth from ACE-owned state
- this is real bounded runtime progress
- this is still not V1

## Evidence now on disk

The resident supervisor slice now proves all bounded E2 requirements:
- explicit startup ownership persisted in `runtime_instances`
- explicit shutdown request/completion ownership persisted in `runtime_instances`
- explicit startup/runtime/shutdown failure-phase truth persisted in `runtime_instances`
- inspectable lifecycle truth exposed through `supervisor-status`
- targeted supervisor/runtime tests green
- full ACE suite green on the exact staged tree

What still does **not** exist:
- V1
- daemon/service/platform proof
- generalized runtime fabric
- worker-pool semantics
- scheduler control-plane ownership
- broad restart/recovery runtime-class completion

## Exact pass result

E2 now passes because all bounded requirements are true on disk and in tests:

1. **Startup ownership is explicit**
   - ACE persists explicit startup truth through `startup_status` and `startup_completed_at`.

2. **Shutdown ownership is explicit**
   - ACE persists explicit shutdown truth through `shutdown_status`, `shutdown_requested_at`, and `shutdown_completed_at`.

3. **Failure phase truth is explicit**
   - ACE persists `failure_phase` with bounded values `startup`, `runtime`, and `shutdown`.

4. **Inspection reflects startup/shutdown truth**
   - `supervisor-status` exposes the richer lifecycle fields directly from ACE-owned state.

5. **Tests prove the contract directly**
   - targeted supervisor runtime + CLI slice passes at **13/13 OK**
   - full ACE suite passes at **417/417 OK** on the exact staged tree

## Immediate non-claims

Even if E2 passes, it still does **not** mean:
- V1
- daemon proof
- platform/service proof
- worker-pool semantics
- scheduler control-plane ownership
- multi-command governed runtime rollout
- generalized runtime fabric
- continuity-source write authority

Those claims remain forbidden unless separately proven.

## Minimum implementation targets

Acceptable implementation work for E2 is bounded to the resident supervisor slice.

Examples of acceptable target classes:
- explicit startup transition persistence semantics
- explicit shutdown transition persistence semantics
- bounded degraded startup/shutdown state handling
- targeted status-surface expansion for those states
- targeted tests proving those states and transitions

Examples of unacceptable fake progress:
- README-only changes
- report-only changes
- launchd-only changes
- test-count growth without new runtime truth
- rewording E1 as if it already included startup/shutdown ownership
- broad V1 or service-language expansion

## Kill conditions

Kill E2 immediately if implementation collapses back into any of these:
- launchd is still the only startup/shutdown truth source
- shutdown truth is only “row disappeared”
- startup truth is only “process exists”
- degraded startup/shutdown is uninspectable
- governed-run history is reused as the startup/shutdown ledger under a different name

## Evidence bundle for E2 PASS

Implemented surfaces:
- `ace/supervisor_runtime.py`
- `ace/storage.py`
- `ace/__init__.py`
- `ace/tests/test_supervisor_runtime.py`
- `ace/tests/test_supervisor_cli.py`

Verification:
- `python3 -m unittest ace.tests.test_supervisor_runtime ace.tests.test_supervisor_cli` -> **13/13 OK**
- `python3 -m unittest discover ace/tests` -> **417/417 OK**
- staged-tree re-verification -> **417/417 OK**

## Bottom line

E1 is real.
E2 is now also real for the bounded resident supervisor slice.

**E2 PASS is honest repo truth for bounded startup/shutdown ownership on the resident supervisor seam.**

The next work must move forward from that truth without inflating it into V1 or broader platform/runtime-class claims.
