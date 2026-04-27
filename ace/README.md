# Super A.C.E. — Governed Foundation

Super A.C.E. is currently best described as a governed foundation / Phase 0 continuity substrate for DealerScope work, with two narrow local-only Phase 1 closed-loop proofs, two narrow local-only Phase 2 action-runtime proofs, two narrow local-only Phase 3 resume/recovery proofs, two narrow local-only Phase 4 runtime-ownership proofs, one narrow local-only Phase 7A cross-seam owned-recovery lifecycle proof, one narrow local-only Phase 9A ownership interruption replay-durability proof, and one narrow local-only Phase 9B recovery interruption replay-durability proof.

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
- CLI commands: `intake`, `list`, `show`, `add-evidence`, `add-obligation`, `add-contradiction`, `approve`, `block`, `done`, `resolve`, `drop`

## Runtime

- Python 3
- standard library only
- entrypoint: `python3 ace/ace.py`
- install proof: root `pyproject.toml` packages `ace*` as `super-ace-v1` with no runtime dependencies
- CI proof: GitHub Actions installs `coverage`, runs `coverage run -m unittest discover -s ace/tests -t .`, and reports informational coverage on push and pull request changes under `ace/`

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
- read-only continuity handling is guarded by automated tests so ingest proofs cannot silently drift into source-surface mutation without breaking CI

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

This slice does not include sweep logic, notifications, LaunchAgent wiring, LLM logic, broader continuity orchestration, write authority over continuity-loop sources, general action-runtime, recovery-runtime, or runtime-ownership orchestration beyond the bounded Phase 2, Phase 3, Phase 4/4B, Phase 7A, Phase 9A, and Phase 9B proofs, or production deployment semantics.
