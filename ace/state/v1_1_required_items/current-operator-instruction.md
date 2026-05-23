# Current Operator Instruction
Authority: this file is the durable operator scope anchor. The bot does not edit this file. Operator (Andrew) updates it via explicit instruction. Chat-level conflicts lose to this file.
Last updated: 2026-05-22 by operator authorization
## Mode
implementation_approved — V1.1 cleanup + event_sequence precursor for item 2
## Scope
Two bounded work items in sequence:
Phase A: Cleanup from Ja’rvontis audit
- Remove pycache directories from repo and add to .gitignore
- Consolidate the three duplicate normalization functions (_normalize_required_human_text in repository.py, _normalize_required_text in telegram_intake.py, _normalize_required_text in action_runtime.py) into one shared utility in ace/normalization.py
- Tests must prove all three callers still behave identically after consolidation
Phase B: event_sequence column
- Add event_sequence INTEGER NOT NULL column to events table
- Populate via SELECT COALESCE(MAX(event_sequence), 0) + 1 inside append_event
- Migration logic backfills existing events with sequential numbers in (created_at, id) order, preserving current effective ordering
- Hash chain verifier walks ORDER BY event_sequence
- Tests prove deterministic ordering across rebuilds and that hash verification still passes for existing data
Phase C: V1.1 item 1 INSERT gap closure
- Add INSERT block to SQLite authorizer for events table
- Add ace_events_no_insert trigger to events table
- Allow exception path so append_event continues to work (e.g. via authorizer state flag or designated connection marker)
- Update test fixtures that previously used direct INSERT to use append_event instead
- Tests must prove: direct INSERT INTO events from any non-append_event path is refused, and append_event still functions normally
## Allowed write paths
- ace/.py for normalization consolidation and event_sequence column implementation*
- ace/storage.py
- ace/normalization.py (new file)
- ace/tests/.py for new and modified tests*
- ace/tests/.py
- .gitignore for pycache exclusion
## Allowed actions
- File writes/edits to the above paths only
- Removing pycache directories from tracked files (git rm)
- Git commits with Operator-Scope trailer
- Git push to origin/master
- Running full ACE test suite under PYTHONWARNINGS=error
- Read access to all of ACE, Ja’rvontis audit notes if needed
## Forbidden
- Editing this anchor file (operator-owned)
- Modifying authorization.json or operator-scope-design-decisions.md
- Modifying OpenClaw config
- Filesystem permission changes
- Credential reads or writes
- External sends
- Launchd plist modification
- DealerScope changes
- Subagent spawns
- Force-push or history rewrite
- Starting V1.1 item 2 (Backblaze attestation) — that’s a separate scope
## Slices
Sequential. Report each commit before next. Wait for operator approval before each next slice.
Slice A1: Remove pycache from tracked files, add to .gitignore. Verify nothing breaks. Single commit.
Slice A2: Create ace/normalization.py with shared function. Update repository.py, telegram_intake.py, action_runtime.py to import from it. Tests prove behavioral parity. Single commit.
Slice B1: Add event_sequence column with migration that backfills existing events. Update append_event to populate it. Tests prove migration is safe and ordering is preserved. Single commit.
Slice B2: Update hash chain verifier to walk ORDER BY event_sequence. Tests prove existing chains still verify and that ordering is now deterministic across simulated rebuilds. Single commit.
## Expiry
This scope expires 4 hours from Slice A1 commit, OR when Slice B2 lands with all tests passing, whichever first. After expiry, scope reverts to investigation/consultation only.
## Tiered denial behavior
If you encounter a need to do something outside this scope:
- Do NOT extend scope yourself
- Do NOT edit this anchor
- Do NOT proceed
- Stop, report what you need, wait for operator to update anchor
## Operator-owned items NOT in this scope
- Backblaze credential setup
- B2 SDK integration
- V1.1 item 2 work
- All other operator-owned items from prior anchor
