# DealerScope Conversation Writeback Enforcement Plan

Status: Active recommendation
Date: 2026-04-17
Owner: Ja'various

## Problem
DealerScope doctrine already requires governed writeback and mirror sync after meaningful work, but conversation outcomes are still able to end as chat-only knowledge.

This creates a reliability gap:
- decisions can remain only in conversation history
- routing/policy conclusions can live only in reports outside the governed brain
- operator-visible Obsidian can lag behind meaningful conversation closeout

## Established truth to preserve
Canonical governed source remains:
- `brains/dealerscope-brain`

Human-visible destination-of-record mirror remains:
- `/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain`

Not authoritative for DealerScope:
- `/Users/andrewpilson/Documents/Javarious-Wiki`

## Current tooling reality
### What exists
- `scripts/dealerscope-brain-sync.py` mirrors selected canonical brain folders into the Obsidian Vault mirror
- governed standards already define repo-first authoring, mandatory writeback, transcript/source ingestion, and required sync after meaningful work

### What is missing
There is no hard closeout mechanism that guarantees meaningful conversations become governed brain artifacts before work is considered complete.

## Required operating rule
Any meaningful DealerScope or Paperclip conversation that changes one or more of the following must end in governed writeback:
- policy
- routing
- architecture
- trust semantics
- implementation direction
- incident posture
- operator doctrine
- reusable lessons

Required closeout path:
1. create or update canonical page(s) in `brains/dealerscope-brain`
2. run mirror sync to `/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain`
3. verify mirror parity on changed artifacts

## What should be written back from conversations
- decision summaries
- implementation closeout summaries
- incident summaries
- doctrine or standards updates
- reusable review artifacts
- transcript/source capture inventories
- postmortems and durable lessons

## What should not be blindly written back
- every chat message
- raw iterative chatter
- duplicate drafts
- temporary debug spam
- secrets or auth material

## Enforcement recommendation
### Immediate discipline rule
Do not treat meaningful DealerScope/Paperclip conversation work as complete until:
- governed brain artifact exists
- mirror sync has been run when needed
- verification confirms the mirror is current enough for operator trust

A closeout wrapper now exists at `scripts/dealerscope-writeback-closeout.sh`.
It:
1. requires named governed brain artifact paths
2. runs the canonical-to-Obsidian sync
3. runs exact-parity verification through `scripts/check-dealerscope-writeback-closeout.py`

### Minimal implementation change
Add a closeout checklist or helper script that forces the operator/agent to answer:
1. Did this conversation create a durable decision?
2. What canonical brain page records it?
3. Was the Obsidian mirror synced?
4. What parity check was performed?

### Better implementation after that
A first enforcement helper now exists at `scripts/check-dealerscope-writeback-closeout.py`.
It validates:
- target canonical page path exists
- mirror path exists after sync
- canonical and mirror content match by exact SHA-256 hash parity for touched files

Example:
```bash
python3 scripts/check-dealerscope-writeback-closeout.py \
  01_Standards/DealerScope-Knowledge-Writeback-Doctrine.md \
  01_Standards/DealerScope-Feed-Protocol-and-Sync-Contract.md
```

## Current sync-script note
`scripts/dealerscope-brain-sync.py` is directionally correct for the mirror path, but it currently mirrors only selected canonical directories and does not itself enforce conversation closeout or verification discipline.

## Recommended next engineering step
1. define the closeout checklist contract
2. expand or wrap the existing sync script with verification output
3. use that closeout path for Paperclip routing/governor work going forward

A conversation-oriented wrapper now exists at `scripts/closeout-governed-conversation.sh`.
It requires:
- a durable summary via `--summary`
- named governed brain artifacts via `--artifacts`

Then it calls the governed writeback closeout flow so conversation closeout is tied to real governed files instead of chat memory alone.

## Bottom line
The doctrine already says conversations with durable outcomes belong in the governed brain.
What is missing is enforcement, not philosophy.
