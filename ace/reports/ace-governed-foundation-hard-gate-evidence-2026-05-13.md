# A.C.E. Governed-Foundation Hard Gate Evidence — 2026-05-13

## Verdict

PASS at the current governed-foundation level.

FAIL / UNEARNED for V1, V2, V3, broad platform/runtime-fabric, daemon/service proof, sleep/network resilience, and raw live Telegram Bot API polling acceptance.

This document is intentionally blunt: it separates verified source/runtime truth from future proof gates.

## Verified source/runtime truth

- Source HEAD: `430b88b` (`ace: serialize governed cycle execution`)
- Supervisor runtime: `runtime_6cc9ef9fe5f44c5eb3b2203a80ab3d40`
- Supervisor status: live under launchd, current heartbeat present at `2026-05-13T13:19:06.531710Z`
- Latest governed run: `run_808ac9dba1fa46cbb848e859e2a2402e`
- Latest governed run trigger: `operator`
- Latest governed run status: `completed`
- Event hash chain: `PASS` with `(True, None)`
- Full ACE suite: `PYTHONWARNINGS=error python3 -m unittest discover ace/tests` => `506 tests OK`
- V2 Telegram direct-work certification: `PASS` for `telegram:7529788084:33604`
- Active false V1/platform claims: none found in active ACE source; existing V1/platform/service/fabric mentions are explicit negative boundaries.

## Real fixes landed in this hardening sequence

- Required persisted pass verdict before closeout.
- Added tamper-evident event hash chain.
- Serialized SQLite event hash appends to fix race-created broken chains.
- Ignored SQLite runtime journal residue instead of deleting live state files.
- Exported `ACE_OPENCLAW_CHAT_ID` from the launchd cycle wrapper based on operator Telegram target.
- Added first-run Telegram backlog checkpointing so old messages are marked processed rather than backfilled.
- Added durable Telegram transport diagnostics in `telegram_transport_attempts`.
- Added durable Telegram Bot API update offsets in `telegram_transport_offsets`.
- Fixed missing-token/no-inbox raw Telegram path so it records `status=disabled`, `error_type=missing_bot_token` instead of silently returning nothing.
- Added governed raw Telegram polling proof support using the governed OpenClaw token source switch, TLS trust-store handling, Bot API offset persistence, and transport-offset-aware first-run backlog checkpointing.
- Added a single-flight governed cycle boundary: concurrent cycle attempts now record an auditable `skipped` governed run with `failure_code=cycle_already_active` instead of executing concurrently.

## Current Telegram runtime evidence

Runtime DB: `ace/state/telegram_runtime.db`

Tables verified present:

- `processed_telegram_messages`
- `telegram_transport_attempts`
- `telegram_transport_offsets`

Current live state after hardening:

- `processed_telegram_messages`: nonzero entries, proving checkpoint state exists.
- `telegram_transport_attempts`: records disabled state when raw Bot API token is not configured and no local inbox source is configured.
- `telegram_transport_offsets`: table exists; rows appear only after successful raw Bot API fetches with update IDs.

## Blocked / unearned proof gates

These are not source-pass claims and must not be rounded up:

1. Raw live Telegram Bot API polling acceptance
   - Current status: partially proven as a controlled fetch/backlog-safety transport proof, still not fully earned as a live launchd-cycle acceptance proof.
   - Evidence earned: governed OpenClaw token source can fetch Telegram Bot API updates without committing the secret; TLS trust-store handling works; first raw Bot API backlog is checkpointed rather than returned for ingestion; `telegram_transport_offsets.next_offset` persists.
   - Remaining proof: run a controlled launchd-cycle acceptance with raw polling enabled, no backlog flood, no unaccounted notification side effects, and a post-cycle hash-chain/test gate.

2. Sleep/network-blip resilience
   - Blocker: no acceptance run has been executed/proven for sleep/wake or network interruption recovery.
   - Required future proof: controlled interruption test with pre/post runtime state and event-hash verification.

3. Broad V1/V2/V3/platform/runtime-fabric claims
   - Blocker: current A.C.E. remains a governed foundation / Phase 0 continuity substrate with narrow local-only proven seams.
   - Missing: generalized runtime fabric, worker/scheduler control-plane ownership, broader continuity orchestration, LLM logic, production deployment semantics, distributed/high-availability behavior.

## Cleanliness boundary

A.C.E. source is clean at commit `430b88b`.

The only dirty workspace item observed during this gate was runtime memory (`MEMORY.md` / daily log), which is not an A.C.E. source failure.

## Final truth statement

Clean, tried, tested governed-foundation A.C.E.: PASS.

A.C.E. V1/V2/V3: FAIL / UNEARNED until the proof gates above are completed with live evidence.
