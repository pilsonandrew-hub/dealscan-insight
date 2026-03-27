# Gemini 3.1 Pro — Complete Independent Red Team Audit
_2026-03-26 | All 6 files audited individually to avoid token limits_

---

## 🔴 CRITICAL (5 issues)

**C1 | ingest.py:881**
SSRF via unvalidated `apify_run_id` — attacker forges webhook with `"run_id": "../users/me"`, server makes authenticated Apify API calls using your APIFY_TOKEN.
FIX: `if not re.match(r'^[a-zA-Z0-9_-]{5,50}$', apify_run_id): return`

**C2 | ingest.py:1181**
IDOR in `pass_opportunity` — uses Service Role client without verifying the user owns the opportunity. Any authenticated user can corrupt any deal.
FIX: Query opportunity first, verify `user_id` matches before writing.

**C3 | ingest.py:2350**
`score_result` is undefined in `insert_alert_log` — will throw NameError and crash alert logging.
FIX: Change to `vehicle.get("score_breakdown", {}).get("dos_score", ...)`

**C4 | outcomes.py:181**
Cross-tenant data leak — `get_outcomes_summary()` ignores the returned `user_id` from `_verify_auth`. Fetches ALL users' sales margins and ROI.
FIX: Add `.eq("user_id", user_id)` filter to query.

**C5 | ds-govdeals/main_api.js:269**
DATA LOSS — `Actor.pushData(lot)` is called BEFORE `scrapeDetailPagesForVin()`. VINs are never saved to the dataset.
FIX: Move `Actor.pushData()` loop to execute AFTER `scrapeDetailPagesForVin()` completes.

---

## 🟠 HIGH (14 issues)

**H1 | score.py**
`_compute_max_bid_v2` hardcodes `0.88` for ALL vehicles — Standard lane should be `0.80`. You're overbidding on every Standard deal.
FIX: Add `tier` param, `ceiling = 0.80 if tier == "standard" else 0.88`

**H2 | ingest.py:1794**
Gov sources exempt from ALL business rules — rust bypass 8yr, age 20yr, mileage 200k. Completely violates SOP.
FIX: Remove all gov-source exceptions. Same rules apply everywhere.

**H3 | ingest.py:1809**
Rust states allowed for newer vehicles — should be unconditional reject.
FIX: Remove age bypass, reject all rust state vehicles.

**H4 | ingest.py:1828**
Missing year bypasses age check — unknown-year vehicles pass through unchecked.
FIX: Reject vehicles with missing year.

**H5 | ingest.py:1836**
Gov sources bypass 4yr max age rule (allows up to 20yr).
FIX: Remove `gov_sources` exception, enforce `max_age = 4` globally.

**H6 | ingest.py:1847**
Gov sources bypass 50k mileage rule (allows up to 200k).
FIX: Remove `is_gov` exception, enforce `max_mileage = 50000` globally.

**H7 | ingest.py:3366**
`min_margin_target` defaults to $500 — below both $1500 and $2500 SOP.
FIX: `1500 if vehicle_tier == 'premium' else 2500`

**H8 | ingest.py:1651**
`min_margin_target` stored as flat `500` in normalization path too.
FIX: Same as H7 — tier-specific value everywhere.

**H9 | ingest.py:1142-1153**
Copy-paste error — `buyer_premium_pct` and `buyer_premium` have identical fallback logic. Percentage overwrites flat fee field, corrupting financial calculations.
FIX: Separate logic for each field.

**H10 | outcomes.py:151**
`patch_outcome()` upsert missing `user_id` in payload — can create null-user rows.
FIX: Include and validate `user_id` in upsert payload.

**H11 | rover.py:204**
Rover recommendations completely ignore ALL business rules — bad deals surface to feed.
FIX: Apply age/mileage/rust/dos_score filters before ranking.

**H12 | ds-govdeals/main_api.js:87**
Max age set to 12 years instead of 4 years.
FIX: `if (year && (currentYear - year) > 4) return false;`

**H13 | ds-govdeals/main_api.js:88**
Rust state bypass for vehicles ≤2 years old.
FIX: Remove bypass. `if (HIGH_RUST_STATES.has(state)) return false;`

**H14 | ds-govdeals/main_api.js:82**
Missing max mileage check (50k) in govdeals actor entirely.
FIX: `const mileage = parseInt(item.meterCount || 0); if (mileage > 50000) return false;`

---

## 🟡 MEDIUM (5 issues)

**M1 | ingest.py:362**
`int(vehicle.get("mileage"))` crashes on comma-formatted strings like "12,000".
FIX: `int(str(vehicle.get("mileage") or 0).replace(',', ''))`

**M2 | ingest.py:1087**
Bid range $3k-$35k documented but never enforced.
FIX: `if not (3000 <= current_bid <= 35000): return None`

**M3 | ingest.py:1941**
`buyer_premium` truthiness check fails on legitimate value of `0` — zero-premium auctions get inflated cost and may be incorrectly rejected.
FIX: Use `is not None` checks.

**M4 | ds-govdeals/main_api.js:371**
Event listener pollution — detail page navigation triggers global `page.on('response')` listener, polluting `interceptedLots` with irrelevant data.
FIX: `page.removeAllListeners('request')` and `page.removeAllListeners('response')` before detail page loop.

**M5 | rover.py**
Auth error body leaks internal exception to client.
FIX: Return generic error, log internally.

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 CRITICAL | 5 |
| 🟠 HIGH | 14 |
| 🟡 MEDIUM | 5 |
| **TOTAL** | **24** |

---

## Gemini-Only Finds (Codex Missed These)

| Issue | Severity |
|-------|----------|
| SSRF via apify_run_id | 🔴 CRITICAL |
| IDOR in pass_opportunity | 🔴 CRITICAL |
| score_result NameError in alert logging | 🔴 CRITICAL |
| DATA LOSS — VINs never saved (govdeals) | 🔴 CRITICAL |
| Copy-paste fee field errors corrupting margins | 🟠 HIGH |
| maxMileage never used in ds-allsurplus | 🟠 HIGH |
| Max age 12yr in govdeals (should be 4yr) | 🟠 HIGH |
| No mileage check at all in govdeals | 🟠 HIGH |
| Bid range never enforced ($3k-$35k) | 🟡 MEDIUM |
| Mileage string crash on comma format | 🟡 MEDIUM |
| Event listener pollution in govdeals | 🟡 MEDIUM |

**11 issues Codex completely missed. 4 of them are CRITICAL.**
