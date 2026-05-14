# A.C.E. Raw Telegram Shared-Token Conflict Evidence

Date: 2026-05-14
Baseline: `ecd2aa5 ace: add explicit telegram transport selector`

## Verdict

A.C.E. raw Telegram Bot API polling with the shared OpenClaw Telegram bot token is **blocked**.

This is not a missing-token defect anymore. The governed token source successfully reached Telegram. Telegram rejected `getUpdates` with a conflict because another consumer is already polling the same bot token.

A.C.E. remains below V1 / not V1 from this proof.

## Evidence

Live re-ground before this report:

- Workspace git: clean except memory/runtime logging outside ACE source.
- ACE git: clean.
- ACE HEAD: `ecd2aa5 ace: add explicit telegram transport selector`.
- Launchd production cycle config was restored to the safe default path and does **not** leave raw Bot API polling enabled.
- Event hash chain verification: `(True, None)`.

Durable `telegram_transport_attempts` row from the controlled launchd-managed proof:

```text
transport=telegram_bot_api
status=error
message_count=0
error_type=telegram_conflict
error_summary=Telegram getUpdates conflict: another consumer is polling this bot token.
```

The launchd proof temporarily supplied:

```text
ACE_TELEGRAM_TRANSPORT=telegram_bot_api
ACE_USE_OPENCLAW_TELEGRAM_BOT_TOKEN=true
ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED=true
```

This removed the earlier missing-token condition but exposed the real single-consumer boundary.

## Root cause

Telegram Bot API `getUpdates` is single-consumer. OpenClaw already owns the configured Telegram bot token for live inbound Telegram chat handling. A.C.E. cannot safely long-poll that same token on a schedule without conflicting with OpenClaw.

## Truth boundary

Earned:

- Controlled raw Bot API probe can reach Telegram using the governed OpenClaw token source.
- Bot API attempts are recorded durably.
- Bot API conflict is recorded durably instead of silently returning no work.
- Production launchd cycle was rolled back to the safe OpenClaw-session/default path.
- Event hash chain remains valid.

Not earned:

- Scheduled raw Telegram Bot API polling with the shared OpenClaw bot token.
- Live inbound Telegram message processing through raw polling.
- Sleep/network resilience.
- Broad V1/platform/runtime-fabric claim.

## Decision boundary

One of these must be chosen before raw polling can be made a valid acceptance gate:

1. **Dedicated A.C.E. Telegram bot/token**
   - A.C.E. owns `getUpdates` for its own bot.
   - OpenClaw keeps its current Telegram bot and session stream.
   - This is the cleanest ownership model for raw Bot API polling.

2. **Keep A.C.E. on the OpenClaw session stream**
   - A.C.E. treats OpenClaw as the Telegram transport owner.
   - Raw Bot API polling with the shared OpenClaw token is removed from near-term acceptance.
   - Future transport proof focuses on session-stream ingestion, backlog safety, cycle closure, and explicit degradation.

3. **OpenClaw-mediated handoff / webhook queue**
   - OpenClaw remains Telegram owner.
   - A.C.E. receives a governed queue/webhook/event handoff.
   - This avoids Telegram `getUpdates` conflict while keeping A.C.E. input event provenance explicit.

## Recommendation

Do **not** enable scheduled raw Bot API polling with the shared OpenClaw Telegram bot token.

For V1-grade transport ownership, prefer either:

- dedicated A.C.E. bot/token, or
- explicitly scope A.C.E. Telegram intake to the OpenClaw session stream and stop treating shared-token raw polling as a pass/fail V1 gate.
