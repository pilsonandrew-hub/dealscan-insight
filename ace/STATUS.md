# ACE 1.0 Status

Date: 2026-05-14
Current commit: `5d0e153 ace: add audit verify cli`

ACE 1.0 is a local governed resident foundation for turning bounded operator work into auditable item lifecycle records. It runs under launchd, keeps a local SQLite-backed item/event ledger, records append-only event hashes, ingests direct Telegram work through the proven OpenClaw session-stream path, and can move explicitly eligible work through the governed lifecycle to verified completion.

## What ACE 1.0 does

ACE 1.0 can:

- create and track governed work items with item state, source, session, evidence, obligations, contradictions, confidence tier, and verdict metadata;
- ingest bounded direct-work messages from Telegram through the OpenClaw session stream;
- preserve Telegram intake evidence, parser evidence, autonomy-eligibility evidence, execution evidence, and closeout evidence;
- run a launchd-managed local cycle that sweeps, briefs, ingests, processes eligible work, and records governed run status;
- prevent concurrent governed cycles from silently overlapping;
- reconcile stale launchd cycle runs after interruption;
- maintain a resident supervisor runtime with heartbeat/status inspection and recorded restart recovery evidence;
- enforce closeout gates requiring supporting evidence and acceptable verdicts;
- compute drift dimensions currently surfaced as `loop_depth`, `decision_drift`, and `claim_drift`;
- compute autonomy verdicts from composite drift score using bounded `ship`, `monitor`, `review`, and `block` thresholds;
- verify the append-only event hash chain with `ace audit verify`.

## What ACE 1.0 does not do

ACE 1.0 does not provide broad natural-language understanding. Telegram direct-work intake is parser-bounded and keyword-bounded.

ACE 1.0 does not use raw Telegram Bot API polling in production. Shared-token Bot API polling conflicts with OpenClaw's Telegram ownership, so production intake uses the OpenClaw session stream.

ACE 1.0 does not have cost guardrails such as token-spend circuit breakers, runaway-session cutoffs, or budget-aware autonomy throttles.

ACE 1.0 does not have a cleanly proven full network-loss resilience gate. A network interruption test exposed and led to a stale-cycle recovery fix, but that is not the same as a clean network-loss pass.

ACE 1.0 does not claim broad platform autonomy, broad source authenticity, or general-purpose agent orchestration. It is a local governed foundation with bounded proven seams.

## Deferred to 1.x

Deferred work includes:

- adding a `retry_rate` drift dimension;
- adding cost guardrails and runaway-session controls;
- broadening or replacing the keyword-bounded Telegram parser;
- completing a clean sleep/wake and network-loss resilience proof;
- deciding whether future ingestion expansion should use an OpenClaw-mediated queue/webhook or another owned intake surface;
- reviewing deprecated Phase 1 / recovery / resume modules before removal or replacement.

## Current verification posture

As of this status file, the latest committed source is `5d0e153 ace: add audit verify cli`. The next commit after this file should contain only this `STATUS.md` addition.
