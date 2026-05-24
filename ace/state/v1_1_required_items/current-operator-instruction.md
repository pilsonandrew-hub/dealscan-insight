# Current Operator Instruction

Authority: this file is the durable operator scope anchor. The bot does not edit this file except by explicit operator instruction. Operator (Andrew) updates it via explicit instruction. Chat-level conflicts lose to this file.

Last updated: 2026-05-24 by operator authorization after V1.1 code-side acceptance.

## Mode

investigation_only — paused for operator activation phase.

## Current state

V1.1 code-side work is complete and accepted:

- Item 1 (three-layer event lockdown) — done
- Item 2 (external attestation through Slice I6) — done
- Item 3 (operator scope enforcement) — done
- Cutover executed at `evt_58b80e6282374bf2b1a8611963817aa2`
- 721 tests passing
- CI green at `c8a08e7`
- Working tree clean except pre-existing `unused.db`

## Authorized work

No code changes authorized.

No scope work authorized.

No implementation work authorized.

The assistant is waiting for Andrew to complete operator activation on his own machine and report back.

## Operator-only actions

The assistant must not initiate operator activation work and must not modify:

- hooks
- PATH
- OS accounts
- environment files
- GitHub settings
- operator-owned configuration

These are operator-only actions.

## Remaining allowed future action

After Andrew reports operator activation complete and explicitly authorizes it, the only remaining commit is the ACE 1.0 re-tag action.

## Required behavior

Stop after this anchor reset commit is pushed and CI is green.
