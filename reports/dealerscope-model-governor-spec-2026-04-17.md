# DealerScope Model Governor Spec

Date: 2026-04-17
Status: Active implementation source of truth

## Purpose

This document defines the recommended routing-governor model stack for DealerScope based on live bridge validation, production history, operational constraints, and task sensitivity.

It is intended to be the implementation source of truth for Claude, Codex, and any runtime/governor work that follows.

For comparison history and old-to-new lane mapping, also see:
- `reports/paperclip-routing-policy-change-log-2026-04-17.md`
- `reports/paperclip-routing-transition-index-2026-04-17.md`

## Core principles

1. Live bridge behavior outranks catalog presence, vendor reputation, and benchmark hype.
2. No premium lane becomes trusted by convention alone. Premium lanes must pass DealerScope-specific bridge validation.
3. Sensitive financial and bid-related tasks must route only through approved US-hosted lanes.
4. DeepSeek is allowed for non-sensitive structured volume only.
5. Crosshair deterministic rules must be hard-blocked from LLM routing.
6. Exclusions must be explicit, documented, and reviewable.
7. The governor must fail closed.

## Task lane architecture

### Lane A: Premium judgment escalation
Use for:
- architecture critique
- contradiction detection
- recon escalations with low confidence
- final bid strategy on high-value vehicles
- decisions with material financial consequence

Model target:
- Claude Opus 4.7

Operational rule:
- This is the designated premium reviewer target, not an automatically trusted live default.
- It must pass a DealerScope bridge probe on three real tasks before full activation:
  1. recon evaluation
  2. architecture critique
  3. deal analysis with full vehicle data

Temporary fallback until certified:
- Gemini 2.5 Flash
- Gemini 2.0 Flash

Constraints:
- explicit escalation only
- never default route
- hard budget gated
- US-hosted lanes only

### Lane B: Fast structured review
Use for:
- opportunity scoring review
- secondary evaluation
- market intelligence summaries
- analytics review
- operational triage requiring judgment
- document critique

Primary:
- Gemini 2.5 Flash

Fallback:
- Gemini 2.0 Flash

Constraints:
- default review lane
- low latency target
- US-hosted lanes only

### Lane C: Volume workhorse, non-sensitive structured tasks
Use for:
- listing normalization
- scrape output structuring
- HTML parsing
- public auction text extraction
- routine operational transforms with no financial sensitivity

Primary:
- DeepSeek V3.2

Constraints:
- public / non-sensitive data only
- no bid strategy
- no deal evaluation
- no financial projections
- no CTM or recon financial judgment

### Lane D: Cheap triage and utility
Use for:
- health checks
- alert composition
- formatting
- light summaries
- low-cost second pass validation
- simple extraction

Primary:
- Gemini 2.5 Flash Lite

Fallback:
- Gemini 2.0 Flash

### Lane E: Specialist long-document extraction
Use for:
- PSR extraction
- Manheim long-document parsing
- very long Google Docs dumps
- structured extraction from large documents

Primary:
- Kimi K2

Constraints:
- specialist-only lane
- not eligible for general reviewer rotation
- document threshold / explicit task-class trigger required

### Lane F: Proven sustained fallback
Primary:
- Gemini 2.0 Flash

Purpose:
- safe landing when higher lanes trip circuit breakers or fail validation
- proven environment-compatible fallback with real production history

### Lane G: Hard block, deterministic rules only
Use for:
- Crosshair deterministic filters
- hard rules engine tasks
- anything that should never route to an LLM

Behavior:
- active rejection
- no fallback route
- governor returns explicit blocked/no-llm decision

### Lane H: US-only financial-sensitive tasks
Use for:
- bid strategy
- recon evaluation above sensitivity threshold
- CTM ratio calculation review
- profit and margin judgment
- any task with material financial consequence

Allowed models:
- Claude Opus 4.7 once certified
- Gemini 2.5 Flash
- Gemini 2.0 Flash

Disallowed:
- DeepSeek
- Kimi
- Qwen
- MiniMax

## Ranked stack for DealerScope

### Active rotation
1. Gemini 2.5 Flash
2. Gemini 2.0 Flash
3. DeepSeek V3.2 (non-sensitive tasks only)
4. Gemini 2.5 Flash Lite
5. Kimi K2 (specialist only)

### Premium target lane
- Claude Opus 4.7, certified for the compact structured premium contract path used in DealerScope escalation flows

### Pending validation
- MiniMax M2.5
- Qwen 235B A22B only if runtime path changes materially

### Explicit exclusions
- Gemini 3.1 Pro Preview
  - reason: unintended model substitution incident in production path, pending root cause investigation
- Kimi K2.5
  - reason: returned no response content in live probe
- MiniMax M2.7
  - reason: returned no response content in live probe
- MiniMax M1
  - reason: weak output in live probe
- Kimi latest
  - reason: invalid model id in bridge path
- MiniMax text-01
  - reason: invalid model id in bridge path
- Qwen 3.6 / 3.6 Plus
  - reason: runtime identity / API id not cleanly validated in current path
- Qwen 235B A22B
  - reason: reasoning-heavy behavior makes it unsuitable for current governor-routed structured workloads

## Governor requirements before production

1. JSON Schema validation for governor config
2. Canonical task-class registry
3. Bridge-validated model allowlist
4. Explicit exclusion list with reasons and retest criteria
5. Circuit breakers for failing lanes
6. Hard budget gates for premium lanes
7. Structured routing decision logs
8. Fail-closed behavior on unknown task classes
9. Hard block support for deterministic no-llm tasks
10. Sensitive-task policy enforcement at route time, not by operator memory

## Operational rules

### Certification rule
No model becomes a primary lane only because it looks good on paper. It must pass DealerScope-specific bridge tests in the current environment.

### Financial sensitivity rule
Any task involving bids, deal evaluation, financial projections, recon scoring with material consequence, or final margin judgment must route to approved US-hosted lanes only.

### Specialist model rule
Kimi K2 is not a general reviewer. It is reserved for long-document extraction and similar specialist document tasks.

### DeepSeek boundary rule
DeepSeek handles public-data, non-sensitive structured tasks only.

### Exclusion governance rule
Excluded models remain blocked until explicitly re-proven and the exclusion reason is retired.

## Recommended implementation order

1. Add canonical task classes and sensitivity labels
2. Encode financial-sensitive task blocking for DeepSeek and all non-approved lanes
3. Add explicit exclusions into governor config
4. Add schema validation and fail-closed startup checks
5. Add circuit breakers and structured route logs
6. Keep Claude Opus 4.7 constrained to the certified compact contract path in governor/bridge code
7. Add regression tests and drift checks so future prompt or lane changes do not silently break certification

## Plain-English recommendation

DealerScope should run on a disciplined multi-lane stack, not a popularity contest.

The practical stack today is:
- Gemini 2.5 Flash as the main reviewer
- Gemini 2.0 Flash as the proven sustained fallback and co-primary safety lane
- DeepSeek V3.2 for non-sensitive structured volume only
- Gemini 2.5 Flash Lite for cheap triage
- Kimi K2 only for long-document specialist work

Claude Opus 4.7 should be the premium escalation lane, but only after it passes a real DealerScope bridge certification in this exact environment.

The governor is the real control point. Without hard exclusions, task sensitivity rules, schema validation, and circuit breakers, the model stack will drift and become expensive, inconsistent, and unsafe.
