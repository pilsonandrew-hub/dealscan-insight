# Current Operator Instruction
Authority: this file is the durable operator scope anchor. The bot does not edit this file. Operator (Andrew) updates it via explicit instruction. Chat-level conflicts lose to this file.
Last updated: 2026-05-22 by operator authorization
## Mode
implementation_approved — V1.1 cleanup + event_sequence precursor for item 2
## Scope
V1.1 cleanup, event_sequence checkpoint-forward implementation, V1.1 item 1 INSERT gap closure.
Phase A: Cleanup from Ja’rvontis audit — COMPLETED (Slice A1)
- pycache removal — done in 4364094
- Duplicate normalization consolidation — canceled (functions not actually identical)
Phase B: event_sequence column with checkpoint-forward design
- Slice B1 (commit 600d65f) had a design bug: backfilled using (created_at, id) ordering which disagrees with the original implicit row-id chain. To be reverted and redone with checkpoint design.
- B-revert: Revert Slice B1 cleanly
- B-disclose: Document legacy chain defects: 163 timestamp/id inversions, 4 deliberately backdated proof events, 2 concurrent-write chain breaks from 2026-05-23, root cause analysis, decision to checkpoint forward not rewrite
- B-cutover: Design and append a single cutover event marking the V1.1 chain boundary
- B-append: Redesign append_event to assign event_sequence inside the transaction at write time, using BEGIN IMMEDIATE serialization, with head-hash recomputation inside the transaction
- B-tests: Tests prove pre-cutover events stay unchanged, post-cutover events verify deterministically, concurrent writes produce clean chains
Phase C: V1.1 item 1 INSERT gap closure
- Slice C1 work already done locally but not committed (per prior diagnosis). To be revisited after Phase B completes — INSERT lockdown must coexist with the new cutover/append design
## Allowed write paths
- ace/.py for normalization consolidation and event_sequence column implementation*
- ace/storage.py
- ace/normalization.py (new file)
- ace/tests/.py for new and modified tests*
- ace/tests/.py
- .gitignore for pycache exclusion
- ace/state/v1_1_required_items/legacy-chain-defects.md (new file for the disclosure)
- ace/state/v1_1_required_items/cutover-event-design.md (new file for the cutover architecture record)
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
