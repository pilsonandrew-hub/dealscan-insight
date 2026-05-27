# ACE Status

Date: 2026-05-27
Current status: operational work-tracking CLI, ACE 2.0 closeout
Current mission: core hygiene (`ace stale`, `ace loose-ends`, `ace digest`) plus honesty, intake, and filter-health commands

ACE is an operational local work-tracking layer for Andrew. It surfaces idle work, lifecycle gaps, weekly Telegram digests with resume context, documentation contradictions, optional false-closure git advisories, Telegram commitment proposals, and monthly filter signal-to-noise reporting.

The ace-1.0 label remains in git history from an earlier closeout attempt. **ACE 2.0 is the current operational release name** for the full command surface below (integration branch: master).

## Current operational commands

### `ace stale`

Lists idle active work items whose latest event is older than a configurable threshold.

- default threshold: 7 days
- reads `items` and `events` only
- fixed-width table: `item_id`, `current_state`, `days_idle`, `last_event_type`
- sorts by `days_idle` descending

### `ace loose-ends`

Scans item/event history for operational slop patterns.

- state transition predecessor gaps
- `CLAIMED_DONE` without supporting evidence
- operator-initiated forward motion without `operator_approval`
- filters terminal cleanup residue

### `ace digest`

Combines `ace stale` and `ace loose-ends` into one weekly operator message.

- JACE Telegram outbound path
- `--dry-run` for inspection
- per-stale-item resume context: last three events, current state, open obligations
- Telegram-safe truncation (4096 chars)
- Sunday 9am launchd plist: `ace/launchd/ai.superace.digest.plist`

### `ace contradictions`

Read-only documentation honesty check for `ace/README.md` and `ace/STATUS.md`.

- operational-command claims vs CLI `--help`
- release-name literals vs repository label list output
- CI badge claims vs latest workflow run (`--skip-ci` for offline)
- fixed-width findings table; exit `1` on critical/error rows

### `ace hooks install` / `ace hooks status`

Optional operational git hooks at `ace/hooks/operational/`.

- `commit-msg` false-closure advisory: warns when completion language appears while `ace loose-ends` still reports gaps
- **non-blocking** (always exit `0`)
- separate from V1.1 scope-enforcement hooks in `ace/hooks/hooklib.py`

### `ace propose` / `ace propose accept` / `ace propose reject`

Commitment ingestion from the OpenClaw Telegram session stream.

- bounded phrases: `i will`, `i need to`, `let me`, `remember to`
- creates TRIAGE items with source `telegram/commitment-proposal`
- accept → `APPROVED`; reject → `DROPPED`
- decisions append to `ace/state/propose_filter_decisions.jsonl`

### `ace filter-health`

Read-only monthly signal-to-noise report (`--month YYYY-MM`).

- `propose:*` filters from accept/reject decision log
- `telegram:*` filters from direct-work item outcomes
- `loose_ends:*` current snapshot counts (`snapshot_only`, no historical SNR)
- drift warnings when ratio falls below tuning threshold

## Activated vs non-activated surfaces

Activated and operational:

- SQLite-backed ACE state database
- commands listed above
- JACE Telegram path for digest
- Sunday digest launchd plist
- ACE CI on `master` (`.github/workflows/ace-ci.yml`)
- ACE 2.0 closeout (git label `ace-2.0` on integration branch `master`)

Present in code but not the active mission:

- V1.1 cryptographic foundation work
- event-sequence/checkpoint-forward work
- Backblaze/external attestation machinery
- blocking scope-enforcement hooks (`ace/hooks` via `hooklib.py`)
- broad governance foundation claims

## What ACE is right now

ACE is a practical operator layer for local work hygiene and honest self-checks.

It helps answer:

- What work has gone stale?
- What lifecycle gaps look suspicious?
- What should Andrew see in a weekly digest (with enough context to resume)?
- Do README/STATUS claims still match repo reality?
- Are Telegram commitment or direct-work filters drifting toward noise?

## What ACE is not currently claiming

ACE is not currently claiming:

- activated V1.1 cryptographic integrity
- external Backblaze attestation as an active proof boundary
- active scope-enforcement governance as the operator-facing product
- broad autonomous runtime fabric or distributed agent orchestration

## Verification posture

Prove operational posture with:

- `ace contradictions` (and `--skip-ci` only when offline)
- focused tests for each operational command surface
- full ACE test suite before push
- CI green after push to `master`
- live command smoke output when behavior changes

For documentation-only changes:

- diff review
- documentation-only commit
- `ace contradictions` clean after doc update
- CI green after push
- git label `ace-2.0` points at the release commit on `master`

Post-release smoke:

```sh
sh ace/scripts/verify_operational_release.sh
```

## Current priority

Keep the ACE 2.0 operational surface useful and honest. Do not reopen V1.1 cryptographic, attestation, or scope-enforcement work unless Andrew explicitly directs it.
