# ACE phase truth matrix — 2026-05-05

> **Primary current-status authority**
> Canonical status: **Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**
> This matrix is an authority artifact for implemented-vs-specified-vs-blocked phase truth and should be read together with `ace/README.md`, `reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md`, and `reports/ace-enterprise-status-verdict-2026-05-05.md`.

## Governing verdict

**ACE is not V1.**

Current strongest evidence-safe classification:

**Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**

This matrix exists to kill ambiguity.
It separates:
- implemented and verified
- specified but not implemented
- blocked / not justified
- structural guidance only

---

## Authority order

When sources conflict, trust them in this order:
1. live repo truth + live test truth
2. `ace/README.md`
3. `reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md`
4. `reports/ace-historical-post-baseline-scorecard-2026-04-25.md`
5. daily memory logs for phase history and decision chronology
6. older planning/spec docs

---

## Pre-phase foundation proofs

### Governed baseline
- Status: **IMPLEMENTED / VERIFIED**
- Evidence: verified commit `f354c41416edcfc02bb116c5fce9981565ae7ae9`
- Meaning: governed baseline adopted in real repo history

### Open-loops read-only ingest proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - memory 2026-04-25
  - commit `09f849c7a25aac149e1eafdc218ba64f632fe96f`
  - targeted tests green
  - full suite at 263 green at that checkpoint
- Meaning: `continuity/open-loops.json` read-only ingest into ACE `TRIAGE` is real

### Pending-promotions read-only ingest proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - memory 2026-04-25
  - commit `c2ea3e9d26a5ac58cd5af7dd1042f67e4ccd7b5d`
  - targeted tests green
  - full suite at 267 green at that checkpoint
- Meaning: `continuity/pending-promotions.json` read-only ingest into ACE `TRIAGE` is real

### CI proof workflow
- Status: **IMPLEMENTED / VERIFIED**
- Evidence: commit `02b30fe153918170504cc983eec084dd4202e102`

### Minimal packaging proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence: commit `a08dce0b8ba5de70d713b242a457bf6682f06627`

---

## Phase 1

### Phase 1 closed-loop proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - spec: `reports/ace-artifact-phase1-closed-loop-proof-spec-2026-04-25.md`
  - landed commit: `02c02d8`
  - targeted test pass: 7 tests
  - full suite truth at checkpoint: 327 tests green
- Source family: `continuity/pending-promotions.json`
- Meaning:
  - first honest local-only closed loop
  - deterministic decision artifact on pending-promotions input
  - replay-safe
  - no continuity writeback

### Phase 1 interpretation
- Status: **LOCKED**
- Correct label:
  - first closed-loop proof
- Incorrect label:
  - product version
  - ACE 1

---

## Phase 1B

### Phase 1B second closed-loop proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - spec: `reports/ace-artifact-phase1b-second-closed-loop-proof-spec-2026-04-25.md`
  - memory 2026-04-26
  - landed commit: `cd61723`
  - alignment commits: `1b30dd3`, `5606afa`
  - full suite truth at checkpoint: 333 tests green
- Source family: `continuity/open-loops.json`
- Meaning:
  - second materially different closed loop
  - decision based on source-row severity
  - replay-safe
  - no continuity writeback

### Phase 1B interpretation
- Status: **LOCKED**
- Correct label:
  - second distinct closed-loop proof
- Incorrect label:
  - product version
  - ACE 1B

---

## Phase 2

### Phase 2 bounded action-runtime proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - selected/spec'd on 2026-04-26
  - README and hard-gate register both later count two Phase 2 proofs as real
  - current README includes Phase 2 and 2B as landed
  - current hard-gate register includes both as proven
  - current live suite green at 400 tests
- Seam:
  - bounded `action_queue` lifecycle
  - `record_operator_followup`
- Meaning:
  - deterministic enqueue/claim/execute/fail/idempotence exists in bounded form

### Phase 2B bounded action-runtime proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - current README includes Phase 2B as landed
  - current hard-gate register includes Phase 2B as proven
  - live suite green at 400 tests
- Seam:
  - bounded `action_queue` lifecycle
  - `record_operator_rejection`
- Meaning:
  - materially different second bounded action-runtime proof exists

### Important Phase 2 process truth
- Status: **HISTORICAL WARNING**
- Evidence from memory 2026-04-26:
  - earlier Phase 2 attempts were process-contaminated / stale-boundary / semantically insufficient
- Meaning:
  - some earlier agent claims were rejected
  - only later landed repo truth counts

---

## Phase 3

### Phase 3 bounded resume/recovery proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 3 proof
  - hard-gate register includes landed Phase 3 proof
  - live suite green at 400 tests
- Meaning:
  - one bounded resume/recovery seam is real

### Phase 3B bounded recovery proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 3B proof
  - hard-gate register includes landed Phase 3B proof
  - live suite green at 400 tests
- Meaning:
  - second bounded recovery outcome exists

---

## Phase 4

### Phase 4 bounded runtime-ownership proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 4 proof
  - hard-gate register includes landed Phase 4 proof
  - live suite green at 400 tests
