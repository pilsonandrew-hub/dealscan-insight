# Current Operator Instruction

Authority: this file is the durable operator scope anchor. The bot does not edit this file except by explicit operator instruction. Operator (Andrew) updates it via explicit instruction. Chat-level conflicts lose to this file.

Last updated: 2026-05-26 by explicit operator reset instruction.

## Mode

operational_ongoing — normal ACE use, not a sprint.

## Current operational reality

ACE is in ongoing operational use for its original mission: helping Andrew track work, catch loose ends, and prevent code slop.

The active operational surface is limited to three CLI commands:

- `ace stale` — track idle work items.
- `ace loose-ends` — catch state-transition and evidence/authorization loose ends.
- `ace digest` — send a weekly Telegram digest through the existing JACE bot path.

V1.1 cryptographic, attestation, scope-enforcement, and related foundation code may exist in the repository, but it is not the active mission and is not authorized for new work under this anchor.

## Authorized work

Only the following writes are authorized:

- Bug fixes to `ace stale` when Andrew reports issues.
- Bug fixes to `ace loose-ends` when Andrew reports issues.
- Bug fixes to `ace digest` when Andrew reports issues.
- Filter refinements for those three commands when Andrew reports noise.
- Documentation updates explicitly requested by Andrew for the operational reset.

## Forbidden work

The following are forbidden unless Andrew gives a new explicit instruction that supersedes this anchor:

- New V1.1 work.
- V1.2 work.
- Item 4 work.
- Backblaze sync work.
- Attestation activation.
- ACE 1.0 re-tag work.
- Scope guard activation.
- Operator activation checklist execution.
- Infrastructure work outside the three CLI commands.
- Investigation or remediation of inactive cryptographic/attestation/scope-enforcement code unless Andrew explicitly asks for it.

## Required behavior

After the operational reset documentation commit is pushed and CI is green, stop.

Do not start V1.2 work.
Do not propose new features.
Do not generate roadmaps.
Do not investigate existing cryptographic code.
Do not recommend reactivation.

Wait for explicit instruction from Andrew before any further ACE work.
