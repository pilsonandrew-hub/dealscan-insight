# Paperclip Routing Transition Index - 2026-04-17

Status: Active navigation index

## Purpose

This file is the quick navigation layer for the April 17 routing transition.

Use it when you want to find the right file quickly without remembering exact filenames.

## Read in this order

### 1. Current active policy
- `reports/dealerscope-model-governor-spec-2026-04-17.md`
- `reports/dealerscope-model-role-map-2026-04-17.md`
- `reports/paperclip-routing-governor-config-v2-2026-04-16.json`

### 2. Live implementation
- `scripts/paperclip-routing-governor.js`
- `scripts/paperclip-routing-governor.test.js`
- `scripts/paperclip-openrouter-bridge.js`
- `scripts/test-javarious-task-handoff-helper.js`

### 3. Comparison and transition history
- `reports/paperclip-routing-policy-change-log-2026-04-17.md`

### 4. Historical artifacts kept for audit/comparison
- `reports/paperclip-routing-governor-config-v1-2026-04-15.json`
- `reports/paperclip-routing-test-matrix-2026-04-15.md`
- `reports/paperclip-http-bridge-integration-note-2026-04-15.md`
- `reports/paperclip-openrouter-bridge-refactor-spec-2026-04-15.md`
- `reports/paperclip-routing-governor-enterprise-implementation-handoff-2026-04-15.md`
- `reports/paperclip-routing-governor-integration-blueprint-2026-04-15.md`
- `reports/paperclip-routing-governor-v2-build-spec-2026-04-16.md`
- `reports/paperclip-external-review-agent-spec-2026-04-16.md`
- `reports/paperclip-typed-task-transport-spec-2026-04-16.md`
- `reports/paperclip-http-agent-usage-contract-2026-04-15.md`
- `brains/dealerscope-brain/reports/README-STATUS-2026-04-17.md`

## Operating rule

If a historical file conflicts with:
- the active governor spec
- the active role map
- the active governor config
- the live governor/bridge scripts

then trust the active governor spec, role map, config, and live scripts.

## Why this index exists

The routing transition produced several useful layers:
- live policy
- live code
- test verification
- transition narrative
- historical snapshots

This file keeps those layers easy to navigate.
