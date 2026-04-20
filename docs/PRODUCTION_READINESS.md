# DealerScope Production Readiness

## Purpose

This document describes current DealerScope production-readiness truth using verified live code, verified route surface, current config authority, and current migrations.

It does **not** treat historical route families, synthetic validation harnesses, legacy export helpers, or old architecture assumptions as readiness authority.

---

## Current readiness truth

DealerScope is production-shaped as a **hybrid live system**, not as a neat single Docker/Celery/Postgres stack.

Current verified authority order:
1. live code
2. live schema/migrations
3. frontend/backend integration points
4. workflows/control-plane files
5. historical docs and legacy tooling

---

## Current backend readiness surface

### Backend entrypoint
- `backend/main.py`

### Current mounted route families
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

### Route families removed from current main backend surface
These route families are no longer mounted from the main backend entrypoint because they were absent from verified production route surface and had become false authority:
- `auth`
- `vehicles`
- `upload`
- `ml`
- `opportunities`

Legacy code for those areas may still exist in the repo, but it is not current mounted production authority.

---

## Current frontend/runtime readiness surface

Frontend API access should route through:
- `src/config/settings.ts`
- `settings.api.baseUrl`

The current frontend service/component tier has been cleaned so it no longer hardcodes the Railway production origin in the major live surfaces.

Readiness claims should therefore be based on:
- centralized API base resolution
- current mounted backend route families
- current live route checks

Not on stale per-file hardcoded origins.

---

## Verified production route truth

### Present
- `/health`
- `/healthz`
- `/api/ingest/opportunities/{opportunity_id}/pass`
- `/api/opportunities/{opportunity_id}/pass`

### Absent
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

Any readiness surface still assuming those absent routes are live is stale and should be treated as a defect in documentation/tooling, not as current production truth.

---

## Current scoring/readiness reality

Current scoring truth lives in:
- `backend/ingest/score.py`
- `backend/ingest/condition.py`

Current vehicle rule model is a two-lane system:

### Premium lane
- max age 4 years
- max mileage 50,000
- bid ceiling 0.88

### Standard lane
- max age 10 years
- max mileage 100,000
- reject mileage-per-year over 18,000
- bid ceiling 0.80

Any readiness or review process that still assumes a single 4-year / 50k universal model is stale.

---

## Current operationally relevant backend surfaces

### Ingest
- `webapp/routers/ingest.py`

### Analytics
- `webapp/routers/analytics.py`

### Rover
- `webapp/routers/rover.py`

### Sniper
- `webapp/routers/sniper.py`

### Sonar
- `webapp/routers/sonar.py`

### Recon
- `webapp/routers/recon.py`

These surfaces should outrank historical generic CRUD assumptions when evaluating production readiness.

---

## What is no longer valid as readiness evidence

The following are not authoritative production-readiness evidence on their own:
- synthetic validation/report generators
- obsolete security harnesses
- legacy local AI evaluation harnesses
- legacy export/deployment helpers
- legacy Codex packaging/sync scores
- local v4.7 harness behavior
- dead route assumptions in old scripts or docs

They may still exist for historical or local-use reasons, but they do not define current production readiness.

---

## What should count as production-readiness evidence

Use:
- current mounted route surface from `backend/main.py`
- current frontend config authority from `src/config/settings.ts`
- current migrations under `supabase/migrations/`
- current workflows/control-plane files
- direct live route checks
- current targeted tests tied to active surfaces

Examples of current evidence that matter more than legacy docs:
- targeted backend suites around ingest/scoring/reconciliation
- live route checks proving health/pass routes present and old route families absent
- workflow wording aligned to live two-lane scoring truth

---

## Current readiness rule

A surface is only production-authoritative if it satisfies both:
1. it is present in current live code/config authority
2. it survives current live route or current integration proof

If a script, route family, or doc fails that standard, treat it as:
- legacy
- transitional
- synthetic
- or stale

Do not let it define production readiness.
