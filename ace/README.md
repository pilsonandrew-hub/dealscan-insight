# Super A.C.E. — Governed Foundation

> **Authority status note — 2026-05-05**
> Current canonical status: **Super A.C.E. is a governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams. It is not V1.**
>
> Primary authority surfaces:
> - `ace/README.md`
> - `reports/ace-governance-v1-hard-gate-and-gap-register-2026-04-26.md`
> - `reports/ace-enterprise-status-verdict-2026-05-05.md`
> - `reports/ace-phase-truth-matrix-2026-05-05.md`
>
> Documents under `reports/ace-phase*`, `reports/ace-v1-*`, and older planning/scorecard artifacts are not current-status authority unless they explicitly state they are a hard gate, blocker, gap register, or historical artifact.

Super A.C.E. is currently best described as a governed foundation / Phase 0 continuity substrate for DealerScope work, with two narrow local-only Phase 1 closed-loop proofs, two narrow local-only Phase 2 action-runtime proofs, two narrow local-only Phase 3 resume/recovery proofs, two narrow local-only Phase 4 runtime-ownership proofs, one narrow local-only Phase 7A cross-seam owned-recovery lifecycle proof, one narrow local-only Phase 9A ownership interruption replay-durability proof, one narrow local-only Phase 9B recovery interruption replay-durability proof, and one narrow local-only Phase 11 owned-recovery cross-surface interrupted-success ordering proof.

## What this slice provides

- `ace/` package skeleton
- SQLite bootstrap at `ace/state/ace.db`
- append-only event logging
- explicit item state transitions with loud failure on illegal moves
- a minimal item repository
- read-only continuity/open-loops ingest proof into a temp ACE DB with deterministic provenance and replay reuse
- read-only continuity/pending-promotions ingest proof into ACE TRIAGE for pending rows only, with deterministic provenance and replay reuse
- local-only Phase 1 closed-loop proof that reuses pending-promotions ingest, writes one ACE-owned decision evidence row per pending item, and stays replay-safe without queue or continuity-source writes
- local-only Phase 1B closed-loop proof that reuses open-loops ingest, derives a bounded severity-based decision from original source rows, writes one ACE-owned decision evidence row per eligible item, and stays replay-safe without continuity-source writes
- local-only Phase 2 action-runtime proof that reuses the existing `action_queue` surface for one bounded ACE-owned lifecycle (`record_operator_followup`), proves queued/claimed/completed-or-failed semantics, writes only `ace://phase2/action-outcome` evidence, and stays replay-safe without continuity-source writes
- local-only Phase 2B action-runtime proof that reuses the same bounded `action_queue` seam for a materially different ACE-owned lifecycle (`record_operator_rejection`), proves deterministic queued/claimed/completed-or-failed semantics, writes only `ace://phase2/action-rejection` evidence, and stays replay-safe without continuity-source writes
- local-only Phase 3 resume/recovery proof that reuses existing `sessions` and `resume_candidates` surfaces for deterministic session registration, deterministic candidate registration, replay-safe claim semantics, bounded recovery completion, and explicit stale-target failure without continuity-source writes
- local-only Phase 3B bounded recovery proof that reuses the same `sessions` and `resume_candidates` seam for deterministic selection/dismissal behavior, replay-safe completion semantics, and explicit stale-target failure without continuity-source writes
- local-only Phase 4 runtime-ownership proof that reuses the existing `action_queue` surface for deterministic ownership registration, replay-safe claim/release semantics, bounded local outcome evidence, and explicit missing-target failure without continuity-source writes
- local-only Phase 4B runtime-ownership proof on the same bounded seam that treats malformed or invalid persisted ownership payload during release as a durable explicit failed outcome, writes no success evidence, and remains replay-safe without continuity-source writes
- local-only Phase 7A cross-seam owned-recovery lifecycle proof that composes the bounded ownership and recovery seams for the same work item, proves a replay-safe claimed-ownership → selected-recovery → dismissed/completed terminal path, rejects cross-item seam mismatch, and preserves claimed ownership without success artifacts when recovery fails
- local-only Phase 9A ownership interruption replay-durability proof that demonstrates a success artifact already written on the ownership seam can be replayed safely without duplicate evidence and without a false completed claim when the queue row is still only `claimed`
- local-only Phase 9B recovery interruption replay-durability proof that demonstrates a success artifact already written on the newer resume-recovery completion seam can be replayed safely without duplicate evidence and without a false completed claim when the session row is still only `claimed`
- local-only Phase 11 owned-recovery cross-surface interrupted-success ordering proof that demonstrates replay-safe healing when recovery is already durably `dismissed` with recovery evidence present while ownership remains only `claimed`, completing ownership without duplicate recovery evidence and without false cross-surface terminal claims
- broader local runtime contract doctrine stating what currently counts as durable local success, durable local failure, replay-healable intermediate state, evidence non-duplication, and ordered but explicitly non-atomic runtime behavior across the landed local seams
- bounded local sweep runtime in `ace/sweep.py` that classifies stale `TRIAGE`, `APPROVED`, `BLOCKED`, `CLAIMED_DONE`, and legacy `ACTIVE` items from live ACE DB truth, emits `item.sweep_flagged` events with duplicate suppression, and always writes an `ace.sweep.completed` summary event
- bounded read-only operator briefing runtime in `ace/briefing.py` that groups live ACE DB truth into deterministic `stale`, `blocked`, `needs_decision`, and `claimed_done` sections without mutating runtime state
- bounded operator-notification runtime in `ace/action_runtime.py` that enqueues deterministic `send_operator_notification` actions, claims and executes them replay-safely, records durable failed/completed state in `action_queue`, and writes `ace://notification/delivery` evidence on success through the real OpenClaw Gateway loopback `/tools/invoke` transport
- bounded autonomous operator-cycle seam in `ace/cycle.py` that composes live sweep truth, live briefing regeneration, briefing-file persistence, and notification orchestration instead of pretending `sweep` alone is the operator loop
- bounded resident supervisor-runtime seam in `ace/supervisor_runtime.py` that owns a distinct runtime-instance ledger, explicit `starting/live/stale/stopped/failed` lifecycle truth, heartbeat-based staleness, and operator inspection independent of governed one-shot cycle runs
- bounded resident supervisor startup/shutdown ownership seam in `ace/supervisor_runtime.py` that persists explicit `startup_status`, `shutdown_status`, `failure_phase`, `startup_completed_at`, `shutdown_requested_at`, and `shutdown_completed_at` truth for the resident supervisor slice
- bounded resident supervisor active runtime inspection seam in `ace/supervisor_runtime.py` that persists append-only runtime transition history and surfaces that history through `supervisor-status` distinctly from governed one-shot run history
- bounded resident supervisor runtime failure/recovery contract seam in `ace/supervisor_runtime.py` that persists ACE-owned recovery request/result truth and append-only recovery history distinctly from governed one-shot failure/interruption
- live-proven user-scoped LaunchAgent scheduling seam under `ace/launchd/` that executes the real `ace cycle` path against the live ACE DB
- one live-proven delivered operator alert path: seeded stale ACTIVE item -> sweep finding -> notification action completion -> `ace://notification/delivery` evidence -> OpenClaw-recorded Telegram delivery metadata
- CLI commands: `init`, `bootstrap`, `intake`, `list`, `show`, `inspect`, `sweep`, `briefing`, `cycle`, `cycle-status`, `supervisor-run`, `supervisor-status`, `add-evidence`, `add-obligation`, `add-contradiction`, `resolve-obligation`, `resolve-contradiction`, `approve`, `block`, `done`, `resolve`, `drop`

