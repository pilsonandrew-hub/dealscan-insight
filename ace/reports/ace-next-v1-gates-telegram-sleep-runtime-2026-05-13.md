# A.C.E. Next V1 Gates — Telegram, Sleep/Network, Runtime Fabric

Date: 2026-05-13
Current source baseline: `430b88b`

## Current verified state

A.C.E. is clean at the governed-foundation gate, not V1.

This report was originally written against source baseline `430b88b`. Later hardening and CI reconciliation supersede several operational details below. Current tracked truth as of `f32ea73 ace: record ci-green verification posture`:

- ACE Items 1–5 are PASS at the governed-foundation level.
- ACE CI is green on master for `f32ea73`: https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/25916758062.
- Full ACE suite passes locally: `Ran 564 tests ... OK`.
- `ace audit verify` reports `event_hash_chain=ok`, `evidence_consistency=ok`, `governed_run_integrity=ok`, and `runtime_instance_integrity=ok`.
- Item 3 sleep/wake resilience proof passed on the accepted bounded path with artifact `/tmp/ace-item3-sleep-wake-proof-20260515T055227Z.json`.
- Item 4 parser breadth passed for operator-directive Telegram messages only.
- Shared-token raw Telegram Bot API polling is blocked by Telegram `getUpdates` single-consumer ownership conflict with OpenClaw. See `ace/reports/ace-raw-telegram-shared-token-conflict-2026-05-14.md`.
- Governed cycle single-flight protection is implemented: concurrent cycle attempts record `status=skipped`, `failure_code=cycle_already_active` instead of executing concurrently.

## Gate 1 — Telegram transport ownership acceptance

### Current truth

Raw live Telegram Bot API polling with the shared OpenClaw Telegram bot token is blocked and must not be treated as a near-term pass/fail V1 gate.

OpenClaw has a Telegram bot token configured in `~/.openclaw/openclaw.json`. A.C.E. supports a governed no-secret token source switch (`ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN=true`) that can read that token without committing the secret. Controlled probing proved Telegram can be reached and raw Bot API attempts are durably recorded.

The decisive later proof showed the shared token cannot be safely long-polled by A.C.E.: Telegram returns a `telegram_conflict` because OpenClaw already owns polling for that bot token. Production intake therefore remains on the OpenClaw session-stream path.

### Valid future options

Before raw polling can be an acceptance target, choose one ownership model:

1. Dedicated A.C.E. Telegram bot/token.
   - A.C.E. owns `getUpdates` for its own bot.
   - OpenClaw keeps ownership of the current Telegram bot/session stream.

2. OpenClaw-mediated handoff / queue / webhook.
   - OpenClaw remains Telegram owner.
   - A.C.E. receives governed handoff events with explicit provenance.

3. Explicitly keep A.C.E. on OpenClaw session-stream intake.
   - Raw Bot API polling with the shared token is removed from the V1 acceptance path.
   - Future proof focuses on session-stream ingestion, backlog safety, cycle closure, and explicit degradation.

### Pass criteria for any future transport gate

- Transport ownership is explicit and non-conflicting.
- No secret is committed to git.
- Transport attempts and failures are durably recorded.
- No backlog flood occurs.
- A controlled direct-work message reaches `VERIFIED_DONE`, or a controlled no-message/no-work interval records a successful no-side-effect attempt.
- Full ACE suite passes after the live proof.
- `ace audit verify` remains green.
- GitHub ACE CI is green for the committed change.

### Fail criteria

- Any silent return when transport work is expected.
- Shared-token `getUpdates` conflict.
- Backlog ingestion without explicit consent.
- Missing durable attempt row.
- Offset/handoff state not persisted when applicable.
- Notification side effects not accounted for.

## Gate 2 — Sleep/network resilience proof

### Current truth

Partially earned at the bounded governed-foundation level, not broadly earned.

Item 3 sleep/wake resilience passed on the accepted bounded path. That proof accepts either same-runtime sleep survival with advancing heartbeat or prior-runtime failure/replacement, and verifies supervisor continuity, hash-chain integrity, cycle integrity, state integrity, post-wake cycle execution, and the full ACE test suite.

Item 2 bounded network-loss proof passed on the current OpenClaw session-stream path. This is not a raw Bot API or broad platform-network claim.

### Required proof

- Establish pre-interruption supervisor/runtime state.
- Introduce controlled sleep/wake or network interruption.
- Confirm launchd supervisor recovers or remains live.
- Confirm governed run lifecycle does not create contradictory state.
- Confirm event hash chain remains valid.
- Confirm any transport failure is observable, not silent.

### Pass criteria

- Pre/post runtime state recorded.
- No broken hash chain.
- No stuck startup/shutdown status.
- No silent transport failure.
- Full ACE tests still pass after recovery.

## Gate 3 — V1 runtime-fabric criteria

### Current truth

Unearned.

A.C.E. remains a governed foundation / Phase 0 continuity substrate with narrow local-only proven seams.

### Minimum V1 criteria to define before implementation

A.C.E. V1 cannot be claimed until at least these are specified and proven:

1. Runtime ownership
   - What processes A.C.E. owns.
   - What launchd owns.
   - What OpenClaw owns.
   - What is merely observed.

2. Transport ownership
   - Telegram direct-work via OpenClaw session stream.
   - Raw Telegram Bot API polling.
   - Disabled/degraded transport states.

3. Failure semantics
   - Retry boundaries.
   - Disabled states.
   - Operator notification boundaries.
   - No silent failure paths.

4. Recovery semantics
   - Supervisor recovery.
   - Cycle interruption recovery.
   - Sleep/network interruption behavior.
   - Hash-chain preservation.

5. Claims boundary
   - Explicit distinction between local governed runtime, daemon/service, platform, runtime fabric, and distributed/high-availability claims.

## Current recommendation

Do not call A.C.E. V1.

Do not pursue shared-token raw Telegram Bot API polling as a near-term gate. The next valid transport decision is one of: dedicated A.C.E. bot/token, OpenClaw-mediated handoff, or explicitly keeping the OpenClaw session-stream path as the governed transport boundary.

For any future ACE clean-commit or gate claim, require five pieces of evidence: commit hash, git status, full local ACE suite, `ace audit verify`, and green GitHub ACE CI.
