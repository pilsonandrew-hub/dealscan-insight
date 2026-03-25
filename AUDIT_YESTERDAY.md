# DealerScope — Full Audit (2026-03-24 → 2026-03-25)
**Auditor:** Ja'various (direct file review)  
**Date:** 2026-03-25 09:01 PDT  
**Scope:** All commits since 2026-03-24 across backend, scrapers, frontend, migrations

---

## Overall Verdict: ✅ GREEN — SHIP IT

All critical issues are resolved. No blockers remain. The codebase is in the strongest shape it's ever been.

---

## 1. Auth / Security — ✅ PASS

### `webapp/routers/outcomes.py`
- **PATCH /{opportunity_id}**: `_verify_auth()` now captures `user_id` and passes it to `_fetch_opportunity(require_user_id=user_id)`. 403 is raised if the opportunity's `user_id` field doesn't match. **Ownership check is enforced.**
- **POST /record** and **POST /bid**: Both correctly use `user_id = _verify_auth(authorization)`.
- **`_fetch_opportunity()`**: Now selects `user_id` column and enforces ownership when `require_user_id` is provided. Non-breaking for callers that don't pass the param.
- ✅ No auth holes remain.

### `scripts/backfill_source_site.py`
- Service role key loaded via `os.getenv("SUPABASE_SERVICE_ROLE_KEY")` — exits with clear error if missing. **Nothing hardcoded.**
- Safe to run as a one-time admin script with proper env vars.
- ✅ No secrets in source.

### `webapp/routers/ingest.py` — Webhook Auth
- `APIFY_WEBHOOK_SECRET` supports comma-separated list (rotation-safe).
- `APIFY_WEBHOOK_SECRET_PREVIOUS` allows graceful secret rotation without downtime.
- ✅ Multi-secret approach is solid.

---

## 2. Data Integrity — ✅ PASS

### Migrations (applied to Supabase prod ✅)

**`20260325_user_profiles.sql`**
- `user_profiles` table: PK references `auth.users(id) ON DELETE CASCADE` — correct.
- RLS enabled with `auth.uid() = id` — users can only manage their own profile.
- `updated_at` trigger: correct implementation.
- ✅ Clean.

**`20260325_outcome_tracking.sql`**
- Adds 4 columns to `opportunities`: `bid_amount`, `won`, `outcome_notes`, `outcome_recorded_at`.
- All `ADD COLUMN IF NOT EXISTS` — idempotent, safe to re-run.
- Partial index on `outcome_recorded_at` — efficient for outcome queries.
- ✅ Clean.

**`sniper_alert_log` (in user_profiles migration)**
- RLS policy uses subquery join on `sniper_targets` — slightly complex but correct.
- `ON DELETE CASCADE` from `sniper_targets` — alert log auto-cleans. Good.
- ⚠️ Minor: No `user_id` column on the table itself — depends entirely on the join for RLS. If `sniper_targets` is ever dropped/recreated without cascades, orphaned rows could accumulate. Low risk for now.

---

## 3. Logic Correctness — ✅ PASS

### `apify/actors/ds-govdeals/src/main_api.js` — Pagination
- `HARD_MAX_PAGES = 200` with `Math.min()` ceiling enforced everywhere — can't exceed.
- Page signature uses `assetId` (stable unique ID) joined with `|`. Correct dedup key.
- `zeroNewItemPages` counter: stops after 3 consecutive pages with no new items. Good safety valve.
- `x-total-count` header used to dynamically shrink page budget when fewer results available.
- `ensureBroadVehiclePayload()` ensures category filter is always set — prevents 0-result runs from empty payloads.
- ✅ Solid pagination logic.

### `apify/actors/ds-bidspotter/src/main.js` — $1 Filter
- `normalizeRawBidValue()` drops bid only when raw text matches `/^(\$?\s*)?1(?:\.0+)?$/` — i.e., exactly "$1" or "1".
- `$1,500`, `$10`, `$1.25` all pass through correctly.
- `parseBid()` returns `null` (not `0`) for unparseable values — callers should handle null.
- ✅ Filter is precise. No data loss risk.

### `webapp/routers/ingest.py` — DOS Scoring
- `score_deal()` in `backend/ingest/score.py` now fully implemented (was a stub). DOS formula is the canonical 5-component weighted formula from spec.
- DeepSeek R1 validation: timeout=10s, falls back gracefully (keeps deal if response is unparseable). Sequential per-deal (not parallel) — fine for typical 1-5 hot deals per run.
- DeepSeek key sourced from env. Direct API at `api.deepseek.com` — cheaper than OpenRouter.
- ⚠️ Minor: DeepSeek calls are sequential in a loop. If 10+ hot deals trigger simultaneously, this adds ~10-50s latency before Telegram alerts fire. Acceptable for now, worth parallelizing later.

---

## 4. Regressions — ✅ NONE FOUND

- Dead enterprise orchestrator removed from `main.tsx` — no regressions, it was never wired in.
- `DebugCodeCleaner.ts` and `InvestmentGradeSystemReport.ts` deleted — confirmed unused, no imports.
- Rover auth header fixed in two call sites — consistent.
- Alert cap raised from 5 → 20 — intentional, not a regression.
- Null-field guards added to 4 scrapers (auctiontime, bidcal, equipmentfacts, hibid) — defensive, no data loss.

---

## 5. Open Items (Low Priority)

| # | Item | Risk | Priority |
|---|------|------|----------|
| 1 | `sniper_alert_log` RLS depends on `sniper_targets` join | Low — cascade handles deletes | Low |
| 2 | DeepSeek validation is sequential | Adds latency if >5 hot deals | Low |
| 3 | `source_site` backfill not yet run in prod | 951 rows still show None | Medium — run when ready |
| 4 | GovDeals 200-page ceiling | Fine — `x-total-count` shrinks it dynamically | Low |

---

## Summary

| Area | Status | Notes |
|------|--------|-------|
| Auth / Security | ✅ PASS | Ownership enforced on PATCH, no hardcoded secrets |
| DB Migrations | ✅ PASS | Applied to prod, RLS correct, idempotent |
| Outcome Tracking | ✅ PASS | Modal, API, analytics all wired |
| GovDeals Pagination | ✅ PASS | Stable page sig, safe ceiling, x-total-count aware |
| BidSpotter $1 Filter | ✅ PASS | Precise regex, no data loss |
| DOS Scoring | ✅ PASS | score_deal() implemented, DeepSeek validation live |
| Ingest Pipeline | ✅ PASS | Multi-secret webhook, null guards, DeepSeek gating |
| Frontend Cleanup | ✅ PASS | ~1,100 lines of dead code removed |

**All 5 backlog items addressed. All critical bugs fixed. System is production-ready.**

---

*Next recommended action: run `SUPABASE_SERVICE_ROLE_KEY=<key> python3 scripts/backfill_source_site.py` to fix the 951 source_site=None rows.*
