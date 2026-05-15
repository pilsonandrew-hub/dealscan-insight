# ACE Gate 4 Recovery Failure Taxonomy — 2026-05-06

> **Scope**
> This artifact classifies current recovery-failure truth on the live ACE repo.
> It does **not** authorize V1 promotion, runtime-class reopening, or broad recovery claims.

## Purpose

Recovery is no longer honest to describe as simply “missing.”
The live repo already proves several bounded recovery failure classes.
The real problem is that the proof is uneven:
- some classes are clearly implemented and tested,
- some are only bounded in one path,
- some are still not systematized.

This artifact separates those three states.

---

## Recovery surfaces reviewed

Primary code surfaces:
- `ace/resume_recovery_runtime.py`
- `ace/owned_recovery_runtime.py`
- `ace/runtime_ownership.py`

Primary test surfaces:
- `ace/tests/test_resume_recovery_runtime.py`
- `ace/tests/test_owned_recovery_runtime.py`
- `ace/tests/test_resume_runtime.py`
- `ace/tests/test_runtime_ownership.py`

---

## Recovery failure classes

### R1. Malformed session metadata rejection
Meaning:
- malformed or non-object recovery/session metadata must fail explicitly
- no partial success artifact may be emitted
- durable recovery/session truth must remain non-success

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_resume_recovery_runtime.py` proves malformed metadata raises `ValidationError` with zero partial writes
- `owned_recovery_runtime.py` enforces JSON-object session metadata and raises `ValidationError` on decode/object mismatch

### R2. Candidate/session selection conflict rejection
Meaning:
- a session cannot silently switch to a different candidate
- mismatched selection must fail loudly
- no success evidence may leak during mismatch

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_resume_recovery_runtime.py` proves selecting a different candidate for the same session raises `ValidationError`
- `owned_recovery_runtime.py` enforces `selected_candidate_id` equality across connected lifecycle surfaces

### R3. Cross-seam identity mismatch rejection
Meaning:
- ownership, session, and candidate must refer to the same item and same connected lifecycle
- mismatch must fail before success artifacting

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_owned_recovery_runtime.py` proves cross-seam item/session/candidate mismatch raises `ValidationError` and writes no evidence
- `_assert_connected_same_item()` in `owned_recovery_runtime.py` enforces item/ownership/candidate/session consistency

### R4. Stale or deleted target failure
Meaning:
- recovery completion against a missing target item must fail explicitly
- no success evidence may be written
- persistent state must reflect failure, not silent no-op

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_resume_recovery_runtime.py` proves stale target completion returns `failed`, writes no evidence, and marks session `failed`
- `test_owned_recovery_runtime.py` proves stale/deleted underlying item yields `recovery_status=failed`, preserves claimed ownership, writes no success evidence, and leaves session failed
- `test_runtime_ownership.py` proves release against missing target fails explicitly with no ownership success evidence

### R5. Replay-safe dismissal completion
Meaning:
- completing dismissal twice must not duplicate recovery evidence
- bounded success must remain idempotent under replay

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_resume_recovery_runtime.py` proves dismissal writes one evidence row and replay is safe
- `test_owned_recovery_runtime.py` proves connected finalize is replay-safe and non-duplicative

### R6. Interrupted split-heal recovery/ownership completion
Meaning:
- if one side of a recovery/ownership success already landed before interruption,
  replay must heal the remaining side without duplicating evidence or inventing a new success path

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_owned_recovery_runtime.py` proves interrupted cross-surface success healing without duplicate recovery evidence
- `test_runtime_ownership.py` proves interrupted ownership success heals without duplicate evidence

### R7. Ownership conflict rejection
Meaning:
- conflicting owners must not silently co-own the same bounded work item
- conflict must fail explicitly without false success

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_runtime_ownership.py` proves conflicting owner claim/re-register paths raise `ValidationError`

### R8. Malformed ownership payload rejection
Meaning:
- corrupted persisted ownership payload must fail explicitly on release/finalization
- no success evidence may be emitted

Current status:
- **IMPLEMENTED IN BOUNDED FORM**

Evidence basis:
- `test_runtime_ownership.py` proves malformed persisted payload yields failed ownership release and zero success evidence

---

## What is still only partial

### P1. Recovery failure taxonomy is not yet centralized
What is missing:
- one governed artifact mapping all recovery failure classes to exact code paths, evidence surfaces, and persistent state outcomes

Why this matters:
- the repo has many bounded proofs, but they are distributed across resume, owned recovery, and ownership surfaces
- that makes overclaiming easier than it should be

### P2. Success/no-op/failure distinctions are not yet governed as one family
What is missing:
- one explicit review surface explaining where recovery is:
  - success,
  - bounded no-op/replay reuse,
  - explicit failure,
  - healed interruption

Why this matters:
- the proofs exist in pieces
- the operator/governance layer still has to infer the full taxonomy across files

### P3. Cross-seam contradiction inventory is still incomplete
What is missing:
- explicit map of every recovery/ownership/session/candidate contradiction class that is prevented, healed, or still unproven

Why this matters:
- we have bounded mismatch rejection and interrupted split-heal proofs
- we do not yet have a complete contradiction inventory for the whole recovery family

### P4. Broader recovery inspection surface is still narrow
What is missing:
- one bounded operator-facing inspection surface summarizing recovery failure truth without requiring multi-table/test-level archaeology

Why this matters:
- failure truth is durable in tables and evidence
- but inspection still depends too much on knowing the internal seams

---

## What is not missing anymore

The repo already disproves these stale claims:
- “recovery failure proof is absent”
- “only replay success exists”
- “recovery has no stale-target failure proof”
- “cross-seam mismatch rejection is unproven”

Those statements are now false against live repo truth.

---

## Honest weak-point ranking inside recovery

### Stronger bounded recovery proofs already on disk
1. malformed metadata rejection
2. candidate/session selection conflict rejection
3. cross-seam identity mismatch rejection
4. stale/deleted target failure
5. replay-safe dismissal completion
6. interrupted split-heal recovery/ownership completion
7. ownership conflict rejection
8. malformed ownership payload rejection

### Weaker remaining recovery-governance gaps
1. centralized recovery failure taxonomy
2. unified success/no-op/failure/healed classification surface
3. broader contradiction inventory across recovery seams
4. bounded operator-facing failure inspection for the recovery family

---

## What would count as real next progress

Real Gate 4 recovery progress next would look like:
- one governed recovery failure matrix tied to exact code/test surfaces
- one contradiction map covering recovery/ownership/session/candidate seams
- one bounded inspection artifact showing how to read recovery failure truth directly
- targeted tests only where a real contradiction or unclassified failure family is still unproven

## What would not count

Do not count any of the following as recovery progress by themselves:
- nicer recovery logs
- broader resilience language
- re-proving replay-safe cases we already have
- renaming recovery states without tightening proof
- implying broad recovery maturity from the bounded dismissal/replay proofs alone

---

## Bottom line

Recovery is **not absent**.
Recovery is **bounded, real, and uneven**.

The next honest move is not to invent missing recovery proof.
It is to turn the already-landed recovery proofs into a governed taxonomy, then attack the still-unmapped contradiction and inspection gaps.
