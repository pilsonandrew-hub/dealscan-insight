# ACE Gate 4 Composition-Seam Contradiction Note — 2026-05-06

> **Scope**
> This note centralizes current contradiction truth across the decision, sweep, and briefing composition seams.
> It does **not** authorize V1 promotion, runtime-class reopening, or broader platform claims.

## Purpose

The remaining Gate 4 weakness is no longer absence of proof.
The weakness is that composition-seam contradiction truth is real but scattered.

This note collapses the current repo-grounded truth for:
- Phase 1 / decision composition,
- sweep composition,
- briefing composition,
- and the still-partial families that connect them.

---

## Composition-seam contradiction classes

### C1. Decision evidence exists even though malformed closed-loop input should have been rejected
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- `ace/phase1_closed_loop.py`
- `ace/tests/test_phase1_closed_loop.py`
- `ace/tests/test_phase1b_closed_loop.py`

Meaning:
- malformed/schema-invalid top-level closed-loop input does not emit decision evidence.
- replay reuses existing decision evidence instead of inventing a second decision story.

### C2. Closed-loop run mutates the continuity source while also claiming read-only decision truth
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- Phase 1 / Phase 1B tests explicitly guard write/unlink/rename/replace behavior on the source boundary.

Meaning:
- decision proof stays bounded to read-only use of continuity source truth.
- source mutation is not silently smuggled into the loop.

### C3. Phase 1 source-row loading silently compresses malformed per-row source truth into absence
**Status:** PARTIAL

Repo-grounded basis:
- `ace/phase1_closed_loop.py::_load_pending_source_rows()`
- current Gate 4 Phase 1 artifacts on row-outcome matrix and soft-skip classification

Meaning:
- non-dict rows are skipped,
- invalid/missing status rows are skipped,
- pending rows that later fail required-field normalization are skipped.

Honest interpretation:
- this is not explicit false success.
- this is under-classified ambiguity debt inside the decision composition seam.

### C4. Sweep re-emits unchanged stale truth as if it were fresh activity
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- `ace/sweep.py`
- `ace/tests/test_sweep.py`

Meaning:
- duplicate stale findings are suppressed when fingerprint is unchanged.
- unchanged truth is not restated as a fresh contradiction-free signal.

### C5. Sweep suppresses materially changed stale truth and leaves operators with an outdated stale story
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- `ace/sweep.py`
- `ace/tests/test_sweep.py`

Meaning:
- sweep fingerprints include activity time, last event id, evidence count, obligation count, contradiction count, and stale classification inputs.
- changed truth re-emits instead of hiding behind duplicate suppression.

### C6. Sweep with zero findings implies silence instead of durable “nothing stale found” truth
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- `ace/sweep.py`
- `ace/tests/test_sweep.py`

Meaning:
- the sweep summary event still lands even when no item findings emit.
- absence is not flattened into missing operator truth.

### C7. Briefing duplicates stale TRIAGE items into `needs_decision`, creating contradictory operator sections
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- `ace/briefing.py`
- `ace/tests/test_briefing.py`

Meaning:
- stale item ids are excluded from the live `needs_decision` section.
- the same item is not rendered as both stale and active-decision work in one briefing.

### C8. Briefing diverges from live DB state for blocked / claimed_done / triage sections
**Status:** PREVENTED IN BOUNDED FORM

Repo-grounded basis:
- `ace/briefing.py`
- `ace/tests/test_briefing.py`

Meaning:
- briefing sections are built from current repo item state plus sweep findings.
- render is deterministic and tied to live DB state rather than loose narrative reconstruction.

---

## What is still partial

### P1. Decision ambiguity centralization
Current truth:
- top-level malformed input rejection is already strong.
- replay safety is already strong.
- source-boundary immutability is already strong.

Remaining weakness in this earlier draft:
- historical pre-fix row-loader weakness families were still governed mostly by surrounding notes rather than one central composition-seam contradiction family.

Current live truth:
- the earlier Phase 1 soft-skip family was tightened later on 2026-05-06 and is no longer active runtime truth.

### P2. Cross-surface composition narration
Current truth:
- sweep and briefing each prevent specific contradiction classes.
- Phase 1 has bounded explicit failure and replay-safe reuse.

Remaining weakness:
- there is still no one short governed explanation that tells an operator how decision, sweep, and briefing contradictions relate as one family.

### P3. One-step operator inspection
Current truth:
- `ace gate4-inspection` now exposes bounded Gate 4 artifacts on disk.

Remaining weakness:
- the operator still depends on report-backed interpretation rather than a richer first-class runtime inspection model.
- that is acceptable at the current class, but it remains partial.

---

## Honest current conclusion

Decision / sweep / briefing contradiction control is already bounded and real.
The weak point is not missing contradiction prevention.
The weak point is that composition-seam contradiction truth is still organized as multiple adjacent proofs rather than one compact governed family.

That means the honest next progress is:
1. keep composition contradiction truth centralized in governed artifacts,
2. expose those artifacts through bounded inspection surfaces,
3. avoid pretending this becomes runtime-class advancement or V1 evidence.

---

## Anti-fake rules

Do **not** count any of the following by themselves:
- broader “composition is robust now” language
- restating sweep or briefing behavior without mapping contradiction class
- new logs without new contradiction inspectability
- reusing superseded Phase 1 soft-skip language after runtime truth changed
- treating report centralization as maturity promotion

---

## Bottom line

The composition seam is no longer an unknown.
It is now truthfully classed as:
- strong bounded contradiction prevention across sweep and briefing,
- strong bounded explicit failure/replay discipline at top-level closed-loop decision,
- and one earlier ambiguity family inside Phase 1 row loading that was later tightened the same day.

That is a real Gate 4 truth improvement.
It is not a new runtime lane.