## Runtime

- Python 3
- standard library only
- entrypoint: `python3 ace/ace.py`
- install proof: root `pyproject.toml` packages `ace*` as `super-ace-governed-foundation` with no runtime dependencies
- CI proof: `.github/workflows/ace-ci.yml` installs `coverage`, runs `coverage run -m unittest discover -s ace/tests -t .`, and reports informational coverage on push and pull request changes under `ace/`

## State

- Database: `ace/state/ace.db`
- Canonical path: `TRIAGE -> APPROVED -> CLAIMED_DONE -> VERIFIED_DONE`
- `ACTIVE` is tolerated for legacy records, but not the primary happy path
- `resolve` enforces closeout gate checks for evidence, contradictions, and obligations, then writes `closeout_runs`
- continuity open-loop ingest stays read-only, maps only active-like items to `TRIAGE`, and reuses rows by deterministic `source + source_session`
- continuity pending-promotions ingest stays read-only, maps only `status == "pending"` items to `TRIAGE`, and reuses rows by deterministic `source + source_session`
- phase1 closed-loop proof classifies pending items from the original pending-promotion source field, keeps `continuity/pending-promotions.json` as the ingest source label, writes only `ace://phase1/decision` evidence, and skips duplicate decision evidence on replay
- phase1b closed-loop proof classifies eligible open-loop items from the original source-row severity field, keeps `continuity/open-loops.json` as the ingest source label, writes only `ace://phase1b/decision` evidence, and skips duplicate decision evidence on replay
- phase2 action-runtime proof enqueues deterministic `record_operator_followup` rows, claims them explicitly, executes only a bounded ACE-owned local evidence effect, fails explicitly without success evidence when preconditions break, and replays completed/failed rows idempotently
- phase4 runtime-ownership proof reuses the existing `action_queue` seam for deterministic ownership registration, replay-safe claim/release semantics, one ACE-owned local ownership outcome artifact, and explicit missing-target failure without continuity-source writes
- phase4b runtime-ownership proof stays on the same bounded seam and treats malformed or invalid persisted ownership payload during release as a durable explicit failed outcome with no success evidence
- phase7a cross-seam owned-recovery lifecycle proof composes bounded ownership and recovery behavior for the same item, writes exactly one recovery artifact plus one ownership artifact on the happy path, rejects cross-seam item mismatch, and leaves ownership claimed with no success artifacts when recovery fails
- phase11 owned-recovery cross-surface ordering proof demonstrates replay-safe healing of the mixed interrupted-success state where recovery is already durably `dismissed` with recovery evidence present while ownership remains only `claimed`, completing ownership without duplicate recovery evidence and without false cross-surface terminal claims
- read-only continuity handling is guarded by automated tests so ingest proofs cannot silently drift into source-surface mutation without breaking CI
- bounded sweep truth is now live: `ace sweep` reads current item state plus evidence/open-obligation/open-contradiction counts and latest activity timestamps, classifies only bounded stale buckets, writes replay-safe `item.sweep_flagged` events with fingerprint suppression, and writes one `ace.sweep.completed` summary event per run without mutating item state
- bounded briefing truth is now live: `ace briefing` reads live ACE DB truth through repository APIs, reuses the bounded stale-classification contract without calling mutating sweep execution, renders deterministic operator sections, and prevents duplicate placement of the same item across `stale` and `needs_decision`
- bounded notification truth is now live at the runtime seam: `ace/action_runtime.py` provides deterministic enqueue/claim/execute helpers for `send_operator_notification`, requires explicit age and/or deadline context, snapshots operator message content at enqueue time, records durable failed state for malformed payloads/missing targets/transport failures, and writes canonical notification-delivery evidence on success through Gateway `/tools/invoke`
- bounded autonomous cycle truth is now live: `ace cycle` composes sweep execution, briefing regeneration, briefing-file persistence, and notification orchestration from the landed seams, and refuses fake notification-free execution when actionable findings exist but routing is not supplied
- bounded V2.3 drift inspection truth is now live: `ace inspect <item_id>` exposes `loop_depth`, `decision_drift`, and `claim_drift` dimensions from chronological item-event truth, with `--drift-window` validation and explicit non-claim boundaries in `reports/ace-v2-3-drift-dimensions-evidence-2026-05-13.md`
- scheduling truth is now live: the user-scoped LaunchAgent executes the real `ace cycle` wrapper against the live ACE DB on schedule, with inspectable logs and environment-driven routing
- delivered-alert truth is now live: the current repo/runtime proof includes a completed `send_operator_notification` action plus `ace://notification/delivery` evidence carrying real Telegram delivery metadata (`messageId` `29370`, `chatId` `7529788084`)
- landed runtime contract truth is local-only and seam-bounded: durable success requires the owning row to reach its seam-specific terminal success state plus its required success evidence; durable failure requires explicit terminal failure state plus inspectable failure context and no success evidence; interrupted states are acceptable only where landed proofs show they are replay-healable without duplicate evidence or false terminal claims

