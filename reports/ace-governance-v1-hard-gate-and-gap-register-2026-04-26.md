# ACE V1 Hard Gate and Gap Register — 2026-04-26

> **Primary current-status authority**
> Canonical status: **Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**
> This document is a live blocker/gate authority and should be read together with `ace/README.md`, `reports/ace-enterprise-status-verdict-2026-05-05.md`, and `reports/ace-phase-truth-matrix-2026-05-05.md`.

## Current truthful label

**Super A.C.E. is not yet V1.**

Current honest boundary:

- **Governed Foundation / Phase 0**
- **two narrow local-only Phase 1 closed-loop proofs**
- **two narrow local-only Phase 2 action-runtime proofs**
- **two narrow local-only Phase 3 resume/recovery proofs**
- **two narrow local-only Phase 4 runtime-ownership proofs**
- **one narrow local-only Phase 7A cross-seam owned-recovery lifecycle proof**
- **one narrow local-only Phase 9A ownership interruption replay-durability proof**
- **one narrow local-only Phase 9B recovery interruption replay-durability proof**
- **one narrow local-only Phase 11 owned-recovery cross-surface interrupted-success ordering proof**
- **one narrow local-only E1 resident supervisor identity proof**
- **one narrow local-only E2 startup/shutdown ownership proof on that same resident supervisor seam**
- **one narrow local-only E3 active runtime inspection proof on that same resident supervisor seam**
- **one narrow local-only E4 runtime failure/recovery contract proof on that same resident supervisor seam**
- **one narrow local-only E5 anti-inflation boundary proof on that same resident supervisor seam**
- **one narrow local-only E6 distinct minimal slice proof on that same resident supervisor seam**
- **main-repo validation at 422 tests OK**

This is meaningful progress, but it is **not** yet a full ACE V1 runtime.

## What is actually proven now

1. Governed git baseline and coherent local commit history.
2. SQLite-backed ACE substrate with explicit workflow and closeout gate behavior.
3. Read-only ingest proof for `continuity/open-loops.json`.
4. Read-only ingest proof for `continuity/pending-promotions.json`.
5. Bounded Phase 1 decision proof on pending-promotions.
6. Bounded Phase 1B decision proof on open-loops.
7. Bounded Phase 2 action-runtime proof for `record_operator_followup`.
8. Bounded Phase 2B action-runtime proof for `record_operator_rejection`.
9. Bounded Phase 3 resume/recovery proof using `sessions` and `resume_candidates`.
10. Bounded Phase 3B recovery proof using the same seam for deterministic select/dismiss behavior.
11. Bounded Phase 4 runtime-ownership proof using the existing `action_queue` seam for deterministic ownership registration, claim/release semantics, and replay-safe local outcome evidence.
12. Bounded Phase 4B runtime-ownership proof on the same seam for durable explicit malformed-payload release failure with no success artifacting and replay-safe failed-row inspection.
13. Bounded Phase 9A ownership interruption replay-durability proof showing replay heals an interrupted success-artifact / terminal-state split without duplicate evidence or false terminal claims.
14. Bounded Phase 9B recovery interruption replay-durability proof showing replay heals an interrupted success-artifact / terminal-state split on the newer recovery seam without duplicate evidence or false terminal claims.
15. Bounded Phase 11 owned-recovery cross-surface interrupted-success ordering proof showing replay heals the mixed durable state where recovery is already terminal-success while ownership is still only claimed, without duplicate evidence or contradictory cross-surface terminal claims.
16. Bounded E1 resident supervisor identity proof with a distinct `runtime_instances` ledger, `supervisor-run`, `supervisor-status`, explicit `starting|live|stale|stopped|failed` lifecycle truth, and inspection independent from governed one-shot cycle runs.
17. Bounded E2 startup/shutdown ownership proof on that same resident supervisor seam with explicit `startup_status`, `shutdown_status`, `failure_phase`, and lifecycle timestamps surfaced through supervisor inspection and proved by targeted tests.
18. Bounded E3 active runtime inspection proof on that same resident supervisor seam with append-only resident runtime transition history surfaced through supervisor inspection and proved independently from governed-run history.
19. Bounded E4 runtime failure/recovery contract proof on that same resident supervisor seam with ACE-owned recovery request/result truth and append-only recovery history surfaced through supervisor inspection distinctly from governed-run failure/interruption.
20. Bounded E5 anti-inflation boundary proof on that same resident supervisor seam with explicit bounded runtime claims and explicit anti-inflation non-claims surfaced directly through supervised-runtime inspection.
21. Bounded E6 distinct minimal slice proof on that same resident supervisor seam with explicit slice definition, exact E1–E5 artifact bundle, and non-reduction proof surfaced directly through supervised-runtime inspection.
22. Informational coverage measurement in CI and passing main suite at **422 tests OK**.

## Hard V1 gate

ACE may only be called **V1** when **all** items below are pass, not “mostly pass.”

### Gate 1 — Closed-loop breadth

Required:
- At least **3 materially distinct** bounded closed loops proven end-to-end.
- At least **2 materially distinct** bounded action-runtime lifecycles proven end-to-end.
- At least **2 materially distinct** bounded recovery outcomes proven end-to-end.

Current status: **FAIL**

Why:
- Decision breadth exists, but overall loop breadth is still narrow and local.
- Action runtime has only two operator-facing bounded lifecycles.
- Recovery breadth is still limited even after the landed Phase 3 and Phase 3B proofs.

### Gate 2 — Runtime ownership truth

Required:
- ACE-owned runtime contract must be explicit for queueing, claiming, completion, failure, replay, and inspection.
- Boundaries between schema, runtime, and recovery semantics must be documented and enforced.
- No reliance on “table exists” as runtime proof.

