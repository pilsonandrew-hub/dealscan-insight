# Paperclip Routing Policy Change Log - 2026-04-17

Status: Active reference for April 17 routing-policy transition

## Purpose

This file records the routing-policy transition from the older Paperclip/OpenRouter lane model into the current governor-aligned policy.

It exists to preserve:
- comparison history
- rationale for the change
- old-to-new lane mapping
- source-of-truth guidance

It should be read alongside the live implementation files, not instead of them.

See also:
- `reports/paperclip-routing-transition-index-2026-04-17.md`

## Current source of truth

Policy and runtime truth now live in:
- `reports/dealerscope-model-governor-spec-2026-04-17.md`
- `reports/dealerscope-model-role-map-2026-04-17.md`
- `reports/paperclip-routing-governor-config-v2-2026-04-16.json`
- `scripts/paperclip-routing-governor.js`
- `scripts/paperclip-routing-governor.test.js`
- `scripts/paperclip-openrouter-bridge.js`

## How to use this file

Use this as the narrative comparison layer.

- If you want the story of the transition, read this file.
- If you want exact live behavior, use the active config and scripts.
- If an older report conflicts with this file and the live config/scripts, trust the live config/scripts.
- If this file ever drifts from the active governor spec or role map, update this file rather than silently letting comparison history rot.

## Why this changed

The earlier routing setup worked as a useful exploration phase, but it had become too loose to serve as production policy.

Main reasons for the transition:
- lane names and active runtime behavior had drifted apart
- some historical docs still looked authoritative even after policy changed
- sensitive financial/recon work needed harder restrictions and explicit fail-closed behavior
- Claude premium usage needed compact structured contracts enforced in code, not remembered manually
- `/run` and `/task` routing needed to converge on one governor-aware path
- “model failures” were often actually policy, bridge, or contract failures

## Main policy changes

### 1. Routing moved to explicit governor policy
Older routing assumptions were replaced by a more explicit governor-driven model with:
- task-class routing
- allowlist enforcement
- excluded-model enforcement
- premium gating
- fail-closed behavior
- clearer lane intent

### 2. Gemini became the default fast review path
Current default review posture:
- `openrouter_gemini_review` → Gemini 2.5 Flash as main fast reviewer
- `openrouter_gemini_proven` → Gemini 2.0 Flash as proven fallback/co-primary
- `openrouter_gemini_triage` → Gemini 2.5 Flash Lite for cheap utility/triage

### 3. Claude moved to premium escalation, not general default review
Claude is now intentionally constrained:
- premium lane only
- compact structured contract enforced in governor/bridge flow
- approval-gated for sensitive premium use cases
- certified for compact premium recon usage after live bridge validation

### 4. DeepSeek was restricted
DeepSeek is no longer treated as a general fallback for sensitive financial judgment.

Current role:
- non-sensitive structured volume
- code reasoning
- scrape normalization
- summarization
- orchestration
- general chat

It should not be used for premium financial/recon judgment paths.

### 5. Kimi became specialist-only
Kimi is now treated as a specialist lane for long-document / PSR-style extraction rather than a general reviewer rotation candidate.

### 6. Crosshair deterministic tasks were hard-blocked from LLM routing
Some tasks should not be routed through an LLM at all. That boundary is now explicit.

### 7. Bridge/runtime now honor governor contracts
The bridge was upgraded so live runtime behavior matches governor policy:
- governor-emitted compact Claude contracts are now consumed in `/run`
- `/task` was moved closer to the same shared routing path
- stale lane-catalog mismatches were cleaned up and verified live after restart

## Old lane names to current policy meaning

This is a conceptual mapping, not a claim that every old lane is a one-to-one replacement.

| Older lane name | Current meaning / replacement |
|---|---|
| `openrouter_claude_review` | replaced by `openrouter_claude_premium` for premium escalation only |
| `openrouter_claude_fallback` | no direct equivalent as an active standard lane; older fallback concept retired |
| `openrouter_general` | replaced in practice by task-specific governed routing, often `openrouter_deepseek_workhorse` or Gemini lanes depending on task class |
| `openrouter_deepseek_reasoner` | replaced by `openrouter_deepseek_workhorse` with narrower non-sensitive permissions |
| `openrouter_kimi_review` | replaced by `openrouter_kimi_specialist` |
| `openrouter_qwen_review` | not active in current governed rotation |
| `openrouter_minimax_review` | not active in current governed rotation |

## What became historical only

These files remain useful for comparison/audit history, but should not be treated as live policy:
- `reports/paperclip-routing-governor-config-v1-2026-04-15.json`
- `reports/paperclip-http-bridge-integration-note-2026-04-15.md`
- `reports/paperclip-openrouter-bridge-refactor-spec-2026-04-15.md`
- `reports/paperclip-routing-governor-enterprise-implementation-handoff-2026-04-15.md`
- `reports/paperclip-routing-governor-integration-blueprint-2026-04-15.md`
- `reports/paperclip-routing-test-matrix-2026-04-15.md`
- `reports/paperclip-routing-governor-v2-build-spec-2026-04-16.md`
- `reports/paperclip-external-review-agent-spec-2026-04-16.md`
- `reports/paperclip-typed-task-transport-spec-2026-04-16.md`
- `reports/paperclip-http-agent-usage-contract-2026-04-15.md`
- mirrored copies under `brains/dealerscope-brain/reports/`

## Important implementation outcomes from this transition

### Verified in tests
- governor tests updated and passing against the new policy
- policy mismatch around PSR fallback was found and corrected through tests
- compact Claude contract behavior was added to governor tests

### Verified live
- premium Claude lane worked end to end through the live bridge
- compact recon JSON contract succeeded live after restart
- lane-catalog drift between governor and bridge was fixed
- `/task` and `/run` became much closer to one routing truth

## Durable lessons

- Production truth beats documentation assumptions.
- Runtime truth beats catalog guesses.
- A visible UI or historical doc can lag behind the real enforced contract.
- Routing policy should be explicit, deterministic, and fail closed.
- Sensitive financial judgment should never rely on informal model-role memory.
- Historical docs are valuable, but only if clearly labeled as historical.

## Recommended use going forward

Use this file when you need to answer:
- what changed?
- why did we change it?
- what do the old lane names correspond to now?
- which files are current versus historical?

For exact behavior, always defer to the live config and scripts.
