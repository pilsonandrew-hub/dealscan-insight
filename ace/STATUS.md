# ACE 1.0 Status

Date: 2026-05-19
Current commit: `0eace9e ace: enforce item provenance uniqueness`

ACE 1.0 is a local governed resident foundation for turning bounded operator work into auditable item lifecycle records. It runs under launchd, keeps a local SQLite-backed item/event ledger, records append-only event hashes, ingests direct Telegram work through the bounded OpenClaw session-stream path, routes ACE/JACE outbound operator status through the dedicated JACE Telegram Bot API path, and can move explicitly eligible or narrowly bounded internal work through the governed lifecycle to verified completion.

ACE remains a governed-foundation system, not a broad V1 platform/runtime fabric. The current direction is broad autonomous operating-layer hardening through narrow, proven, durable seams.

## What ACE 1.0 does

ACE 1.0 can:

- create and track governed work items with item state, source, session, evidence, obligations, contradictions, confidence tier, verdict metadata, and closeout metadata;
- enforce database-level provenance uniqueness for non-null `(source, source_session)` and re-read existing rows on duplicate provenance instead of creating duplicate item/event rows;
- ingest bounded direct-work messages from Telegram through the OpenClaw session stream with bounded tail reads (`ACE_OPENCLAW_SESSION_TAIL_LINES`) to avoid unbounded session-history scans;
- coalesce duplicate semantic Telegram direct-work messages and record duplicate evidence without creating repeated work items;
- parse operator-directive style Telegram work with a deterministic bounded marker corpus;
- default broad Telegram direct work to governed execution instead of automatic autonomy; only bounded operator-continuation directives receive automatic autonomy eligibility;
- preserve Telegram intake evidence, parser evidence, autonomy-eligibility evidence, execution evidence, correction evidence, closeout evidence, and JACE delivery evidence;
- plan governed execution for non-autonomy broad direct work and keep it blocked until execution result or escalation evidence exists;
- autonomously execute only bounded ACE-owned internal inspection work through `run_governed_execution`, writing `ace://governed-execution/result` evidence, resolving the governed-execution obligation, and closing only passing inspections;
- drain a bounded local action queue for safe local evidence-recording actions (`record_operator_followup`, `record_operator_rejection`) while intentionally excluding external notification delivery actions from automatic dispatch;
- run a launchd-managed local cycle that ingests, processes eligible work, executes bounded governed inspections, drains bounded local queue actions, sweeps, briefs, and records governed run status;
- prevent concurrent governed cycles from silently overlapping;
- reconcile stale launchd cycle runs after interruption;
- route ACE operator notifications through the dedicated JACE-owned Telegram Bot API path when `ACE_NOTIFICATION_CHANNEL=jace`, with local `alert_log` and evidence proof;
- maintain a resident supervisor runtime with heartbeat/status inspection and recorded restart recovery evidence;
- accept explicit supervisor shutdown during `starting` as well as `live`, so early-start resident runtimes can terminalize cleanly;
- survive a bounded machine sleep/wake proof while preserving supervisor continuity, hash-chain integrity, cycle integrity, state integrity, and post-wake cycle execution;
- enforce closeout gates requiring supporting evidence, no open blocking obligations/contradictions, and acceptable verdicts;
- persist terminal closeout metadata (`closed_at`, `closed_by`, `closed_reason`) for `VERIFIED_DONE` items;
- compute drift dimensions currently surfaced as `loop_depth`, `decision_drift`, and `claim_drift`;
- compute autonomy verdicts from composite drift score using bounded `ship`, `monitor`, `review`, and `block` thresholds;
- enforce first-pass local cost guardrails using a SQLite-backed usage ledger and deterministic local cost/token/session limits;
- verify governed audit integrity with `ace audit verify`, including event hash chain, evidence-row consistency, governed-run integrity, and runtime-instance integrity.

## What ACE 1.0 does not do

ACE 1.0 does not provide broad natural-language understanding. Telegram direct-work intake is parser-bounded and keyword-bounded.

ACE 1.0 parser breadth is scoped to operator-directive messages sent to ACE. Commitment self-statements such as “I’ll X” / “need to Y” and deadline-only patterns such as “by Friday” are not in the current 1.0 parser scope. If ACE later ingests non-operator conversations such as Slack channels or multi-party chats, those markers should be added as a separate slice.

ACE 1.0 does not treat raw Telegram Bot API polling as a broad inbound ownership claim. Current inbound intake remains the bounded OpenClaw session-stream path; outbound JACE/operator status delivery is independently owned by ACE/JACE through `@JACEthaACE_Bot` and local `ace/state/ace-telegram.env` token material.

ACE 1.0 does not integrate with external billing providers or automatically measure model-provider spend. The current cost guardrails are local deterministic guardrails only.

