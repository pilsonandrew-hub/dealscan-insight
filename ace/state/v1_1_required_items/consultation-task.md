# Operator Scope Enforcement Consultation Task

Source: reconstructed from `memory/2026-05-21.md` and Andrew's correction after the Item 3 re-implementation bypass.

## Current operator boundary

Stop all V1.1 implementation. This is now the top priority.

Consult Claude, Gemini, and DeepSeek on operator scope enforcement architecture before any implementation.

No implementation. No commits except the breach log update, the current operator-instruction anchor, this consultation task file, and the consultation results file.

Save consultation results to:

`ace/state/v1_1_required_items/operator-scope-enforcement-consultation.md`

## Minimum questions for the consultation

1. How should ACE represent the current operator-authorized scope durably so it survives compaction, session handoff, and agent restart?
2. How should runtime/code paths gate implementation actions, file writes, commits, DB mutation, external sends, and tests against that durable scope?
3. What should happen when active context conflicts with the durable operator instruction anchor?
4. How should the system prove that blocked actions were blocked before side effects occurred?
5. How should approvals be structured so "proposal only", "investigation only", and "implementation approved" are machine-distinguishable?
6. What architecture best prevents the repeated bypass pattern documented in the breach log while avoiding cosmetic compliance that can be ignored by an agent?

## Required output format

Create `operator-scope-enforcement-consultation.md` with:

- Claude recommendation
- Gemini recommendation
- DeepSeek recommendation
- Cross-model agreement
- Disagreements/tradeoffs
- Final proposed architecture
- Explicit non-implementation boundary
