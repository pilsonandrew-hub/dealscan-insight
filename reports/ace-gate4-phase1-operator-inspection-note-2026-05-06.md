# ACE Gate 4 Phase 1 Operator Inspection Note — 2026-05-06

> **Scope**
> This is an operator-facing interpretation note for current Phase 1 row outcomes.
> It does **not** promote ACE to V1 and does **not** change runtime-class boundaries.

## Purpose

The current Phase 1 seam is no longer broad decision failure.
It is narrower:
**some row-level source conditions are intentionally filtered, while malformed pending-row structure now fails loudly under the governed source contract.**

This note translates that distinction into operator-facing language.

---

## Current operator-facing truth

When Phase 1 does **not** produce decision evidence for a row, that absence can currently mean different things:

### 1. Intentional bounded ineligibility
This is acceptable.
Current example:
- row status is not `pending`

Interpretation:
- the row was not eligible for Phase 1 follow-up
- this is bounded filtering, not bad source truth disappearing silently

### 2. Loud schema failure during governed pending-row normalization
This is already explicit.
Current examples:
- row is not an object
- row has missing/invalid status
- row is `pending` but fails required-field normalization

Interpretation:
- malformed pending-row structure no longer disappears into a soft skip
- current behavior fails loudly under the governed pending-promotions source contract

### 3. Loud hard failure later in the path
This is already explicit.
Current example:
- an ingested item cannot be matched back to a required source row by id

Interpretation:
- this is not a silent skip
- current behavior is already bounded and inspectable as a hard failure

---

## What operators should not assume

Do **not** assume that “no Phase 1 decision evidence” always means the same thing.
Right now it can mean:
- intentionally not eligible
- loud schema failure during governed pending-row normalization
- later explicit hard failure

That distinction still matters, but malformed pending rows are no longer part of the earlier pre-fix weak-loader class.

---

## What is already strong

The following are already bounded and should not be re-described as missing:
- malformed top-level closed-loop input rejection with zero writes
- missing required top-level closed-loop field rejection with zero writes
- replay-safe decision evidence reuse
- read-only continuity-source boundary during run
- explicit later hard failure when a required ingested source row cannot be found

---

## What is still weak

The weak point is not broad decision logic.
It is specifically:
- bounded/local-only scope remains in force
- operator language must continue to distinguish bounded filtering from loud schema failure and later hard failure

The most important current distinction is:
**the operator should not collapse bounded filtering, governed schema failure, and later hard failure into one generic “no decision evidence” bucket.**

---

## Honest next progress

Real improvement from here would be:
1. preserve the governed distinction between bounded filtering and loud schema failure
2. verify adjacent operator/report surfaces stay aligned with the tightened runtime contract
3. only reopen this seam if a genuinely new unclassified Phase 1 row family appears

---

## Bottom line

Current Phase 1 absence is not one thing.
It is a mix of:
- acceptable bounded filtering
- loud governed schema failure for malformed pending rows
- explicit later hard failure

That distinction is now surfaced more truthfully than before, without broadening ACE’s bounded scope.
