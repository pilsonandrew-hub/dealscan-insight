# A.C.E. Next V1 Gates — Telegram, Sleep/Network, Runtime Fabric

Date: 2026-05-13
Current source baseline: `430b88b`

## Current verified state

A.C.E. is clean at the governed-foundation gate, not V1.

Verified after the latest hardening pass:

- ACE source HEAD: `430b88b`
- Event hash chain: `(True, None)`
- Supervisor runtime: live (`runtime_6cc9ef9fe5f44c5eb3b2203a80ab3d40`)
- Latest governed run observed: completed, `trigger_kind=operator`
- Full ACE suite with warnings as errors: `506 tests OK`
- Telegram runtime DB exists with:
  - `processed_telegram_messages`
  - `telegram_transport_attempts`
  - `telegram_transport_offsets`
- Missing-token/no-inbox raw Telegram path is observable: records `telegram_transport_attempts(status=disabled,error_type=missing_bot_token)`
- Governed raw Telegram token source, TLS trust-store handling, Bot API offset persistence, and transport-offset-aware backlog checkpointing are implemented and source-tested.
- Governed cycle single-flight protection is implemented: concurrent cycle attempts record `status=skipped`, `failure_code=cycle_already_active` instead of executing concurrently.

## Gate 1 — Raw live Telegram Bot API polling acceptance

### Current truth

Partially proven, still not fully earned.

OpenClaw has a Telegram bot token configured in `~/.openclaw/openclaw.json`. A.C.E. now supports a governed no-secret token source switch (`ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN=true`) that reads the existing OpenClaw Telegram bot token at runtime without committing the secret.

Controlled fetch proof has shown Telegram can be reached, TLS trust-store handling can succeed, first-run Bot API backlog can be checkpointed rather than returned for ingestion, and `telegram_transport_offsets.next_offset` can persist.

The remaining acceptance gap is a full launchd-cycle proof with raw polling enabled and all side effects accounted for.

### Required before enabling

1. Token source must be explicit and governed.
   - Either an A.C.E.-specific token env var is installed into launchd, or an audited adapter intentionally reads the OpenClaw Telegram token.
   - No secret should be committed to git.

2. Backlog safety must be proven before first live poll.
   - `ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED=true` must be active on first runtime poll.
   - `processed_telegram_messages` must be preserved.
   - `telegram_transport_offsets` must be used after successful Bot API fetches.

3. Acceptance proof must be controlled.
   - Use a single controlled Telegram message or a known no-message poll window.
   - Verify `telegram_transport_attempts` records `status=ok` or explicit API failure.
   - Verify offset row persists when update IDs are returned.
   - Verify no backlog flood occurs.
   - Verify event hash chain after cycle.

### Pass criteria

- Live launchd cycle runs with `ACE_TELEGRAM_BOT_TOKEN` present.
- Bot API transport attempt is recorded durably.
- If updates exist, only new eligible messages are ingested; existing backlog is checkpointed or ignored safely.
- `telegram_transport_offsets.next_offset` persists after successful updates.
- A controlled direct-work message reaches `VERIFIED_DONE`, or a controlled no-message poll records a successful no-update attempt without side effects.
- Full ACE test suite passes under `PYTHONWARNINGS=error` after the live proof.
- Event hash chain remains `(True, None)`.

### Fail criteria

- Any silent return when raw Bot API is expected.
- Backlog ingestion without explicit consent.
- Missing durable attempt row.
- Offset not persisted after update IDs.
- Notification side effects not accounted for.

## Gate 2 — Sleep/network resilience proof

### Current truth

Unearned.

No live sleep/wake or network interruption acceptance run has been executed and proven.

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

Next best engineering action: finish Gate 1 with a controlled launchd-cycle raw Telegram acceptance proof. A.C.E. already has the governed no-secret token source switch (`ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN=true`), TLS trust-store handling, Bot API offset persistence, and backlog checkpointing. The remaining bar is launchd-cycle integration without backlog flood, unaccounted notification side effects, stuck governed runs, or hash-chain/test regressions.
