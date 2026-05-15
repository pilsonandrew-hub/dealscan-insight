# ACE 1.0 Status

Date: 2026-05-15
Current commit: `9fb349e ace: extend audit verify integrity checks`

ACE 1.0 is a local governed resident foundation for turning bounded operator work into auditable item lifecycle records. It runs under launchd, keeps a local SQLite-backed item/event ledger, records append-only event hashes, ingests direct Telegram work through the proven OpenClaw session-stream path, and can move explicitly eligible work through the governed lifecycle to verified completion.

ACE remains a governed-foundation system, not a broad V1 platform/runtime fabric.

## What ACE 1.0 does

ACE 1.0 can:

- create and track governed work items with item state, source, session, evidence, obligations, contradictions, confidence tier, verdict metadata, and closeout metadata;
- ingest bounded direct-work messages from Telegram through the OpenClaw session stream;
- parse operator-directive style Telegram work with a deterministic bounded marker corpus;
- preserve Telegram intake evidence, parser evidence, autonomy-eligibility evidence, execution evidence, correction evidence, and closeout evidence;
- run a launchd-managed local cycle that sweeps, briefs, ingests, processes eligible work, and records governed run status;
- prevent concurrent governed cycles from silently overlapping;
- reconcile stale launchd cycle runs after interruption;
- maintain a resident supervisor runtime with heartbeat/status inspection and recorded restart recovery evidence;
- survive a bounded machine sleep/wake proof while preserving supervisor continuity, hash-chain integrity, cycle integrity, state integrity, and post-wake cycle execution;
- enforce closeout gates requiring supporting evidence and acceptable verdicts;
- persist terminal closeout metadata (`closed_at`, `closed_by`, `closed_reason`) for `VERIFIED_DONE` items;
- compute drift dimensions currently surfaced as `loop_depth`, `decision_drift`, and `claim_drift`;
- compute autonomy verdicts from composite drift score using bounded `ship`, `monitor`, `review`, and `block` thresholds;
- enforce first-pass local cost guardrails using a SQLite-backed usage ledger and deterministic local cost/token/session limits;
- verify governed audit integrity with `ace audit verify`, including event hash chain, evidence-row consistency, governed-run integrity, and runtime-instance integrity.

## What ACE 1.0 does not do

ACE 1.0 does not provide broad natural-language understanding. Telegram direct-work intake is parser-bounded and keyword-bounded.

ACE 1.0 parser breadth is scoped to operator-directive messages sent to ACE. Commitment self-statements such as “I’ll X” / “need to Y” and deadline-only patterns such as “by Friday” are not in the current 1.0 parser scope. If ACE later ingests non-operator conversations such as Slack channels or multi-party chats, those markers should be added as a separate slice.

ACE 1.0 does not use raw Telegram Bot API polling in production. Shared-token Bot API polling conflicts with OpenClaw's Telegram ownership, so production intake uses the OpenClaw session stream.

ACE 1.0 does not integrate with external billing providers or automatically measure model-provider spend. The current cost guardrails are local deterministic guardrails only.

ACE 1.0 does not claim broad platform autonomy, broad source authenticity, distributed runtime fabric, or general-purpose agent orchestration. It is a local governed foundation with bounded proven seams.

## Recent hardening proof status

- Item 1 — local cost guardrails: PASS for deterministic local ledger / cycle fail-closed guardrails.
- Item 2 — bounded network-loss proof on the current OpenClaw session-stream path: PASS for the accepted current path; this is not a raw Bot API or broad platform-network claim.
- Item 3 — sleep/wake resilience: PASS. Evidence commit: `b9921fe ace: record item 3 sleep wake proof rerun`; artifact: `/tmp/ace-item3-sleep-wake-proof-20260515T055227Z.json`.
- Item 4 — bounded Telegram parser breadth: PASS. Evidence commit: `f88cdeb ace: widen bounded telegram parser breadth`.
- Item 5 — audit verify integrity extension: PASS. Evidence commit: `9fb349e ace: extend audit verify integrity checks`.

## Deferred to 1.x

Deferred work includes:

- adding a `retry_rate` drift dimension;
- extending cost guardrails beyond the local ledger into real provider spend attribution and richer runaway-session controls;
- broadening or replacing the keyword-bounded Telegram parser beyond operator-directive messages;
- deciding whether future ingestion expansion should use an OpenClaw-mediated queue/webhook or another owned intake surface;
- resolving raw Telegram Bot API ownership without shared-token `getUpdates` conflict;
- reviewing deprecated Phase 1 / recovery / resume modules before removal or replacement.

## Current verification posture

As of this status file, the latest committed source is `9fb349e ace: extend audit verify integrity checks`.

Latest verification observed:

- `python3 -m ace.ace audit verify` reports `event_hash_chain=ok`, `evidence_consistency=ok`, `governed_run_integrity=ok`, and `runtime_instance_integrity=ok`.
- Full ACE suite passes: `Ran 564 tests ... OK`.
