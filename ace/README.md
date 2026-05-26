# ACE — Personal Work-Tracking CLI

ACE is currently a personal CLI tool that helps Andrew track stale work items, catch state-transition loose ends, and receive weekly Telegram digests.

It is in normal operational use, not a V1.1/V1.2 sprint and not an activated governance platform.

## Current operational commands

ACE’s active mission is limited to three CLI commands:

- `ace stale` — lists work items whose latest event is older than a configurable number of days.
- `ace loose-ends` — scans existing ACE item/event/evidence records for state-transition, evidence, and authorization gaps.
- `ace digest` — combines stale-work and loose-end findings into a weekly Telegram digest through the existing JACE bot path.

These commands are intended to make ordinary work tracking more honest: old work should surface, loose ends should be visible, and weekly status should reach Andrew without pretending inactive systems are live.

## What ACE is not currently claiming

ACE is not currently claiming to be:

- a governance platform;
- an activated operator-scope enforcement system;
- an active V1.1 or V1.2 runtime;
- an externally attested system;
- a Backblaze-backed durability layer;
- a cryptographically enforced production control plane;
- an activated ACE 1.0 release/tag.

Cryptographic tamper-evidence, external attestation, scope enforcement, and related foundation code exists in the repository, but it is not currently activated as the operating mission.

## Runtime

- Python 3
- SQLite database: `ace/state/ace.db`
- CLI entrypoint: `python3 -m ace.ace`
- Scheduled digest LaunchAgent: `ace/launchd/ai.superace.digest.plist`
- CI workflow: `.github/workflows/ace-ci.yml`

## Current state model

ACE reads the existing `items`, `events`, and `evidence` tables.

The normal item path remains:

`TRIAGE -> APPROVED -> CLAIMED_DONE -> VERIFIED_DONE`

Legacy states and historical proof records may still exist in the database, but the current operational commands should avoid turning inactive historical residue into false live work.

## Operational boundaries

Allowed ongoing work is limited to:

- bug fixes for `ace stale`, `ace loose-ends`, and `ace digest` when Andrew reports issues;
- filter refinements for those commands when Andrew reports noise;
- documentation corrections that keep ACE aligned with its actual current use.

Not currently authorized:

- new V1.1 work;
- V1.2 work;
- Item 4 work;
- Backblaze sync or attestation activation;
- ACE 1.0 re-tagging;
- scope guard/operator activation work;
- infrastructure work outside the three operational commands.

## Verification expectation

Do not treat README claims as proof. Current truth must come from live command output, real git diffs, real test runs, and real GitHub Actions URLs when CI status is claimed.
