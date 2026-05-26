# ACE Status

Date: 2026-05-26
Current status: operational work-tracking CLI, not tagged ACE 1.0
Current mission: `ace stale`, `ace loose-ends`, and `ace digest`

ACE is currently an operational local work-tracking layer for Andrew. Its active value is helping track idle work, catch loose ends, and send a weekly operator digest through the existing JACE Telegram path.

The current active mission is the three-command operating surface:

- `ace stale`
- `ace loose-ends`
- `ace digest`

V1.1 cryptographic work, Backblaze attestation, event-sequence/checkpoint work, and scope-enforcement machinery exist in the codebase, but they are not the active operating mission and are not activated as the current product posture. ACE 1.0 is not tagged, and there is no current plan to tag ACE 1.0.

## Current operational commands

### `ace stale`

`ace stale` lists idle active work items whose latest event is older than a configurable threshold.

Current behavior:

- default threshold: 7 days
- reads existing `items` and `events` rows only
- uses latest event timestamp, not merely `items.updated_at`
- outputs a fixed-width table with:
  - `item_id`
  - `current_state`
  - `days_idle`
  - `last_event_type`
- sorts by `days_idle` descending
- reports only operational work states, not closed historical residue

Purpose: surface neglected work without pretending to solve governance or cryptographic integrity.

### `ace loose-ends`

`ace loose-ends` scans existing item/event history for operational slop patterns.

Current patterns include:

- state transition predecessor gaps
- `CLAIMED_DONE` items without supporting evidence
- operator-initiated items that moved forward without an operator authorization marker

Current behavior:

- reads existing tables only
- outputs a fixed-width table with:
  - `pattern_name`
  - `item_id`
  - `detected_at`
  - `evidence_gap`
- filters known terminal cleanup residue so historical cleanup closure does not create false active work

Purpose: catch loose ends and code/process slop that matter to the operator.

### `ace digest`

`ace digest` combines `ace stale` and `ace loose-ends` into one weekly operator message.

Current behavior:

- sends through the existing JACE Telegram outbound path
- supports dry-run output for inspection without sending
- includes stale and loose-end sections
- truncates safely for Telegram message limits
- has a launchd plist scheduled for Sundays at 9am

Purpose: make ACE useful without requiring Andrew to remember to poll it manually.

## Activated vs non-activated surfaces

Activated and operational:

- SQLite-backed ACE state database
- work item/event reading for the three commands
- `ace stale`
- `ace loose-ends`
- `ace digest`
- JACE outbound Telegram path used by digest
- Sunday 9am digest launchd plist
- tests covering the three command surfaces
- GitHub Actions ACE CI for pushed changes

Present in code but not the active mission:

- V1.1 cryptographic foundation work
- event-sequence/checkpoint-forward work
- Backblaze/external attestation machinery
- scope-enforcement/operator-activation machinery
- broad governance foundation claims
- ACE 1.0 tagging

## What ACE is right now

ACE is a practical operational assistant layer for local work hygiene.

It helps answer:

- What work has gone stale?
- What lifecycle/history gaps look suspicious?
- What should Andrew see in a weekly digest?

That is the current product truth.

## What ACE is not currently claiming

ACE is not currently claiming:

- tagged ACE 1.0 completion
- activated V1.1 cryptographic integrity
- external Backblaze attestation as an active proof boundary
- active scope-enforcement governance as the operator-facing product
- broad autonomous runtime fabric
- broad natural-language work ownership
- production-grade distributed agent orchestration

Those may exist as code paths, historical artifacts, or future options, but they are not the current operational posture.

## Verification posture

The operational posture should be proven by:

- focused tests for `ace stale`, `ace loose-ends`, and `ace digest`
- full ACE test suite before push
- CI green after push
- live command smoke output when behavior changes
- explicit confirmation of changed files per commit

For documentation-only changes, the proof boundary is:

- diff review
- commit containing only the approved documentation file
- CI green after push

## Current priority

Keep ACE useful and honest.

Near-term work should improve the three-command operating surface unless Andrew explicitly reopens cryptographic foundation, attestation, or scope-enforcement work.
