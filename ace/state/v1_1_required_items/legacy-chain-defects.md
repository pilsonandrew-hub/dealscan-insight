# ACE V1.1 Legacy Chain Defects Disclosure

## 1. Summary

This file is the durable disclosure of known defects in the ACE event chain prior to the V1.1 cutover.

It exists because V1.1 establishes tamper-evidence **from cutover forward** rather than retroactively repairing legacy history. This follows Ja’rvontis’ recommendation and Andrew’s governing decision recorded on 2026-05-23: checkpoint forward, do not rewrite history.

This file does **not** claim that pre-cutover history is guaranteed deterministic or tamper-evident. Pre-cutover history is retained unchanged with disclosed legacy defects.

## 2. Inventory of defects

Read-only diagnosis source:

- `/tmp/ace_b1_readonly_diag.txt` at diagnosis time
- durable copy: `ace/state/v1_1_required_items/slice-b1-chain-diagnosis-readonly.md`

Known pre-cutover defects:

- 163 timestamp/id ordering inversions in pre-cutover events.
- Breakdown by `event_type`:
  - `ace.supervisor.heartbeat`: 108
  - `item.evidence_added`: 32
  - `ace.supervisor.failed`: 15
  - `item.created`: 4
  - `ace.sweep.completed`: 3
  - `ace.supervisor.started`: 1
- 4 deliberately backdated `item.created` events:
  - `evt_23baa89e60be405188ecb1d4f80060db` — `launchagent e2e notification proof`
  - `evt_f74e43854f064dda92978ff9f7f9c6d7` — `gateway transport e2e proof item`
  - `evt_00efc6629cbd485b981c223db66a67f9` — `Proceed And continue`
  - `evt_2cea161db6fe4f4796e582021b3aaaeb` — `ACE/Jace launchd automated notification E2E proof 2026-05-21`
- 2 concurrent-write chain breaks at approximately `2026-05-23T02:18:32-33Z`:
  - `evt_17bf5b3365aa42dd962a31b3cca3d0b7`
  - `evt_a93eda9ab0f84b1ca0622d166da027d2`
- B1-residue `event_sequence` values may exist on pre-cutover rows in local/live state databases because Slice B1 briefly backfilled the column before the design was reverted. These values are documented inert residue. They are not authoritative chain order, must not be cleaned up by mutating pre-cutover events, and must be ignored by the V1.1 post-cutover verifier.

## 3. Root cause analysis

The original ACE chain was implicitly ordered by SQLite row `id` / auto-increment append order, not by an explicit sequence counter.

`created_at` was treated as event metadata during chain construction, but some verifier/migration logic treated it as ordering authority. These orderings disagreed for 163 historical events.

`append_event` did not serialize concurrent writes with `BEGIN IMMEDIATE`. Concurrent appends could interleave such that `previous_event_hash` was computed against a stale head, producing the 2 known broken links from 2026-05-23.

Slice B1, committed as `600d65f` and reverted as `19602e0`, attempted to fix ordering by backfilling `event_sequence` using `(created_at, id)`. That exposed the historical disagreement rather than resolving it. In databases already touched by B1/bootstrap, its `event_sequence` values can remain as schema/data residue even after source rollback. The V1.1 checkpoint-forward design treats that residue as legacy defect inventory, not as state to repair.

## 4. Governing decision

Ja’rvontis considered three options:

1. Accept messy history.
2. Re-hash the entire chain.
3. Checkpoint forward.

Re-hash was rejected because it repeats the same action pattern as the original breach and weakens trust even with disclosure.

Accept-messy was rejected because it leaves V1.1 with an ambiguous guarantee.

Checkpoint forward was selected. Legacy history stays unchanged with disclosed defects, including any B1-residue `event_sequence` values. The V1.1 guarantee starts after the cutover boundary.

## 5. Forward design preview

A cutover event will be appended in slice B-cutover, establishing the V1.1 chain boundary.

`append_event` will be redesigned in slice B-append to serialize writes with `BEGIN IMMEDIATE` and assign `event_sequence` inside the transaction, with head-hash recomputation inside that same transaction.

Tests in slice B-tests will prove post-cutover events verify deterministically while pre-cutover events stay as-is.

## 6. Honest claim language

Approved claim:

> ACE has a tamper-evident append-only event chain from the V1.1 cutover forward. Pre-cutover history is retained unchanged with disclosed legacy defects.

Forbidden claims:

- “ACE history is fully tamper-evident.”
- Any claim that implies pre-cutover defects do not exist.
