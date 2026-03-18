# DealerScope — Prioritized Roadmap
Generated: 2026-03-18 (Overnight Audit by Ja'various)
Audit basis: Full codebase inspection + Playwright recon of 12 auction sites.

---

## LEGEND
- 🔴 BROKEN / BLOCKING PRODUCTION
- 🟡 GAP — needed for quality
- 🟢 ENHANCEMENT — good to have
- ⏱ Est. effort in engineer-hours

---

## PHASE 1 — FIX BROKEN PIPES
*Must do first. These are production regressions or near-misses.*

### 1.1 — Fix VITE_API_URL in Production 🔴
**File**: `src/services/roverAPI.ts` lines 83, 112
**Problem**: Falls back to `http://localhost:8000` in production — Rover API calls fail silently.
**Fix**: Set `VITE_API_URL=https://dealscan-insight-production.up.railway.app` in Railway/Vercel frontend env.
**Effort**: ⏱ 15 min (env var only, no code change)
**Impact**: Rover recommendations broken for all prod users without this.

### 1.2 — Confirm SUPABASE_SERVICE_ROLE_KEY in Railway 🔴
**File**: `webapp/routers/ingest.py` lines 111–141, `webapp/routers/rover.py` line 25
**Problem**: Ingest writes need service role key for RLS bypass. Without it, ingest fails in prod (exits at line 125).
**Fix**: Verify `SUPABASE_SERVICE_ROLE_KEY` is set in Railway env for the backend service.
**Effort**: ⏱ 10 min (verify + set in Railway dashboard)
**Impact**: All Apify webhook ingestion fails without this.

### 1.3 — Verify Apify Webhook Secret Rotation 🟡
**File**: `webapp/routers/ingest.py` line 95 — `WEBHOOK_SECRET`, `WEBHOOK_SECRET_PREVIOUS`
**Problem**: If webhook secret was rotated but not updated in Railway, all ingest calls return 401.
**Fix**: Confirm `APIFY_WEBHOOK_SECRET` in Railway matches what's set in each Apify actor's webhook config.
**Effort**: ⏱ 20 min (check Apify + Railway dashboards)

### 1.4 — Wire heuristic_scorer.py into rover.py recommendations 🟡
**File**: `webapp/routers/rover.py` lines 120–196
**Problem**: rover.py fetches from Supabase and re-ranks by Redis affinity, but `build_preference_vector()` in `backend/rover/heuristic_scorer.py` is NOT called. The heuristic scorer is defined but never invoked from rover.py — only Redis affinity is used.
**Fix**: After fetching rover_events, call `build_preference_vector(events, now_ms)` + `rank_opportunities(prefs, raw_rows)` and merge with Redis affinity signal.
**Effort**: ⏱ 1–2 hours
**Impact**: Richer cold-start recommendations; affinity fallback when Redis is cold.

### 1.5 — dealer_sales Schema + Outcomes Endpoint 🟡
**File**: `webapp/routers/outcomes.py` (exists but unverified)
**Problem**: No feedback loop for what vehicles actually sold vs. passed. Without dealer_sales, the ML loop is open.
**Fix**: Create `dealer_sales` Supabase table (opportunity_id, sold_price, sale_date, dealer_id). Verify `/api/outcomes` POST endpoint wires to it.
**Effort**: ⏱ 2–3 hours (schema + endpoint + frontend trigger)

---

## PHASE 2 — EXPAND AUCTION COVERAGE
*Add 3–5 new high-value sources. Current coverage: 9 actors.*

### 2.1 — Proxibid Scraper 🟢
**URL**: proxibid.com/for-sale/commercial-trucks, /for-sale/vehicles
**Recon findings**: Rich taxonomy — commercial trucks, specialty vehicles, trailers. No actor yet.
**Mechanism**: Category page scraping + lot detail fetch. Structured JSON-LD on lot pages.
**Effort**: ⏱ Med (6–10h) — page structure is clean but auction timing varies
**Actor name**: `ds-proxibid`
**Priority**: HIGH — large volume of commercial/fleet vehicles

### 2.2 — USGovBid Scraper 🟢
**URL**: usgovbid.com/auctions
**Recon findings**: Small site, ~40 impound vehicle lots visible, government agency auctions.
**Mechanism**: Simple auction listing page, links to auctionlistservices.com for bidding.
**Effort**: ⏱ Low (3–5h) — small site, predictable structure
**Actor name**: `ds-usgovbid`
**Priority**: MEDIUM — quick win, impound vehicles are often high-arbitrage

### 2.3 — EquipmentFacts Scraper 🟢
**URL**: equipmentfacts.com/equipmentsearch
**Recon findings**: ADESA Mercer listed (major auto auction), Indiana Auto Auction, truck auctions. Sandhills Cloud platform.
**Mechanism**: Search by category, auctioneer listings, lot detail pages
**Effort**: ⏱ Med (6–10h) — Sandhills Cloud backend may have API
**Actor name**: `ds-equipmentfacts`
**Priority**: HIGH — ADESA access is major signal for MMR alignment

### 2.4 — AllSurplus Deep Scrape 🟢
**URL**: allsurplus.com (actor ds-allsurplus already wired)
**Recon findings**: Actor exists but search URL blocked (ERR_ABORTED on /search?q=vehicle). Need to use category URL instead.
**Fix**: Update actor to use category browse URL: `/auctions?categories=vehicles` or similar.
**Effort**: ⏱ Low-Med (3–5h) — actor exists, needs URL fix
**Priority**: MEDIUM — already partially wired

### 2.5 — HiBid Vehicle Category Deep Crawl 🟢
**URL**: hibid.com/lots/700006/cars-and-vehicles
**Recon findings**: Actor ds-hibid exists. Explicit vehicle category URL confirmed.
**Fix**: Verify ds-hibid actor is crawling vehicle category specifically, not just search.
**Effort**: ⏱ Low (2–3h) — actor exists, URL confirmed
**Priority**: MEDIUM — verify existing actor hits vehicle lot page

---

## PHASE 3 — DEEPEN INTELLIGENCE
*Smarter scoring, better arbitrage signals.*

### 3.1 — Redis HSET Migration (Affinity Upgrade) 🟢
**Files**: `backend/rover/redis_affinity.py`
**Problem**: Current impl uses flat string keys (1 Redis key per dimension per user). For 50 dimensions × 1000 users = 50,000 keys. HSET is more efficient.
**Plan**: (See OVERNIGHT_PROGRESS.md Task 0.4 for full spec)
- Migrate to `HINCRBYFLOAT rover:affinity:{user_id} {dimension} {weight}`
- Lazy decay on read instead of scan-on-write
- Add `migrate_to_hset()` transition function
**Effort**: ⏱ 4–6 hours
**Impact**: 10x Redis memory efficiency, removes scan bottleneck

### 3.2 — Manheim Market API Integration 🟢
**File**: `backend/ingest/manheim_market.py` (exists, likely stub)
**Problem**: MMR estimates are currently hardcoded/estimated. Real Manheim data = much better bid ceilings.
**Fix**: Wire `MANHEIM_API_KEY` env var + implement `get_manheim_market_data()` with real API calls.
**Effort**: ⏱ 8–12 hours (API auth, rate limiting, caching)
**Impact**: Most important signal for investment grade accuracy

### 3.3 — Cross-Reference VIN Matcher 🟢
**Problem**: Same vehicle can appear on multiple auction sites. No dedup = duplicate opportunities, inflated counts.
**Fix**: VIN normalization + dedup logic in ingest pipeline. Check `opportunities` table for existing VIN before insert.
**Files**: `webapp/routers/ingest.py` line 2675 area
**Effort**: ⏱ 3–4 hours
**Impact**: Data quality, prevents false positives in alerts

### 3.4 — Condition Grade ML Refinement 🟢
**File**: `backend/ingest/condition.py` — `compute_condition_grade()`
**Problem**: Condition scoring is heuristic-based. VIN decode + description NLP would improve accuracy.
**Fix**: Add VIN decode API (NHTSA free API) + keyword classifier for description text.
**Effort**: ⏱ 6–8 hours
**Impact**: Better investment_grade accuracy, fewer Bronze mis-scores

---

## PHASE 4 — MONETIZATION & GROWTH
*Revenue-generating features and dealer retention.*

### 4.1 — Telegram Hot Deal Alerts (Fully Live) 🟢
**File**: `webapp/routers/ingest.py` — Telegram alerts already wired at line 2150.
**Current state**: Alert logic exists, Telegram send implemented. Need to verify TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID in Railway prod env.
**Fix**: Confirm env vars set, run test ingest to verify end-to-end.
**Effort**: ⏱ 30 min (verify env + test)
**Impact**: High — Andrew already using this channel

### 4.2 — Crosshair → Rover Save Intent 🟢
**Problem**: When user saves/bids in Crosshair, that intent should feed Rover preference vector.
**Fix**: Frontend event: `roverAPI.trackEvent({event: 'save', item: deal})` on Crosshair save action.
**Effort**: ⏱ 2–3 hours (frontend only)
**Impact**: Closes the feedback loop for personalization

### 4.3 — SniperScope Bid Automation MVP 🟢
**Problem**: Dealers want auto-bid up to a ceiling. Manual bidding wastes time.
**Fix**: SniperScope module — user sets max bid, system monitors auction close, fires bid at T-5 min if price is under ceiling.
**Effort**: ⏱ High (20–30h) — needs reliable auction close timing, Apify-triggered or scheduler
**Impact**: Premium feature, high dealer value

### 4.4 — Dealer Analytics Dashboard 🟢
**Problem**: No visibility into ROI per source, win rate, avg buy-vs-sell margin.
**Fix**: Analytics router + React dashboard. Requires dealer_sales table (Phase 1.5).
**Effort**: ⏱ 12–20h
**Impact**: Retention + upsell lever

### 4.5 — Subscription Tier Gating 🟢
**Problem**: All features currently free/ungated.
**Fix**: Add `plan` field to user profile. Gate SniperScope, Rover personalization, high-alert volume by plan.
**Effort**: ⏱ 8–12h (Stripe integration + middleware)
**Impact**: Monetization

---

## SUMMARY PRIORITY MATRIX

| Priority | Task | Effort | Impact |
|----------|------|--------|--------|
| P0 🔴 | Fix VITE_API_URL in prod | 15 min | Rover works at all |
| P0 🔴 | Confirm SUPABASE_SERVICE_ROLE_KEY | 10 min | Ingest works |
| P1 🟡 | Wire heuristic_scorer into rover.py | 1–2h | Better recs |
| P1 🟡 | dealer_sales schema + outcomes | 2–3h | Feedback loop |
| P2 🟢 | Proxibid scraper | 6–10h | +coverage |
| P2 🟢 | USGovBid scraper | 3–5h | Quick win |
| P2 🟢 | EquipmentFacts / ADESA | 6–10h | MMR alignment |
| P3 🟢 | Redis HSET migration | 4–6h | Efficiency |
| P3 🟢 | Manheim API | 8–12h | Score quality |
| P3 🟢 | VIN dedup matcher | 3–4h | Data quality |
| P4 🟢 | Crosshair → Rover save intent | 2–3h | Personalization |
| P4 🟢 | Telegram alerts verify | 30 min | Alerts live |
| P4 🟢 | SniperScope MVP | 20–30h | Premium feature |
| P4 🟢 | Analytics dashboard | 12–20h | Retention |
| P4 🟢 | Subscription gating | 8–12h | Revenue |

---

## CURRENT ARCHITECTURE HEALTH

**✅ Working / Solid:**
- 9 Apify actors wired + scheduled + webhooks configured
- ingest.py fully implemented (normalize → score → Supabase)
- score.py: Investment Grade, bid ceiling, DOS score formula
- rover.py: Auth, recommendations, event tracking
- redis_affinity.py: INCRBYFLOAT pattern implemented
- heuristic_scorer.py: Preference vector + decay algorithm
- alert_gating.py: Multi-signal alert evaluation
- Telegram alert sending in ingest.py
- deal-alerts.sh: Standalone Supabase → Telegram pipeline

**⚠️ Needs Attention:**
- VITE_API_URL not set in prod frontend (Rover broken)
- heuristic_scorer NOT called in rover.py (dead code path)
- Manheim API is stubbed, not live
- No VIN dedup on insert
- dealer_sales table / outcomes feedback loop missing

**🔴 Likely Broken in Prod:**
- Rover recommendations return empty (VITE_API_URL = localhost)
- May be broken if SUPABASE_SERVICE_ROLE_KEY not in Railway

---

*Generated by overnight audit agent Ja'various — 2026-03-18 03:45 AM PT*
*Full audit log: OVERNIGHT_PROGRESS.md*
