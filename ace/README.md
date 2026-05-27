# ACE — Personal Work-Tracking CLI

ACE is a personal CLI that helps Andrew track stale work, catch lifecycle loose ends, send weekly Telegram digests, and keep documentation and intake filters honest.

It is in normal operational use on the **`master`** branch. Closeout release name: ACE 2.0. Cryptographic V1.1/V1.2 foundation code remains in the repository but is not the active mission.

## Current operational commands

ACE’s active mission is these CLI commands:

### Core work hygiene

- `ace stale` — lists work items whose latest event is older than a configurable number of days.
- `ace loose-ends` — scans existing ACE item/event/evidence records for state-transition, evidence, and authorization gaps.
- `ace digest` — combines stale and loose-end findings into a weekly Telegram digest through the existing JACE bot path, including per-stale-item resume context (last three events, current state, open obligations).

### Documentation and operator honesty

- `ace contradictions` — compares high-value README/STATUS claims to verifiable CLI, git tag, and CI badge state.
- `ace hooks install` — installs non-blocking `commit-msg` false-closure advisories (`ace hooks status` shows whether they are active).

### Telegram commitment intake

- `ace propose` — scans the OpenClaw session stream for first-person commitments and creates TRIAGE proposal items; use `accept` or `reject` with an item id for operator confirmation (decisions logged for filter tuning).

### Filter tuning visibility

- `ace filter-health` — read-only monthly signal-to-noise summary for proposal and Telegram direct-work filters, with drift warnings.

These commands are intended to make work tracking honest: neglected work surfaces, loose ends stay visible, weekly status reaches Andrew with enough context to act, and docs or intake filters that drift toward uselessness get caught early.

## What ACE is not currently claiming

ACE is not currently claiming to be:

- a governance platform;
- an activated operator-scope enforcement system (tracked scope hooks in `ace/hooks/hooklib.py` are separate from operational hooks);
- an active V1.1 or V1.2 runtime;
- an externally attested system;
- a Backblaze-backed durability layer;
- a cryptographically enforced production control plane.

Cryptographic tamper-evidence, external attestation, scope enforcement, and related foundation code exists in the repository, but it is not currently activated as the operating mission.

## Runtime

- Python 3
- SQLite database: `ace/state/ace.db`
- CLI entrypoint: `python3 -m ace.ace`
- Scheduled digest LaunchAgent: `ace/launchd/ai.superace.digest.plist`
- CI workflow: `.github/workflows/ace-ci.yml`
- Integration branch: `master` (ACE 2.0 closeout applies git label `ace-2.0`)

## Current state model

ACE reads the existing `items`, `events`, `evidence`, and `obligations` tables.

The normal item path remains:

`TRIAGE -> APPROVED -> CLAIMED_DONE -> VERIFIED_DONE`

Legacy states and historical proof records may still exist in the database, but operational commands should avoid turning inactive historical residue into false live work.

## Operational boundaries

Allowed ongoing work is limited to:

- bug fixes and filter refinements for the operational commands above when Andrew reports issues;
- documentation corrections that keep ACE aligned with verifiable behavior (`ace contradictions` is the check).

Not currently authorized:

- new V1.1 work;
- V1.2 work;
- Item 4 work;
- Backblaze sync or attestation activation;
- scope guard/operator activation work beyond optional `ace hooks install` false-closure advisories;
- infrastructure work outside the operational command surface.

## Verification expectation

Do not treat README claims as proof. Current truth must come from live command output, `ace contradictions`, real test runs, and real GitHub Actions results when CI status is claimed.
