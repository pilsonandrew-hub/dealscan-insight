# Super A.C.E. V1

Super A.C.E. V1 is the local, durable context-and-continuity substrate for DealerScope work.

## What this slice provides

- `ace/` package skeleton
- SQLite bootstrap at `ace/state/ace.db`
- append-only event logging
- explicit item state transitions with loud failure on illegal moves
- a minimal item repository
- CLI commands: `intake`, `list`, `show`, `add-evidence`, `add-obligation`, `add-contradiction`, `approve`, `block`, `done`, `resolve`, `drop`

## Runtime

- Python 3
- standard library only
- entrypoint: `python3 ace/ace.py`

## State

- Database: `ace/state/ace.db`
- Canonical path: `TRIAGE -> APPROVED -> CLAIMED_DONE -> VERIFIED_DONE`
- `ACTIVE` is tolerated for legacy records, but not the primary happy path
- `resolve` enforces closeout gate checks for evidence, contradictions, and obligations, then writes `closeout_runs`

## Current scope

This slice does not include sweep logic, notifications, LaunchAgent wiring, LLM logic, or broader continuity orchestration.