## Runtime ownership payload invariant

For the bounded Phase 4/4B runtime-ownership seam, `action_queue.payload_json` is governed as a canonical JSON object with these required fields:
- `item_id` — normalized ACE item id bound to the ownership row
- `owner` — normalized owner string bound to the ownership row
- `metadata` — JSON object carrying bounded local ownership context

Current proof boundary:
- registration writes canonical sorted-key JSON for that payload
- claim requires the persisted payload to decode and match the claimed owner
- successful release requires the persisted payload to decode and match the releasing owner
- malformed or invalid persisted payload during release is treated as a durable explicit failed runtime-ownership outcome, not a crash and not a success artifact
- this invariant is seam-bounded and local-only; it is not yet a general payload contract for the broader substrate

## Current scope

This slice now includes bounded LaunchAgent wiring, one live-proven scheduled/delivered operator-alert path, the bounded governed-run lifecycle slice for local-only `ace cycle`, one bounded resident supervisor-runtime identity slice, one bounded resident supervisor startup/shutdown ownership slice, one bounded resident supervisor active runtime inspection slice, one bounded resident supervisor runtime failure/recovery contract slice, one bounded resident supervisor anti-inflation boundary proof slice, and one bounded resident supervisor distinct minimal slice proof. It still does not include LLM logic, broader continuity orchestration, continuity-source write authority, a generalized runtime fabric, daemon/service/platform semantics, worker-pool or scheduler control-plane ownership, multi-command governed runtime rollout, or broad production deployment semantics.

It also does not claim atomic all-at-once completion across seams. The strongest current runtime contract is narrower: ordered, replay-healable local behavior on landed seams, with explicit terminal states, explicit bounded failure states, and evidence non-duplication where proven.
