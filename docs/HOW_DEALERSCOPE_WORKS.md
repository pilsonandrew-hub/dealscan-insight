# How DealerScope Works

## Purpose

DealerScope is a vehicle arbitrage intelligence system focused on identifying profitable opportunities from government and public-surplus style auction inventory, then scoring and surfacing them through the current hybrid backend/frontend stack.

This document describes the **current verified model** at a high level. It does not treat older route families, old evaluation harnesses, or deprecated architecture assumptions as system truth.

---

## Current system shape

DealerScope is not a single neat stack.
It is a hybrid live system built from:
- FastAPI backend entrypoint: `backend/main.py`
- current operational routers in `webapp/routers/`
- frontend in `src/`
- Supabase-backed data access and migrations
- Railway-hosted backend APIs
- supporting scripts, workflows, and local-only legacy harnesses

For current truth, prefer:
1. live code
2. live migrations/schema
3. frontend/backend integration points
4. workflow/control-plane files
5. historical docs and parked reports

---

## Current product flow

At the current system level, the main DealerScope flow is:

```text
Auction/source ingest
  -> normalize
  -> gate / reject
  -> score
  -> persist qualifying rows
  -> expose current opportunity surfaces
  -> analytics / rover / sniper / saved-search / recon / sonar follow-on behavior
```

The canonical ingest/scoring path is centered on:
- `webapp/routers/ingest.py`
- `backend/ingest/score.py`
- `backend/ingest/condition.py`

---

## Current route authority

### Main backend entrypoint
- `backend/main.py`

### Current mounted route families
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
- `telegram` (callback router still mounted via separate import/include path)
- `pipeline` (legacy endpoints still present in `backend/main.py`)

### Explicit retained alias
- `POST /api/opportunities/{opportunity_id}/pass`

### Live health / operator observability routes
- `GET /health`
- `GET /healthz`
- `GET /metrics` — backend-origin only, operator-authenticated with `PIPELINE_SECRET`, excluded from OpenAPI

### Not current mounted authority anymore
The older mounted SQLAlchemy/auth router family was removed from the main backend entrypoint because it was absent from verified production route surface and had become false authority:
- `auth`
- `vehicles`
- `upload`
- `ml`
- `opportunities`

Important distinction:
- `telegram` is still mounted in the current main backend entrypoint
- `pipeline` legacy endpoints are still present in `backend/main.py`

Legacy code for some of those areas may still exist in the repo, but they are not mounted from the current main backend entrypoint.

---

## Current ingest path

The primary ingest surface is:
- `webapp/routers/ingest.py`

That surface is responsible for:
- webhook ingest
- normalization
- gating
- score invocation
- save behavior
- delivery log / reconciliation hooks
- opportunity pass handling

The current system is therefore not best understood as “frontend calls generic opportunities CRUD.”
It is better understood as a scored ingest/persistence system with specialized operational surfaces layered on top.

---

## Current scoring model

Current scoring truth lives in:
- `backend/ingest/score.py`

### Two-lane vehicle model
DealerScope currently uses a **two-lane vehicle eligibility model**.

#### Premium lane
- max age: 4 years
- max mileage: 50,000
- bid ceiling: 0.88

#### Standard lane
- max age: 10 years
- max mileage: 100,000
- reject mileage-per-year over 18,000
- bid ceiling: 0.80

### Rust-state behavior
Rust-state handling is part of the current scoring/gating rule set and must be interpreted from current code/workflow truth, not older simplified docs.

### Condition path
Condition scoring is handled through:
- `backend/ingest/condition.py`

---

## Current frontend/API behavior

Frontend code should use:
- `src/config/settings.ts`
- `settings.api.baseUrl`

That central config is the current frontend API authority.
The active frontend service/component tier was cleaned to remove direct hardcoded Railway production-origin fallbacks.

Frontend opportunity reads are largely Supabase-first, while specialized backend route families handle operational and scoring-related behavior.

---

## Current verified production surface

Verified live production checks established the following:

### Present in production
- `/health`
- `/healthz`
- `/metrics` — backend-origin only, operator-authenticated with `PIPELINE_SECRET`, excluded from OpenAPI
- `/api/ingest/opportunities/{opportunity_id}/pass`
- `/api/opportunities/{opportunity_id}/pass`

### Absent in production
- `/api/opportunities` list/detail/save/ignore/rescore routes
- `/api/vehicles/*`
- `/api/auth/*`
- `/api/upload/*`
- `/api/ml/*`
- `/api/health`
- `/api/metrics` — note: this does **not** refer to backend-origin `GET /metrics`
- `/api/ready`
- `/api/live`
- `/api/ingest/ingest-vehicle`

Any doc, script, or evaluation harness that assumes those absent routes are current production truth should be treated as stale unless re-verified.

---

## Current analytics / rover / sniper / sonar / recon role

### Analytics
Current analytics/trust surface:
- `webapp/routers/analytics.py`

### Rover
Current Rover surface:
- `webapp/routers/rover.py`

### Sniper
Current sniper surface:
- `webapp/routers/sniper.py`

### Sonar
Current sonar surface:
- `webapp/routers/sonar.py`

### Recon
Current recon surface:
- `webapp/routers/recon.py`

These are part of the current operational system and should outrank older generic route-family assumptions.

---

## What this document explicitly does not claim anymore

This document does **not** claim that DealerScope currently works like:
- an IAAI/Copart/Manheim-centered route story
- a generic old `/api/opportunities` CRUD product surface
- a live `/api/auth`, `/api/vehicles`, `/api/ml`, or `/api/upload` backend family
- a single-stack Docker/Celery/Postgres app as current deployed truth

Those older models may still appear in historical files, but they are not current verified truth.

---

## Practical rule for future remediation

When fixing DealerScope, start from:
- `backend/main.py`
- current mounted routers
- `src/config/settings.ts`
- current frontend service usage
- `supabase/migrations/`
- live route checks

Do not start from:
- deprecated route families
- synthetic validation harnesses
- legacy export/evaluation helpers
- historical docs that were written against older architecture assumptions