- Meaning:
  - bounded runtime-ownership seam is real

### Phase 4B bounded malformed-payload ownership failure proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 4B proof
  - hard-gate register includes landed Phase 4B proof
  - live suite green at 400 tests
- Meaning:
  - second bounded ownership seam exists through explicit durable failure behavior

---

## Activation-first runtime seams

### Bounded sweep runtime
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/sweep.py`
  - `ace/tests/test_sweep.py`
  - current README includes sweep as landed
  - live suite green at 417 tests
- Meaning:
  - bounded stale classification over live ACE DB truth is real

### Bounded read-only briefing runtime
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/briefing.py`
  - `ace/tests/test_briefing.py`
  - current README includes briefing as landed
  - live suite green at 417 tests
- Meaning:
  - deterministic read-only operator summarization over live ACE DB truth is real

### Bounded operator-notification runtime
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/action_runtime.py`
  - `ace/tests/test_action_runtime.py`
  - current README includes notification seam as landed
  - live suite green at 417 tests
  - live DB proof includes completed action plus canonical delivery evidence
- Meaning:
  - deterministic enqueue/claim/execute notification behavior is real

### Bounded autonomous cycle seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/cycle.py`
  - `ace/tests/test_cycle.py`
  - current README includes cycle seam as landed
  - live suite green at 417 tests
- Meaning:
  - composed operator loop over the landed local seams is real

### User-scoped LaunchAgent scheduling seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/launchd/run-ace-cycle.sh`
  - `ace/launchd/ai.superace.cycle.plist`
  - live user LaunchAgent load proof
  - live scheduler-path logs and briefing artifact generation
- Meaning:
  - scheduled execution of the real `ace cycle` path is real

### Delivered operator-alert path
- Status: **IMPLEMENTED / VERIFIED**

### Bounded E1 resident supervisor identity seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - current README includes resident supervisor identity seam as landed
  - current E1 verdict artifact records live CLI proof and targeted 15/15 verification
- Meaning:
  - ACE owns a distinct resident-runtime ledger and lifecycle inspection surface independent from governed one-shot runs

### Bounded E2 startup/shutdown ownership seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/storage.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - targeted supervisor slice green at 13 tests
  - current live suite green at 417 tests
- Meaning:
  - ACE now owns explicit startup truth, explicit shutdown request/completion truth, and explicit failure-phase truth for the resident supervisor slice without collapsing back to governed-run history

### Bounded E3 active runtime inspection seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/storage.py`
  - `ace/ace.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - targeted supervisor slice green at 14 tests
  - current live suite green at 418 tests
- Meaning:
  - ACE now owns append-only resident runtime transition history and operator-visible active runtime inspection for the resident supervisor slice, distinctly from governed-run history

### Bounded E4 runtime failure/recovery contract seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/storage.py`
  - `ace/__init__.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - targeted supervisor slice green at 18 tests
  - current live suite green at 422 tests
- Meaning:
  - ACE now owns resident-runtime recovery request/result truth and append-only recovery history for the resident supervisor slice, distinctly from governed-run failure/interruption

### Bounded E5 anti-inflation boundary seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/ace.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - targeted supervisor slice green at 18 tests
  - current live suite green at 422 tests
- Meaning:
  - ACE now co-locates explicit bounded runtime claims and explicit anti-inflation non-claims on the supervised-runtime inspection surface instead of leaving those denials only in reports

### Bounded E6 distinct minimal slice seam
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/ace.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - `reports/ace-e6-distinct-minimal-slice-proof-verdict-2026-05-07.md`
  - targeted supervisor slice green at 18 tests
  - current live suite green at 422 tests
- Meaning:
  - ACE now co-locates the smallest honest slice definition, the exact E1–E5 artifact bundle, and explicit non-reduction proof on the supervised-runtime inspection surface rather than leaving minimal-slice truth only in reports
- Evidence:
  - completed notification action `action_0f69b18c6f9f12f7efc288c33bfe5c06844fafcb367bbbe70306394a15d167ad`
  - evidence row `evidence_5b185b8163b14ccb9bb1957d260b0a52`
  - `item.evidence_added` event carrying OpenClaw result with Telegram `messageId` `29370` and `chatId` `7529788084`
- Meaning:
  - one real end-to-end operator alert loop is proven

### Governed run lifecycle slice for bounded `ace cycle`
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/storage.py`
  - `ace/governed_run_runtime.py`
  - `ace/cycle.py`
  - `ace/ace.py`
  - `ace/tests/test_governed_run_runtime.py`
  - `ace/tests/test_governed_run_cli.py`
  - governed-run slice post-implementation verification artifact
  - targeted governed-run slice tests green at 9 tests
  - live suite green at 400 tests
  - strict-warning live suite green at 400 tests
- Meaning:
  - bounded `ace cycle` now owns a first-class governed run identity, lifecycle state machine, and current/last run inspection surface
  - this is a new narrow local-only proven seam
  - this does **not** prove broad runtime rollout, daemon/service/platform semantics, continuity-source write authority, or V1

