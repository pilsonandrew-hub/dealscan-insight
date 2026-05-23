# ACE V1.1 Phase B / Phase C Sprint Closeout

Status: Phase B and Phase C closed for this sprint. V1.1 item 2 remains intentionally unstarted and requires a separate operator-authorized design/session.

## Honest claim language

> ACE has tamper-evident append-only event chain from V1.1 cutover forward. Pre-cutover history is retained unchanged with disclosed legacy defects.

This is the only approved V1.1 chain claim from this sprint. It does not claim fully tamper-evident pre-cutover history.

## Item 1 — Three-layer event lockdown

Item 1 established event-ledger lockdown across UPDATE, DELETE, and INSERT paths.

Completed layers:

1. SQLite trigger protection for event mutation attempts.
2. Connection authorizer protection for direct event writes.
3. Append-path-only INSERT allowance, limited to governed append helpers and closed after each append attempt.

Commits:

- `b826cd8`
- `c56c389`
- `9889a91`
- `f583345`
- `a9733f6`

Result: direct UPDATE/DELETE/INSERT bypass paths are denied, while canonical append helpers continue to write valid post-cutover events with required metadata.

## Item 3 — Operator scope enforcement

Item 3 established operator scope enforcement as durable guardrails around ACE/JACE work.

Accomplished:

- Scope guard with deny-by-default behavior for side-effecting work.
- Machine-readable authorization boundary from the operator scope anchor.
- Guarded ACE write paths for scoped mutations.
- Tracked git hooks for pre-commit, commit-message, and pre-push enforcement.
- Guarded command/wrapper design and enforcement direction.
- Durable design decisions capturing strict denial, bounded bulk approval, expiries, side-effect classes, and tiered denial behavior.

Primary design-decision reference:

- `ace/state/v1_1_required_items/operator-scope-design-decisions.md`

Commits per the design decisions document and implementation history:

- `9abde23` — concrete operator scope enforcement design.
- `d90fbbf` — revised concrete operator scope enforcement design.
- `3616dee` — operator scope guard slice 1.
- `b59972d` — scope guard wired into write paths.
- `e5507be` — operator scope design decisions recorded.
- `0ae3ef3` / `caa9dd7` — tracked operator scope hooks work, with the intermediate hook revert/resubmission history preserved.

Result: ACE has a durable scope-control basis for implementation work, including tracked hooks and denial behavior, while future external or item-2 work remains outside scope unless separately authorized.

## Phase B — event_sequence checkpoint-forward implementation

Phase B implemented the checkpoint-forward event chain instead of rewriting legacy history.

Cutover boundary:

- `evt_58b80e6282374bf2b1a8611963817aa2`

Accomplished:

- Reverted the unsafe B1 ordering/backfill approach.
- Disclosed legacy ordering and chain defects instead of mutating them away.
- Added a cutover event as the V1.1 boundary.
- Implemented post-cutover `event_sequence` assignment at append time.
- Recomputed head hash inside serialized write transactions.
- Verified post-cutover chain determinism while preserving legacy rows unchanged.

Commits:

- `19602e0`
- `2e590e6`
- `cb741a5`
- `58725a8`
- `1a0f864`
- `a8a6393`
- `179fd11`
- `78b1691`
- `374d5a8`

## Audit verify status as of HEAD

As of sprint closeout HEAD, `python3 -m ace.ace --db ace/state/ace.db audit verify` reports all six audit surfaces green:

- `legacy_chain_inventory=ok`
- `event_hash_chain=ok`
- `post_cutover_event_hash_chain=ok`
- `evidence_consistency=ok`
- `governed_run_integrity=ok`
- `runtime_instance_integrity=ok`

## Disclosed legacy defects

Legacy defects are disclosed in:

- `ace/state/v1_1_required_items/legacy-chain-defects.md`

The disclosed defects include:

- 163 timestamp/id ordering inversions in pre-cutover events.
- 4 deliberately backdated proof events.
- 2 concurrent-write chain breaks from 2026-05-23.
- Possible inert B1-residue `event_sequence` values on pre-cutover rows in databases touched by the reverted B1/bootstrap path.

These defects are retained unchanged as historical truth. They are not hidden, rewritten, or included in the post-cutover tamper-evidence claim.

## Remaining for V1.1 closure

V1.1 is not fully closed.

Remaining item:

- Item 2 — external attestation to Backblaze B2.

After item 2 is designed, implemented, tested, and externally verified under separate operator authorization, ACE can receive an honest re-tag of ACE 1.0 using the approved chain-claim boundary.
