Current Operator Instruction

Authority: this file is the durable operator scope anchor. The bot does not edit this file. Operator (Andrew) updates it via explicit instruction. Chat-level conflicts lose to this file.

Last updated: 2026-05-23 by operator authorization. V1.1 closure sprint.

Mode

mplementation_approved — V1.1 closure: dirty file cleanup, tech debt fixes, V1.1 item 2 (external attestation), operator activation checklist, breach log closure, then operator activation, then ACE 1.0 re-tag.

Allowed write paths

ace/.py and ace/tests/.py for tech debt fixes and item 2 implementation
 • ace/backblaze/* or ace/attestation/* (new module for item 2)
 • ace/state/v1_1_required_items/* for closure docs and item 2 design
 • ace/state/breach-log/* for lessons-learned closure
 • MEMORY.md to clean pre-existing dirty state
 • ace/state/v1_1_required_items/operator-scope-consultation-prompt.txt (commit or delete per operator decision)
 • Git tag operations for ACE 1.0 re-tag only after operator confirms activation complete

Editing this anchor file (operator-owned, one-time write above only)
 • Skipping the design phase for item 2
 • Skipping Ja’rvontis review at key checkpoints
 • Direct cutover event modification
 • Force-push or history rewrite
 • Tagging ACE 1.0 before operator confirms activation checklist is complete
 • DealerScope changes
 • SniperScope changes

Required cadence

Each numbered step is its own slice. Commit, push, confirm CI green, report, stop, wait for my approval before next slice.

Expiry

Scope refreshes per slice. If any slice takes more than 4 hours from approval, stop and request refresh.
