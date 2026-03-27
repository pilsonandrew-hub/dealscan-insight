# Codex vs Gemini — Full Independent Audit Comparison
_2026-03-26 | Both ran with zero knowledge of each other's findings_

---

## CRITICAL Issues

| Issue | Codex | Gemini |
|-------|-------|--------|
| Hardcoded webhook secret (ds-allsurplus:391) | ✅ | ✅ |
| SSRF via `apify_run_id` (ingest.py:881) | ❌ MISSED | ✅ NEW |
| IDOR in `pass_opportunity` — no ownership check (ingest.py:1181) | ❌ MISSED | ✅ NEW |
| Outcomes `get_outcomes_summary` leaks ALL users' data (outcomes.py:181) | ✅ (flagged as HIGH) | ✅ CRITICAL |
| Rover recommendations ignore all business rules entirely | ❌ MISSED | ✅ NEW |

**Gemini found 3 CRITICAL issues Codex completely missed.**

---

## HIGH Issues

| Issue | Codex | Gemini |
|-------|-------|--------|
| Bid ceiling hardcoded 0.88 — Standard should be 0.80 | ✅ | ✅ |
| Zero bid = infinite ROI → false hot deal alerts | ✅ | ✅ |
| Gov source gates relaxed (rust bypass 8yr, age 20yr, mileage 200k) | ✅ | ✅ |
| Mileage gate bypassed when field missing | ✅ | ✅ |
| min_margin_target stored as $500 (below SOP) | ✅ | ✅ |
| PATCH outcome missing user_id in upsert | ✅ | ✅ |
| Rover auth errors leak stack traces | ✅ | ✅ |
| Rust state filter missing from score path | ✅ | ✅ |
| Copy-paste error: buyer_premium_pct/buyer_premium identical fallback | ❌ MISSED | ✅ NEW |
| Copy-paste error: doc_fee/auction_fees identical fallback | ❌ MISSED | ✅ NEW |
| maxMileage destructured but NEVER USED in ds-allsurplus (50k cap ignored) | ❌ MISSED | ✅ NEW |
| Null year bypasses age filter in ds-allsurplus | ✅ | ✅ |
| Rust state bypass for young vehicles in ds-allsurplus | ✅ | ✅ |

---

## MEDIUM Issues

| Issue | Codex | Gemini |
|-------|-------|--------|
| Scoring failures silently marked PASSING | ✅ | ✅ |
| CURRENT_YEAR frozen at import | ✅ | ✅ |
| pass_opportunity swallows DB write failures | ✅ | ✅ |
| Duplicate check fails open on DB error | ✅ | ✅ |
| Rover select("*") memory bomb | ✅ | ✅ |
| AllSurplus memory leak (allListings buffer) | ✅ | ✅ |
| Unguarded date parsing crashes page loop | ✅ | ✅ |
| Bid range $3k-$35k documented but not enforced | ❌ MISSED | ✅ NEW |
| Mileage string "12,000" crashes canonical ID generation | ❌ MISSED | ✅ NEW |

---

## Score Card

| | Codex | Gemini | Combined |
|-|-------|--------|---------|
| CRITICAL | 1 | 5 | **5** |
| HIGH | 9 | 13 | **13** |
| MEDIUM | 7 | 9 | **9** |
| **TOTAL** | **17** | **27** | **27** |

**Gemini found 10 issues Codex completely missed — including 3 CRITICAL ones.**

---

## Full Priority Fix Order

### 🔴 FIX TODAY
1. **SSRF via apify_run_id** — active exploit, attacker can use your APIFY_TOKEN
2. **IDOR in pass_opportunity** — any user can corrupt any deal
3. **Rotate webhook secret** in ds-allsurplus
4. **Outcomes data leak** — any user sees all users' margins and ROI

### 🟠 FIX THIS WEEK
5. **Rover ignores all business rules** — surfacing invalid deals to feed
6. **Zero bid infinite ROI** — false hot deal alerts firing right now
7. **Bid ceiling 0.88 for Standard** — overbidding on Standard lane
8. **maxMileage never enforced in ds-allsurplus** — 50k cap does nothing
9. **Copy-paste fee field errors** — financial calculations corrupted
10. **Gov source gate relaxation** — all rules gutted for gov auctions

### 🟡 FIX THIS MONTH
11. Everything else in order listed above

---
_Codex (gpt-5.4-mini) — 17 issues | Gemini 3.1 Pro — 27 issues | 10 unique to Gemini_
_Files audited: score.py, ingest.py, outcomes.py, rover.py, ds-allsurplus/main.js_

---

## DeepSeek R1 — Additional Unique Findings (Codex + Gemini Missed)

### 🔴 NEW CRITICAL — score.py
- **Standard tier allows 10yr old vehicles** (STANDARD_YEAR_CUTOFF = CURRENT_YEAR - 10) — should be 4yr
- **Standard tier allows 100k miles** (line 51) — should be 50k
- **Rust states generate flags instead of rejections** — should hard-reject
- **`del state` causes NameError** in `_compute_max_bid_v2`

### 🔴 NEW CRITICAL — outcomes.py
- **Division by zero** when current_bid=0 on won outcome — crashes endpoint
- **No business rule validation** on ANY outcome recording — can mark won on rust state vehicles

### 🔴 NEW CRITICAL — govdeals main_api.js
- **API key harvesting** — scraper intercepts authenticated GovDeals traffic to steal `x-api-key` headers via MITM. This is likely a CFAA violation.
- **Intentional security bypass** — file header documents "Phase 5 recon - Token Capture + Direct API strategy"

### DeepSeek Score Card Addition
| | Codex | Gemini | DeepSeek | Combined |
|-|-------|--------|----------|---------|
| CRITICAL | 1 | 5 | 8 | **11** |
| HIGH | 9 | 14 | 15 | **20+** |
| MEDIUM | 7 | 5 | 12 | **25+** |
