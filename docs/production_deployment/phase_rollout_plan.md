# DealerScope Production Rollout Plan

## Purpose

This document describes the current rollout posture for DealerScope based on verified live code, verified live route surface, and current backend/frontend authority.

It does **not** treat historical route families, synthetic validation harnesses, or legacy export/evaluation tooling as rollout truth.

---

## Current production authority

### Backend entrypoint
- `backend/main.py`

### Current mounted operational route families
- `admin`
- `ingest`
- `rover`
- `outcomes`
- `analytics`
- `sniper`
- `saved_searches`
- `vin`
- `recon`
- `sonar`
- `lifecycle`

### Explicit retained alias
- `POST /api/opportunities/{opportunity_id}/pass`

### Live health routes
- `GET /health`
- `GET /healthz`

### Route families intentionally removed from the main entrypoint
These older families were unmounted because they were absent from verified production route surface and had become false operational authority:
- `auth`
- `vehicles`
- `upload`
- `ml`
- `opportunities`

Legacy code for some of those surfaces may still exist in the repo, but they are not part of the current main backend rollout surface.

---

## Current frontend/runtime authority

Frontend API base should resolve through:
- `src/config/settings.ts`
- `settings.api.baseUrl`

The active frontend service/component tier has been cleaned to stop hardcoding the Railway production origin directly.

Current frontend behavior should not rely on:
- dead `/api/health`
- dead `/api/metrics`
- dead `/api/ready`
- dead `/api/live`
- dead `/api/ingest/ingest-vehicle`

---

## Current production route truth

### Verified present in production
- `/health`
- `/healthz`
- `/api/ingest/opportunities/{opportunity_id}/pass`
- `/api/opportunities/{opportunity_id}/pass`

### Verified absent in production
- `/api/opportunities` list/detail/save/ignore/rescore routes
- `/api/vehicles/*`
- `/api/auth/*`
- `/api/upload/*`
- `/api/ml/*`
- `/api/health`
- `/api/metrics`
- `/api/ready`
- `/api/live`
- `/api/ingest/ingest-vehicle`

No rollout step should assume those absent routes are part of current live production.

---

## Rollout assumptions that are no longer valid

This rollout plan intentionally rejects older assumptions such as:
- generic `/api/opportunities` CRUD being a live production authority
- `/api/auth`, `/api/vehicles`, `/api/upload`, or `/api/ml` being mounted production route families
- synthetic validation/evaluation scripts as production evidence
- local v4.7 export/harness scripts as rollout truth
- stale `/api/health` or `/api/metrics` checks as production health authority

---

## Current rollout priority order

### Phase 1: canonical ingest/scoring stability
Primary truth surfaces:
- `webapp/routers/ingest.py`
- `backend/ingest/score.py`
- `backend/ingest/condition.py`
- reconciliation/control-plane scripts directly tied to ingest outcomes

Goal:
- keep current ingest/scoring path coherent
- preserve truthful delivery logging and reconciliation
- avoid reintroducing dead route assumptions or fake fallback behavior

### Phase 2: control-plane truth alignment
Primary surfaces:
- current workflows
- current route assumptions in active scripts
- central frontend API base resolution

Goal:
- ensure code, workflows, scripts, and docs describe the same live system

### Phase 3: docs and operator truth
Primary surfaces:
- README
- current operational docs
- bounded production/readiness docs

Goal:
- remove stale route/architecture lies from operator-facing docs

### Phase 4: historical / legacy artifact demotion
Primary surfaces:
- synthetic validation generators
- legacy export/evaluation helpers
- local harnesses

Goal:
- preserve useful local tooling without letting it masquerade as production truth

---

## Current rollout blockers vs non-blockers

### Real blockers
- any mismatch between live code and workflows that changes business-rule enforcement
- any route assumption that points operators or scripts at dead production endpoints
- any stale authority surface that causes remediation to target dead code paths instead of canonical ones

### Not automatic blockers
- historical docs that are clearly labeled historical
- local legacy harnesses that are clearly labeled non-authoritative
- development allowlists that include local origins for legitimate dev reasons

---

## What to use as rollout evidence

Use:
- current code
- current migrations/schema
- current mounted route surface
- current frontend config authority
- live route checks

Do not use alone:
- synthetic validation reports
- legacy evaluation scores
- export packaging summaries
- deprecated route families still present only as leftover code

---

## Rollout rule going forward

Before any rollout or remediation claim, verify against:
1. `backend/main.py`
2. current mounted routers
3. `src/config/settings.ts`
4. `supabase/migrations/`
5. live route checks
6. current workflows/control-plane scripts

If a script, route, or doc disagrees with those surfaces, downgrade the script/route/doc first instead of treating it as authority.
