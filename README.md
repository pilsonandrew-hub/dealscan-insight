# DealerScope

DealerScope is a vehicle arbitrage intelligence system centered on government and public-surplus auction inventory. It ingests listings, applies DealerScope business rules, scores opportunities, and exposes the current product surface through a hybrid FastAPI + Supabase + React stack.

## Current system truth

This repository is **not** a neat single-stack app.
It is a hybrid live system with:
- FastAPI backend entrypoint in `backend/main.py`
- current operational routers under `webapp/routers/`
- React frontend under `src/`
- Supabase-backed data access and migrations
- Railway-hosted backend APIs
- supporting scripts, workflows, and local harnesses

For current truth, prefer:
1. live code
2. live schema/migrations
3. frontend/backend integration points
4. workflows/control-plane files
5. docs and historical artifacts

## Current backend authority

Primary backend entrypoint:
- `backend/main.py`

Current mounted route families in `backend/main.py`:
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

Explicit live alias retained in `backend/main.py`:
- `POST /api/opportunities/{opportunity_id}/pass`

Health endpoints:
- `GET /health`
- `GET /healthz`

## Route families intentionally not treated as current production authority

The older SQLAlchemy/auth router family was removed from the main backend entrypoint because it was absent from live production surface checks and had become false authority:
- `auth`
- `vehicles`
- `upload`
- `ml`
- `opportunities`

Legacy code may still exist in the repo, but those route families are not mounted from the current main backend entrypoint.

## Frontend/API authority

Frontend code should use the centralized settings surface:
- `src/config/settings.ts`
- `settings.api.baseUrl`

Current API-base fallback pattern:
- `VITE_API_URL`
- fallback local backend: `http://localhost:8000`

The active frontend service/component tier was cleaned to stop hardcoding the Railway production origin directly.

## Current core operational surfaces

### Ingest
Primary current ingest surface:
- `webapp/routers/ingest.py`

It owns core behaviors such as:
- Apify webhook ingest
- listing normalization
- gating
- scoring
- persistence
- delivery logging
- opportunity pass handling

### Scoring
Primary scoring surface:
- `backend/ingest/score.py`

Current scoring model includes a **two-lane vehicle system**:
- Premium lane:
  - max age 4 years
  - max mileage 50,000
  - ceiling 0.88
- Standard lane:
  - max age 10 years
  - max mileage 100,000
  - reject mileage-per-year over 18,000
  - ceiling 0.80

### Condition
Condition engine:
- `backend/ingest/condition.py`

### Analytics
Current analytics/trust surface:
- `webapp/routers/analytics.py`

### Rover
Current Rover surface:
- `webapp/routers/rover.py`

### Sonar / Recon / Sniper
Current specialized route families:
- `webapp/routers/sonar.py`
- `webapp/routers/recon.py`
- `webapp/routers/sniper.py`

## Production reality that was verified

Live production checks established:

Exists in production:
- `/health`
- `/healthz`
- `/api/ingest/opportunities/{opportunity_id}/pass`
- `/api/opportunities/{opportunity_id}/pass`

Absent in production:
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

Do not use older docs, scripts, or stale route assumptions to infer live production surface.

## Local backend tests

Backend test runner:
```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
bash scripts/run_backend_tests.sh
```

Targeted backend suites used during cleanup included:
- `tests/test_ingest_scoring.py`
- `tests/test_ingest_save_fallback.py`
- `tests/test_condition_grade.py`
- `tests/test_analytics_trust_model.py`
- `tests/test_reconcile_apify_ingest_runs.py`

## Local development

Frontend and backend local assumptions now standardize on:
- frontend dev origins such as `localhost:5173` / `localhost:4173` where appropriate for dev allowlists
- backend API default `http://localhost:8000`

Do not assume older local route patterns such as `/api/health` or stale anonymous `/api/opportunities` list endpoints are current.

## Schema truth

Database truth lives in:
- `supabase/migrations/`

Important current-system rule:
- when code, scripts, or docs disagree, migrations and live route surfaces outrank historical documentation.

## Scripts and evaluation artifacts

Many legacy scripts, validation harnesses, exports, and evaluation helpers remain in the repo for local packaging, synthetic testing, or historical context.

They are **not** authoritative production truth by default.

Examples now explicitly demoted as non-authoritative or legacy-local:
- synthetic validation/report generators
- obsolete security harnesses
- local legacy export/deployment helpers
- legacy AI/Codex evaluation harnesses

Use them only after verifying their target endpoints and assumptions against current live surfaces.

## What this README is trying to prevent

This README intentionally does **not** describe the old Docker/Celery/Postgres-auth/router surface as if it were the current deployed truth.

If you are remediating DealerScope, do not start from stale route families or historical scripts.
Start from:
- `backend/main.py`
- current mounted routers
- `src/config/settings.ts`
- current frontend service usage
- `supabase/migrations/`
- live route checks
