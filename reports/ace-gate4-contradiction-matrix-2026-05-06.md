# ACE Gate 4 Contradiction Matrix — 2026-05-06

> **Scope**
> This is the centralized contradiction review surface for currently proven ACE seams.
> It does **not** authorize V1 promotion or broader runtime claims.

## Purpose

The repo already contains bounded contradiction prevention across multiple seams.
The problem is no longer total absence.
The problem is that contradiction truth was scattered across tests and modules.

This matrix centralizes what is already proven, what is only partial, and what remains unproven.

---

## Status legend

- **PREVENTED IN BOUNDED FORM** — contradiction is explicitly blocked in tested bounded cases
- **HEALED IN BOUNDED FORM** — contradiction can arise from interruption ordering, but bounded replay heals it without duplicate or false-success truth
- **PARTIAL** — some bounded proof exists, but family-wide contradiction coverage is incomplete
- **UNPROVEN** — no repo-grounded contradiction proof surfaced yet

---

## Central matrix

| ID | Contradiction class | Primary seam(s) | Status | Repo-grounded basis |
|---|---|---|---|---|
| C1 | Action failed but success evidence exists | action | PREVENTED IN BOUNDED FORM | `ace/tests/test_action_runtime.py` negative paths write no success evidence |
| C2 | Duplicate action execution creates duplicate success evidence | action | PREVENTED IN BOUNDED FORM | `ace/tests/test_action_runtime.py` duplicate execute/non-duplication proofs |
| C3 | Governed run terminal truth violates lifecycle ordering | governed run | PREVENTED IN BOUNDED FORM | `ace/tests/test_governed_run_runtime.py` illegal terminal transition fails loudly |
| C4 | Recovery/session/candidate refer to different items but finalize still succeeds | recovery / ownership | PREVENTED IN BOUNDED FORM | `ace/tests/test_owned_recovery_runtime.py` mismatch rejection with zero evidence |
| C5 | Stale/missing recovery target still lands success artifacts | recovery / ownership | PREVENTED IN BOUNDED FORM | `test_resume_recovery_runtime.py`, `test_owned_recovery_runtime.py`, `test_runtime_ownership.py` stale-target failures with zero evidence |
| C6 | Interrupted split-success duplicates evidence on replay | recovery / ownership | HEALED IN BOUNDED FORM | `test_owned_recovery_runtime.py`, `test_runtime_ownership.py` interrupted success healing proofs |
| C7 | Session silently switches to another candidate | recovery | PREVENTED IN BOUNDED FORM | `test_resume_recovery_runtime.py` different-candidate reselection rejected |
| C8 | Malformed persisted ownership payload still releases successfully | ownership | PREVENTED IN BOUNDED FORM | `test_runtime_ownership.py` malformed payload => failed/no evidence |
| C9 | Invalid ingest input still creates downstream item truth | ingest | PREVENTED IN BOUNDED FORM | `test_open_loop_ingest.py`, `test_pending_promotions_ingest.py` malformed/schema-invalid zero-write rejection |
| C10 | Closed-loop malformed input still creates decision evidence | decision | PREVENTED IN BOUNDED FORM | `test_phase1_closed_loop.py`, `test_phase1b_closed_loop.py` malformed/schema-invalid zero-write rejection |
| C11 | Closed-loop replay duplicates decision evidence | decision | PREVENTED IN BOUNDED FORM | `test_phase1_closed_loop.py`, `test_phase1b_closed_loop.py` replay-safe decision evidence reuse |
| C12 | Continuity source file is mutated during closed-loop run | decision / source boundary | PREVENTED IN BOUNDED FORM | Phase1 / Phase1B tests guard write/unlink/rename/replace and verify unchanged source |
| C13 | Sweep re-emits unchanged stale finding as fresh contradiction-free signal | sweep | PREVENTED IN BOUNDED FORM | `test_sweep.py` duplicate suppression when fingerprint unchanged |
| C14 | Sweep suppresses changed item activity and leaves stale contradiction truth | sweep | PREVENTED IN BOUNDED FORM | `test_sweep.py` re-emission on activity/evidence change |
| C15 | Sweep with zero findings omits durable summary truth | sweep | PREVENTED IN BOUNDED FORM | `test_sweep.py` summary event still written with zero findings |
| C16 | Briefing duplicates stale triage into needs_decision | briefing | PREVENTED IN BOUNDED FORM | `test_briefing.py` stale triage excluded from `needs_decision` |
| C17 | Briefing diverges from live DB truth for blocked/claimed_done/triage sections | briefing | PREVENTED IN BOUNDED FORM | `test_briefing.py` live DB classification expectations |
| C18 | Briefing render output is non-deterministic or omits inspection markers | briefing | PREVENTED IN BOUNDED FORM | `test_briefing.py` deterministic render assertions |

---

## Partial areas that remain

### P1. Decision contradiction breadth beyond invalid-input rejection
What is proven:
- malformed/schema-invalid closed-loop input does not emit decision evidence
- replay does not duplicate decision evidence
- continuity source boundary is read-only during run

What remains partial:
- broader contradiction classes around decision ambiguity are not yet organized as one family
- especially for softer Phase 1 source-row skipping behavior versus explicit typed rejection paths

### P2. Recovery contradiction breadth is real but still uneven
What is proven:
- mismatch rejection
- stale-target failure
- replay-safe dismissal
- interrupted split-heal
- malformed payload rejection

What remains partial:
- one centralized governed distinction among success / no-op replay / failed / healed states across the whole recovery family

### P3. Operator-facing contradiction inspection is still narrow
What is proven:
- contradiction prevention exists in tests and persistent rows/events/evidence

What remains partial:
- no single operator-facing inspection surface summarizes contradiction state family-wide without code/test archaeology

---

## Honest next contradiction work

1. **Recovery contradiction breadth first**
   - unify success/no-op/failure/healed distinctions across recovery, ownership, session, and candidate seams
2. **Decision contradiction breadth second**
   - inventory ambiguity and soft-skip contradiction classes around Phase 1 source-row loading
3. **Inspection surface third**
   - produce a bounded operator-facing contradiction inspection artifact

---

## What would count as real next progress

- one recovery contradiction sub-matrix distinguishing proven / bounded / missing classes
- one decision contradiction addendum covering ambiguity and soft-skip behavior
- one inspection artifact that lets a reviewer trace contradiction truth without test-file archaeology
- new tests only where a contradiction family is genuinely not already proven

## What would not count

Do not count any of the following by themselves:
- generic “consistency” language
- more logs without contradiction-state proof
- duplicating already-proven replay-safe tests
- renaming statuses without reducing contradiction risk
- claiming broad Gate 4 maturity from bounded seam wins alone

---

## Bottom line

Contradiction control is already broader than the earlier draft implied.
It is not just action/governed-run/recovery anymore.
It also exists in bounded ingest, decision, sweep, and briefing seams.

What is still missing is not raw proof existence.
What is still missing is:
- breadth where contradiction families are still under-classified,
- centralization of what is already proven,
- and an operator-facing inspection surface.
