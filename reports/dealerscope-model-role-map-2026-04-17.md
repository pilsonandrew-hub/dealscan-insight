# DealerScope Model and Agent Role Map

Date: 2026-04-17
Status: Operating map

## Purpose

This document defines where Claude, Codex, Cursor, Gemini, DeepSeek, Kimi, and Claude Code fit in the DealerScope stack.

The goal is to prevent role blur between:
- live runtime decision lanes
- engineering/build agents
- review and enforcement layers

For routing-policy transition history, old-to-new lane mapping, and historical artifact status, also see:
- `reports/paperclip-routing-policy-change-log-2026-04-17.md`
- `reports/paperclip-routing-transition-index-2026-04-17.md`

## Layer 1: Live runtime model lanes

These models are used in the Paperclip or DealerScope runtime when the system is actively routing tasks.

### Gemini 2.5 Flash
Role:
- main fast reviewer
- primary structured judgment lane

Use for:
- external review
- recon scoring
- market intelligence
- deal adjudication until premium escalation is needed

Not for:
- deterministic Crosshair rules
- private local-only tasks

### Gemini 2.0 Flash
Role:
- proven sustained fallback
- co-primary safety lane

Use for:
- fallback when Gemini 2.5 fails, degrades, or trips limits
- conservative runtime continuity
- lower-risk review fallback

### DeepSeek V3.2
Role:
- non-sensitive structured workhorse

Use for:
- scrape normalization
- summarization
- orchestration support
- code reasoning support in engineering contexts where data is non-sensitive

Hard restrictions:
- no bid strategy
- no final deal evaluation
- no financial judgment
- no sensitive recon decisions

### Gemini 2.5 Flash Lite
Role:
- cheap triage and utility lane

Use for:
- alert formatting
- health checks
- light extraction
- low-cost summaries

### Kimi K2
Role:
- specialist long-document extractor

Use for:
- PSR extraction
- long auction docs
- large structured document extraction

Not for:
- general reviewer rotation
- final financial judgment
- recon scoring

### Claude Opus 4.7
Role:
- premium judgment escalation lane

Use for:
- architecture critique
- contradiction detection
- high-value recon escalations
- premium review when default lanes are not enough

Current status on 2026-04-17:
- bridge/runtime certified
- harness certified for the compact structured premium contract used for DealerScope recon/premium escalation
- should remain escalation-only, with the compact contract enforced in governor/bridge code to avoid prompt-sprawl regressions

## Layer 2: Engineering and build agents

These are not live runtime decision lanes. They are used to build, review, and modify the DealerScope system.

### Codex
Role:
- code reviewer
- architecture/spec generator
- backend reasoning partner

Use for:
- reading code and identifying change points
- producing exact implementation specs
- reviewing backend logic
- validating safety of code changes before implementation

Not for:
- live runtime routing decisions
- replacing Gemini or Claude in production judgment paths

### Claude Code
Role:
- primary implementer

Use for:
- executing approved code changes
- frontend implementation
- applying planned edits from reviewed specs

Not for:
- being the sole reviewer of its own work

## Layer 3: Review enforcement and quality control

These are guardrail systems, not runtime model lanes.

### Cursor
Role:
- automated code reviewer
- ongoing quality and rule enforcement layer

Use for:
- PR review
- commit review
- catching business-rule violations
- flagging silent failures and unsafe logic regressions
- validating that shipped code stays aligned with policy

Important:
- Cursor is not the runtime brain
- Cursor is not the implementation agent
- Cursor is the persistent reviewer watching the codebase

## Required operating pattern

### Runtime path
Use:
- Gemini 2.5 Flash
- Gemini 2.0 Flash
- DeepSeek V3.2
- Gemini 2.5 Flash Lite
- Kimi K2
- Claude Opus 4.7 only as escalation lane

### Build path
Use:
- Codex to review and spec
- Claude Code to implement

### Review path
Use:
- Cursor to review and enforce
- Claude Opus when premium judgment or contradiction detection is needed

## Anti-confusion rules

1. Do not treat Codex as a live runtime routing model.
2. Do not treat Cursor as a runtime decision model.
3. Do not let DeepSeek handle financially sensitive DealerScope decisions.
4. Do not put Kimi in general reviewer rotation.
5. Do not let Claude become a default broad lane outside the certified compact premium contract path.
6. Keep Crosshair deterministic and hard-blocked from LLM routing.

## Current recommendation

The stable near-term stack is:
- Gemini 2.5 Flash as primary fast reviewer
- Gemini 2.0 Flash as proven fallback
- DeepSeek for non-sensitive structured work only
- Gemini 2.5 Flash Lite for cheap utility work
- Kimi K2 for long-document specialist extraction
- Claude Opus 4.7 for premium escalation via the certified compact contract path
- Codex for engineering review/spec
- Claude Code for implementation
- Cursor for continuous review enforcement