ACE 1.0 does not claim broad platform autonomy, broad source authenticity, distributed runtime fabric, or general-purpose agent orchestration. It is a local governed foundation with bounded proven seams.

## Current hardening proof status

- JACE outbound status ownership: PASS. Dedicated `ace jace-status-send` uses the JACE Telegram Bot API token from ignored local env, records `alert_log` transport proof, and writes `ace://jace/outbound-status-delivery` evidence. Live proof delivered Telegram `message_id=8` from `JACEthaACE_Bot`.
- JACE notification routing: PASS. `ACE_NOTIFICATION_CHANNEL=jace` routes operator notification execution through the dedicated JACE Bot API path instead of the OpenClaw-mediated sender, while preserving durable evidence.
- Telegram direct-work duplicate coalescing: PASS. Semantic direct-work keying prevents repeated identical operator directives from creating duplicate work items and records `ace://telegram/duplicate-direct-work` evidence.
- Telegram autonomy boundary: PASS. Broad direct work is governed by default; only bounded continuation directives are automatically autonomy-eligible.
- Governed execution planning/resolution: PASS. Broad governed work receives plan evidence and remains blocked until result or escalation evidence exists.
- Bounded governed inspection executor: PASS. Commit `b0f7085 ace: execute bounded governed inspections`; live launchd proof item `item_c72e9f1f2ba44ecc8b6abd6b72336ac6`, obligation `obligation_acd5c8d01c0a4ddd91aa80988afaa681`, run `run_94444bfd55974d62b42d86bfeaae85e6`, result evidence `evidence_01b90bfe2ad947b5b6714dc43a61d0b0`, no noisy JACE notification.
- Bounded local action queue dispatcher: PASS. Commit `214be78 ace: dispatch bounded local action queue`; live launchd proof item `item_3c05e6ffd4244701b06537e721a32624`, action `action_66d3458bb86002aabc10fa918081d9f27f3dd506ba37f4fd438bfd44b6c7a4b3`, run `run_1d355b376e9e436eb222b392a4618d4a`, evidence `evidence_85b6acc41eb94c14aef1fb95a4699aae`, zero notification delivery evidence and zero `alert_log` rows in the proof window.
- Item provenance uniqueness: PASS. Commit `0eace9e ace: enforce item provenance uniqueness`; SQLite partial unique index `idx_items_source_session_unique` enforces non-null `(source, source_session)` uniqueness and repository duplicate creation re-reads the existing row without duplicate item/event writes.
- Supervisor starting-shutdown seam: PASS. Explicit shutdown is accepted while a runtime is `starting`, not only after `live`.
- Local cost guardrails: PASS for deterministic local ledger / cycle fail-closed guardrails.
- Bounded network-loss proof on the current OpenClaw session-stream path: PASS for the accepted current path; this is not a raw Bot API or broad platform-network claim.
- Sleep/wake resilience: PASS. Evidence commit: `b9921fe ace: record item 3 sleep wake proof rerun`; artifact: `/tmp/ace-item3-sleep-wake-proof-20260515T055227Z.json`.
- Bounded Telegram parser breadth: PASS. Evidence commit: `f88cdeb ace: widen bounded telegram parser breadth`.
- Audit verify integrity extension: PASS. Evidence commit: `9fb349e ace: extend audit verify integrity checks`.

## Deferred to 1.x

Deferred work includes:

- adding a `retry_rate` drift dimension;
- extending cost guardrails beyond the local ledger into real provider spend attribution and richer runaway-session controls;
- broadening or replacing the keyword-bounded Telegram parser beyond operator-directive messages;
- deciding whether future ingestion expansion should use an OpenClaw-mediated queue/webhook or another owned intake surface;
- resolving raw Telegram Bot API inbound ownership without shared-token `getUpdates` conflict;
- reviewing deprecated Phase 1 / recovery / resume modules before removal or replacement.

## Current verification posture

As of this status file, the latest committed source is `0eace9e ace: enforce item provenance uniqueness`.

Latest verification observed:

- Commit hash: `0eace9e ace: enforce item provenance uniqueness`.
- Git status: ACE source clean after the commit; workspace root may show unrelated private memory logging changes.
- Full ACE suite passes: `Ran 593 tests in 65.257s — OK`.
- `python3 -m ace.ace audit verify` reports `event_hash_chain=ok`, `evidence_consistency=ok`, `governed_run_integrity=ok`, and `runtime_instance_integrity=ok`.
- Latest terminal launchd cycle: `run_1d355b376e9e436eb222b392a4618d4a`, `trigger_kind=launchd`, `status=completed`, no notification action/evidence.

Going forward, ACE clean-commit claims require five pieces of evidence: commit hash, git status, full local test suite, hash/audit verification, and live runtime/cycle status. CI status should be included when the change is pushed and CI is available.
