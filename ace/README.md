# Super A.C.E. V1

Super A.C.E. V1 is the local, durable context-and-continuity substrate for DealerScope work.

## What this slice provides

- `ace/` package skeleton
- SQLite bootstrap at `ace/state/ace.db`
- append-only event logging
- explicit item state transitions with loud failure on illegal moves
- a minimal item repository
- read-only continuity/open-loops ingest proof into a temp ACE DB with deterministic provenance and replay reuse
- read-only continuity/pending-promotions ingest proof into ACE TRIAGE for pending rows only, with deterministic provenance and replay reuse
- CLI commands: `intake`, `list`, `show`, `add-evidence`, `add-obligation`, `add-contradiction`, `approve`, `block`, `done`, `resolve`, `drop`

## Runtime

- Python 3
- standard library only
- entrypoint: `python3 ace/ace.py`
- install proof: root `pyproject.toml` packages `ace*` as `super-ace-v1` with no runtime dependencies
- CI proof: GitHub Actions runs `python -m unittest discover -s ace/tests -t .` on push and pull request changes under `ace/`

## State

- Database: `ace/state/ace.db`
- Canonical path: `TRIAGE -> APPROVED -> CLAIMED_DONE -> VERIFIED_DONE`
- `ACTIVE` is tolerated for legacy records, but not the primary happy path
- `resolve` enforces closeout gate checks for evidence, contradictions, and obligations, then writes `closeout_runs`
- continuity open-loop ingest stays read-only, maps only active-like items to `TRIAGE`, and reuses rows by deterministic `source + source_session`
- continuity pending-promotions ingest stays read-only, maps only `status == "pending"` items to `TRIAGE`, and reuses rows by deterministic `source + source_session`
- read-only continuity handling is guarded by automated tests so ingest proofs cannot silently drift into source-surface mutation without breaking CI

## Current scope

This slice does not include sweep logic, notifications, LaunchAgent wiring, LLM logic, broader continuity orchestration, write authority over continuity-loop sources, or production deployment semantics.