Current status: **PARTIAL / FAIL for V1**

Why:
- Some runtime ownership is now real in bounded seams, including the landed Phase 4 and Phase 4B proofs.
- Broader runtime ownership model is still not established.

### Gate 3 — Resume/recovery trust

Required:
- Resume lifecycle must cover more than one bounded terminal outcome.
- Recovery must demonstrate deterministic replay, explicit stale-state handling, and safe no-duplicate-side-effect behavior across multiple meaningful recovery branches.

Current status: **FAIL**

Why:
- Two bounded Phase 3 recovery proofs are real.
- Broader recovery breadth/trust is still not proven.

### Gate 4 — Failure discipline

Required:
- Failure behavior must be explicit, inspectable, and tested across ingest, decision, action, and recovery seams.
- Failure paths must prove zero false-success artifacting and bounded persistent state transitions.

Current status: **PARTIAL / FAIL for V1**

Why:
- Bounded failure paths exist in current proofs.
- Whole-system failure discipline is still not broad enough for a V1 claim.

### Gate 5 — Operational runtime model

Required:
- Explicit statement and proof of how ACE is meant to run operationally.
- Startup/shutdown/inspection expectations must be real, not implied.
- Ownership of runtime state, invocation mode, and observability surfaces must be defined.

Current status: **PARTIAL / FAIL for V1**

Why:
- A canonical Phase 5 operational runtime model now exists and improves governance truth materially.
- The narrow E1 resident supervisor identity slice is real and materially improves runtime truth.
- The narrow E2 startup/shutdown ownership slice is now also real on that same resident supervisor seam.
- The narrow E3 active runtime inspection slice is now also real on that same seam through append-only transition history plus operator-visible inspection distinct from governed-run history.
- The narrow E4 runtime failure/recovery contract slice is now also real on that same seam through ACE-owned recovery request/result truth plus append-only recovery history distinct from governed-run failure/interruption.
- It still does not establish broader daemon/service/platform semantics or a full operational runtime model sufficient for a V1 claim.

### Gate 6 — Confidence discipline

Required:
- Contract tests, proof tests, and full suite remain green.
- Coverage remains honest and informative, not gamed.
- Confidence bar must be defined by proof classes, not just raw test count.

Current status: **PARTIAL / FAIL for V1**

Why:
- Current confidence is materially stronger than earlier phases.
- It is still not a sufficient V1 promotion regime on its own.

### Gate 7 — Write authority model

Required:
- Any write authority beyond ACE-owned local tables/evidence must be explicitly scoped, tested, and recoverable.
- Continuity-source mutation authority must be either still out of scope or deliberately proven with safeguards.

Current status: **FAIL**

Why:
- Current truthful posture is still no continuity-source write authority.
- V1 does not strictly require broad write authority, but if claimed, it must be proven. That proof does not exist.

### Gate 8 — Release/operational packaging truth

Required:
- Packaging, install, CI, and runtime expectations must align with the V1 claim.
- Naming/metadata/doctrine must not outrun runtime truth.

Current status: **PARTIAL**

Why:
- Package/readme/CI truth is much cleaner now.
- Full V1 operational packaging/release posture is still not proven.

## Brutally honest current verdict

If the question is:

### “Is ACE V1 right now?”
**Answer: NO.**

### “Is ACE meaningfully real and beyond foundation theater?”
**Answer: YES.**

### “What is the strongest honest label right now?”
**Governed Foundation / Phase 0 with two narrow local-only Phase 1 proofs, two narrow local-only Phase 2 action-runtime proofs, two narrow local-only Phase 3 resume/recovery proofs, two narrow local-only Phase 4 runtime-ownership proofs, one narrow local-only Phase 7A cross-seam owned-recovery lifecycle proof, one narrow local-only Phase 9A ownership interruption replay-durability proof, one narrow local-only Phase 9B recovery interruption replay-durability proof, and one narrow local-only Phase 11 owned-recovery cross-surface interrupted-success ordering proof.**

## Highest-leverage next move

If we deliberately continue, the prior ownership/recovery breadth lane must now be treated as **tested and blocked on the current local runtime class**.

What is now true:
- the broader runtime ownership/recovery breadth program was the correct next test lane after activation-first closure
- it was taken through distinctness review, survivor spec, and final go/block verdict on the then-current validation baseline + activation-first-closed surface
- the only plausible candidate still collapsed into the already-landed ownership/recovery/replay family
- no materially distinct connected ownership+recovery lifecycle survives on the current local runtime class

Therefore the highest-leverage next move is no longer “open that lane.”
The highest-leverage next move is:

### **advance from the landed bounded E6 distinct minimal slice proof slice only if another bounded runtime obligation can still be made real on disk without inflation**

Why this is now highest leverage:
- the repo now has distinct resident supervisor identity truth, bounded startup/shutdown ownership truth, bounded active runtime inspection truth, bounded runtime failure/recovery contract truth, bounded anti-inflation boundary proof, and bounded distinct minimal slice proof on that same seam
- the next unresolved runtime-class obligation is no longer whether E6 is real, but whether any post-E6 runtime obligation can still be made real without inflation
- reopening the blocked ownership/recovery lane would still be fake motion
- packaging or doctrine-first motion would still be theater

## What would count as counterfeit progress from here

Do **not** claim V1 by doing any of the following alone:
- raising raw test count
- adding one more tiny local-only doc fix
- renaming existing bounded proofs as broader maturity
- treating schema presence as runtime proof
- broadening doctrine language without runtime evidence

## Promotion rule

Until every hard gate above is pass, ACE must not be called V1 in governed surfaces.
