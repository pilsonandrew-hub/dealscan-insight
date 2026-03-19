# OVERNIGHT PROGRESS — DealerScope Full Audit + Roadmap
Started: 2026-03-18 ~3:05 AM PT
Completed: 2026-03-18 ~3:45 AM PT
Status: ✅ ALL 5 TASKS COMPLETE

---

## AGENT STRATEGY
Each phase must be verified complete before moving to next.

---

## PHASE 0: AUDIT (current)
Goal: Full codebase + site recon before building anything.

- [x] 0.1 — Triage 6 unfinished Phase 2 items (code inspection)
- [x] 0.2 — Playwright MCP recon: scan 12 auction sites for vehicle listings
- [x] 0.3 — Rover data path trace: Apify → ingest → Supabase → scorer → frontend
- [x] 0.4 — Redis upgrade plan: document exact migration steps
- [x] 0.5 — Produce full phased roadmap → ROADMAP.md ✅

## PHASE 1: FIX BROKEN PIPES
- [x] 1.1 — Fix deal-alerts.sh actor IDs (N/A — script doesn't call actors directly; IDs in apify/deployment.json ✅)
- [x] 1.2 — Set VITE_API_URL in Railway prod env to https://dealscan-insight-production.up.railway.app ✅ (set via API 2026-03-18 5:03 PM PT)
- [x] 1.3 — Verify GovPlanet actor webhook wiring (actor present, webhook wired ✅)
- [x] 1.4 — OpenAI/Gemini fallbacks — only provenanceTracker.ts calls LLM; already has try/catch fallback ✅
- [ ] 1.5 — Create dealer_sales Supabase schema (MANUAL STEP: apply migration in Supabase SQL editor)

## PHASE 2: EXPAND AUCTION COVERAGE
- [ ] 2.1 — HiBid (has dedicated vehicle auctions, uses hibid.com API — Med effort)
- [ ] 2.2 — Municibid (government surplus, structured listings — Med effort)
- [ ] 2.3 — Proxibid (vehicles category exists — Med effort)
- [ ] 2.4 — AuctionTime (trucks category, good structure — Med effort)
- [ ] 2.5 — USGovBid (impound vehicles, small volume — Low effort)

## PHASE 3: DEEPEN INTELLIGENCE
- [ ] 3.1 — Redis Rover HINCRBYFLOAT migration (already partially done; full spec in ROADMAP.md)
- [ ] 3.2 — Manheim demand engine
- [ ] 3.3 — Cross-reference matcher

## PHASE 4: MONETIZATION PREP
- [ ] 4.1 — outcomes endpoint (POST /api/outcomes — router exists, verify schema)
- [ ] 4.2 — Telegram hot deal alerts live (wired in ingest.py ✅)
- [ ] 4.3 — Crosshair → Rover Save as Intent

---

## LOG

- 03:05 AM — Audit started.
- 03:10 AM — TASK 0.1 started: reading scripts/deal-alerts.sh, rover.py, roverAPI.ts, score.py, deployment.json, LLM call sites
- 03:25 AM — TASK 0.1 COMPLETE. See findings below.
- 03:30 AM — TASK 0.2 started: Playwright MCP recon of 12 auction sites
- 03:40 AM — TASK 0.2 COMPLETE. See site matrix below.
- 03:42 AM — TASK 0.3 COMPLETE. Rover data path fully traced.
- 03:44 AM — TASK 0.4 COMPLETE. Redis upgrade plan documented.
- 03:45 AM — TASK 0.5 COMPLETE. ROADMAP.md written.

---

## TASK 0.1 FINDINGS — TRIAGE 6 ITEMS

### 1. scripts/deal-alerts.sh — Actor IDs
**Status: ALREADY DONE ✅**
- deal-alerts.sh does NOT reference actor IDs directly — it's a Python-backed alert runner that reads Supabase.
- Actor IDs are defined in `apify/deployment.json`, not this script.
- Known good IDs confirmed present in deployment.json:
  - ds-govdeals = `CuKaIAcWyFS0EPrAz` ✅
  - ds-publicsurplus = `9xxQLlRsROnSgA42i` ✅

### 2. webapp/routers/rover.py — Fully wired?
**Status: ALREADY DONE ✅**
- File is 248 lines, fully implemented.
- Auth via Supabase JWT (`_verify_auth()` at line 96).
- GET `/api/rover/recommendations` at line 120 — fetches opportunities from Supabase, re-ranks by Redis affinity vector.
- POST `/api/rover/events` at line 198 — tracks events, writes to rover_events table, updates Redis.
- Redis affinity: imports `backend.rover.redis_affinity`, non-fatal if Redis down.
- **One gap**: `SUPABASE_SERVICE_ROLE_KEY` env var must be set in Railway for full auth (line 25 — falls back to anon key which may have RLS issues).

### 3. src/services/roverAPI.ts — Hitting real backend URL?
**Status: STILL NEEDED ⚠️**
- Lines 83 and 112: `import.meta.env.VITE_API_URL || "http://localhost:8000"`
- `VITE_API_URL` is NOT set in `.env` file — only `VITE_SUPABASE_*` vars present.
- **Fix needed**: Set `VITE_API_URL=https://dealscan-insight-production.up.railway.app` in Railway frontend env vars.
- Without this, prod frontend calls localhost:8000 (broken in production).

### 4. backend/ingest/score.py — Investment Grade tier present?
**Status: ALREADY DONE ✅**
- `_investment_grade()` function at line 222.
- Returns: "Platinum", "Gold", "Silver", or "Bronze" based on `retail_ctm_pct`, `estimated_days_to_sale`, `segment_tier`.
- `INVESTMENT_GRADE_PROXY_SCORES` dict at line 161: Platinum=100, Gold=82, Silver=64, Bronze=25.
- Used in `_weighted_score()` at line 307, `compute_bid_ceiling()` at line 411, `score_deal()` at line 850+.

### 5. apify/deployment.json — GovPlanet actor present?
**Status: ALREADY DONE ✅**
- GovPlanet actor present: `"ds-govplanet": {"id": "pO2t5UDoSVmO1gvKJ", "scheduleId": "jijJOYPk449GYMD6b", "webhookId": "SINNRTPxfC8F5szXq", "status": "enabled"}`
- Total 9 actors wired: govdeals, publicsurplus, hibid, municibid, gsaauctions, allsurplus, bidcal, auctiontime, govplanet
- All pointing to `https://dealscan-insight-production.up.railway.app/api/ingest/apify`

### 6. OpenAI/Gemini API call sites — fallback handling?
**Status: ALREADY DONE ✅**
- Only one LLM call site found: `src/ml/provenanceTracker.ts` line 202 references `gpt-4o-mini`.
- Line 213: Already has `try/catch` with warn log: "OpenAI/Gemini not available — no billing" → falls back to `inferred_null`.
- No backend Python files import openai or google AI libraries directly.
- **Note**: Manheim API is referenced (`backend/ingest/manheim_market.py`) but that's a REST API, not LLM.

---

## TASK 0.2 FINDINGS — PLAYWRIGHT SITE RECON

| Site | Has Vehicles | Search Mechanism | Build Effort | Notes |
|------|-------------|-----------------|-------------|-------|
| allsurplus.com | YES | Keyword search + category filter | Med | Heavy equipment focused, some vehicles; blocked on direct search nav |
| hibid.com | YES | Category: Cars & Vehicles + keyword | Med | Has `/lots/700006/cars-and-vehicles`; actor already wired (ds-hibid) |
| municibid.com | YES | Keyword search, gov surplus | Med | Actor already wired (ds-municibid); government surplus with vehicles |
| proxibid.com | YES | Category: Vehicles + commercial trucks | Med | Rich vehicle taxonomy; cars, trucks, specialty |
| bid4assets.com | NO | Real estate focused | High | Primarily real estate tax sales; skip |
| gsaauctions.gov | YES | Category codes filter (structured) | Low | Actor already wired (ds-gsaauctions); use category 130 for vehicles |
| usmarshals.gov/auctions | NO | Page not found (404) | — | URL dead; skip or find new URL |
| auctiontime.com | YES | Category: Trucks + equipment | Med | Trucks/trailers; actor already wired (ds-auctiontime); farm/commercial |
| usgovbid.com | YES | Browse auctions, impound vehicles | Low | Small volume; "Impound Vehicles (40 lots)" visible |
| bidcal.com | YES | Auctions list + hibid integration | Low | Redirects to bidcal.hibid.com; actor already wired (ds-bidcal) |
| govplanet.com | YES | Keyword search + browse | Low | Actor already wired (ds-govplanet); military + gov surplus |
| equipmentfacts.com | YES | Equipment search + auctioneer filter | Med | Trucks + auto auction events; ADESA Mercer listed; Sandhills Cloud |

**Priority new sites to add** (not yet wired):
1. **proxibid.com** — rich vehicle taxonomy, high volume (Med effort)
2. **usgovbid.com** — impound vehicles, small/quick win (Low effort)
3. **equipmentfacts.com** — ADESA + truck auctions (Med effort)

---

## TASK 0.3 — ROVER DATA PATH TRACE

Full path: Apify webhook → ingest.py → score.py → Supabase → rover.py → roverAPI.ts → frontend

```
[1] Apify actor runs (scheduled)
    └─ ds-govdeals, ds-publicsurplus, etc. (9 actors in deployment.json)
    └─ Webhook POST → https://dealscan-insight-production.up.railway.app/api/ingest/apify

[2] webapp/routers/ingest.py:811 — apify_webhook()
    └─ HMAC validation (APIFY_WEBHOOK_SECRET)
    └─ line ~503: extract_apify_webhook_metadata() — gets dataset ID from payload
    └─ line ~1339: normalize_apify_vehicle() — normalizes each item
    └─ line ~1600: _score_vehicle() → imports backend.ingest.score.score_deal()
    └─ line 1652: score_deal() called with normalized data

[3] backend/ingest/score.py:755 — score_deal()
    └─ _investment_grade() → Platinum/Gold/Silver/Bronze
    └─ _weighted_score() → dos_score (0-100)
    └─ compute_bid_ceiling() → max bid recommendation
    └─ Returns full scoring dict

[4] webapp/routers/ingest.py:2675
    └─ supabase_client.table("opportunities").insert(row).execute()
    └─ Also writes to alert_log (line 2150) and ingest_delivery_log (line 2367)

[5] webapp/routers/rover.py:120 — get_recommendations()
    └─ supa.table("opportunities").select("*").gte("dos_score", 65).order(...).execute()
    └─ Redis affinity re-ranking (if REDIS_URL set)
    └─ Returns serialized recommendations

[6] src/services/roverAPI.ts:112 — getRecommendations()
    └─ fetch(`${apiUrl}/api/rover/recommendations?user_id=...`)
    └─ ⚠️ BREAK POINT: apiUrl = VITE_API_URL || "http://localhost:8000"
    └─ VITE_API_URL not set in prod → calls localhost → FAILS in production

[7] Frontend components consume RoverRecommendations
```

**WHERE IT BREAKS:**
- `src/services/roverAPI.ts` line 83 & 112: `VITE_API_URL` defaults to `localhost:8000` in production.
- **Fix**: Set env var `VITE_API_URL=https://dealscan-insight-production.up.railway.app` in Railway/Vercel frontend deployment.

Secondary risk:
- `webapp/routers/rover.py` line 25: If `SUPABASE_SERVICE_ROLE_KEY` not set in Railway, falls back to anon key → RLS policies may block reads from `opportunities` table.

---

## TASK 0.4 — REDIS UPGRADE PLAN

### Current State
Redis affinity is already implemented in `backend/rover/redis_affinity.py`.
Uses `INCRBYFLOAT` (via `pipeline.incrbyfloat()`) for dimension scoring.
Works but has a decay issue: decay is applied scan-by-scan, not atomically.

### Key Schema (already live)
```
rover:affinity:{user_id}:{dimension}    → float  (INCRBYFLOAT target)
rover:last_event:{user_id}              → unix timestamp
rover:last_updated:{user_id}            → unix timestamp
rover:active_users                      → SET of user_ids
```

Dimension format examples:
- `make:ford`, `model:ford:f-150`
- `segment:tier1`, `source:govdeals`
- `price_range:mid` (low/mid/premium)

### What Moves to Redis vs Stays in Postgres

| Data | Storage | Reason |
|------|---------|--------|
| Affinity scores per dimension | Redis (HINCRBYFLOAT) | Sub-ms writes, hot path |
| Raw event log (rover_events) | Postgres | Audit trail, replay |
| Opportunities table | Postgres | Source of truth, complex queries |
| Alert log | Postgres | Compliance audit |
| User sessions/auth | Supabase (Postgres) | Security requirement |

### Recommended Migration: HSET-based (upgrade from flat keys)

Current implementation uses flat string keys (`rover:affinity:{uid}:{dim}`).
Better pattern: use Redis HASH per user for O(1) HINCRBYFLOAT:

```
HSET rover:affinity:{user_id} make:ford 4.2 model:ford:f-150 8.1 ...
HINCRBYFLOAT rover:affinity:{user_id} make:ford 1.0
HGETALL rover:affinity:{user_id}
```

**Migration steps:**
1. Add `migrate_to_hset()` in `redis_affinity.py` — scan existing flat keys, pipe into HSET, delete flat keys
2. Update `increment_affinity()` to use `pipeline.hincrbyfloat(f"rover:affinity:{user_id}", dim, weight)`
3. Update `get_affinity_vector()` to use `redis_client.hgetall(f"rover:affinity:{user_id}")`
4. Update `apply_decay()` to use `hgetall` + `hset` pipeline

### Railway Redis Connection String Format
```
REDIS_PRIVATE_URL=redis://default:{password}@{host}:{port}
# or for TLS:
REDIS_URL=rediss://default:{password}@{host}:{port}
```

Railway Redis addon provides `REDIS_PRIVATE_URL` (internal network) and `REDIS_URL` (external).
`redis_affinity.py` already reads `REDIS_PRIVATE_URL` first (line 36) ✅

### Decay Fix
Current: decay applied on-write (scan all keys for user → scale → pipeline set)
Better: store `last_decay_ts` in hash, apply lazy decay on read
```python
# On read (get_affinity_vector):
hours_since = (now - last_decay_ts) / 3600
factor = DECAY_FACTOR ** hours_since
for dim, val in hgetall(...).items():
    result[dim] = float(val) * factor
```
This avoids the expensive scan-on-write pattern.

---