### E1 resident supervisor identity slice
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - `ace/supervisor_runtime.py`
  - `ace/storage.py`
  - `ace/ace.py`
  - `ace/tests/test_supervisor_runtime.py`
  - `ace/tests/test_supervisor_cli.py`
  - `reports/ace-e1-resident-supervisor-identity-verdict-2026-05-07.md`
  - targeted supervisor/runtime gate green at **15 tests OK**
  - full ACE suite green at **412 tests OK**
- Meaning:
  - ACE now owns a distinct resident-runtime ledger and lifecycle truth separate from `governed_runs`
  - `supervisor-status` is a real inspection surface independent from `cycle-status`
  - this is a narrow runtime-class prooflet only
  - this does **not** prove V1, startup/shutdown ownership truth, daemon/service/platform semantics, or generalized runtime fabric

## Phase 5

### Phase 5 operational runtime model
- Status: **SPECIFIED / PARTIAL / NOT A RUNTIME PROOF**
- Evidence:
  - memory 2026-04-26 repeatedly states Phase 5 artifacts are structural/doctrinal only
  - canonical artifact written
  - review verdict explicitly PARTIAL, not PASS
  - hard-gate register still marks operational runtime model PARTIAL / FAIL for V1
- Meaning:
  - Phase 5 is governance truth improvement
  - it is not a new landed runtime proof class

---

## Phase 7A

### Phase 7A cross-seam owned-recovery lifecycle
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 7A proof
  - hard-gate register includes landed Phase 7A proof
  - live suite green at 400 tests
- Meaning:
  - one cross-seam owned-recovery lifecycle proof is real

### Historical note
- memory 2026-04-26 contains earlier spec-stage language before later landing
- current repo truth outranks earlier spec-stage memory

---

## Phase 9A

### Ownership interruption replay-durability proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 9A proof
  - hard-gate register includes landed Phase 9A proof
  - live suite green at 400 tests

---

## Phase 9B

### Recovery interruption replay-durability proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 9B proof
  - hard-gate register includes landed Phase 9B proof
  - live suite green at 400 tests

---

## Phase 11

### Owned-recovery cross-surface interrupted-success ordering proof
- Status: **IMPLEMENTED / VERIFIED**
- Evidence:
  - README includes landed Phase 11 proof
  - hard-gate register includes landed Phase 11 proof
  - live suite green at 400 tests

---

## Phases that are not justified as broader maturity claims

### ACE 1 / ACE 2 taxonomy
- Status: **NOT JUSTIFIED**
- Evidence:
  - scorecard explicitly says justified ACE 1 / ACE 2 taxonomy is not proven
  - naming audit showed drift risk across reports
- Meaning:
  - retire as maturity labels

### V1 claim
- Status: **FAILED / FORBIDDEN BY HARD GATE**
- Evidence:
  - hard-gate register explicitly says not V1
  - gate failures remain open
- Meaning:
  - any V1 claim is false

---

## Hard-gate matrix

### Gate 1 — closed-loop breadth
- Status: **FAIL**

### Gate 2 — runtime ownership truth
- Status: **PARTIAL / FAIL for V1**

### Gate 3 — resume/recovery trust
- Status: **FAIL**

### Gate 4 — failure discipline
- Status: **PARTIAL / FAIL for V1**

### Gate 5 — operational runtime model
- Status: **PARTIAL / FAIL for V1**

### Gate 6 — confidence discipline
- Status: **PARTIAL / FAIL for V1**

### Gate 7 — write authority model
- Status: **FAIL**

### Gate 8 — release/operational packaging truth
- Status: **PARTIAL**

---

## Blunt conclusion

What is implemented and verified:
- foundation ingest proofs
- Phase 1
- Phase 1B
- Phase 2
- Phase 2B
- Phase 3
- Phase 3B
- Phase 4
- Phase 4B
- Phase 7A
- Phase 9A
- Phase 9B
- Phase 11
- bounded sweep runtime
- bounded read-only briefing runtime
- bounded operator-notification runtime
- bounded autonomous cycle seam
- bounded resident supervisor identity seam
- bounded user-scoped LaunchAgent scheduling seam
- one live-proven delivered operator-alert path
- bounded governed-run lifecycle slice for local-only `ace cycle`
- live suite at 412 tests green

What is not true:
- ACE is V1
- ACE 1 / ACE 2 are justified maturity labels
- Phase 5 is a landed runtime proof
- the closed 2026-05-06 next-runtime-class chain yields a distinct new implementation lane
- many narrow proofs add up to V1 automatically

## Clean operator summary

- **Phase 1** = first closed-loop proof on pending-promotions
- **Phase 1B** = second distinct closed-loop proof on open-loops
- Together they are the **closed-loop foundation pair**
- ACE has many real bounded proofs beyond that
- The closed 2026-05-06 next-runtime-class chain did not change class in an implementation-real way, because its implementation gate collapsed back to the already-landed governed-run lifecycle slice
- Closure authority: `reports/ace-hard-gate-next-runtime-class-chain-closure-2026-05-06.md`
- **ACE is still not V1 because the hard gates are not cleared**
