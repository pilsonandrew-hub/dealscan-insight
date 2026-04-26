# Super A.C.E. — Governed Foundation

Super A.C.E. is currently best described as a governed foundation / Phase 0 continuity substrate for DealerScope work, with two narrow local-only Phase 1 closed-loop proofs and two narrow local-only Phase 2 action-runtime proofs.

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
- read-only continuity handling is guarded by automated tests so ingest proofs cannot silently drift into source-surface mutation without breaking CI

## Current scope

This slice does not include sweep logic, notifications, LaunchAgent wiring, LLM logic, broader continuity orchestration, write authority over continuity-loop sources, general action-runtime orchestration beyond the two bounded Phase 2 proofs, or production deployment semantics.
