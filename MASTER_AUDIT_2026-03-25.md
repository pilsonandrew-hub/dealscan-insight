# DealerScope Master Audit — 4-Model Synthesis
Models: Gemini 2.5 Pro + DeepSeek R1 + GPT-4.1 + Claude 3.7 Sonnet
Date: 2026-03-25

## DealerScope Master Audit Report

### 1. Executive Summary

The DealerScope codebase exhibits significant security vulnerabilities and a systemic failure to enforce critical business rules, posing a direct risk to business operations and data security. Critical issues include hardcoded API keys in scraper actors, multiple broken access control vulnerabilities allowing unauthorized data modification, and an unauthenticated endpoint exposing sensitive financial metrics. Furthermore, core business rules for vehicle age, mileage, and rust-state filtering are inconsistently or incorrectly implemented across the ingest pipeline, particularly within the Apify scrapers, leading to the processing of non-compliant vehicles and potential financial loss. While the backend demonstrates some resilience with database fallbacks, the combination of security flaws and business logic failures necessitates an immediate halt to deployment.

### 2. CRITICAL Findings (Security Holes, Data Loss, Business Rule Bypass)

| ID | Finding | File(s) + Line Number(s) | Model Agreement |
| :--- | :--- | :--- | :--- |
| **C-01** | **Hardcoded API Keys in Scraper Actors** | `apify/actors/ds-jjkane/src/main.js:23`<br>`apify/actors/ds-allsurplus/src/main.js:5-6`<br>`apify/actors/ds-allsurplus/src/main_api.js`<br>`apify/actors/ds-jjkane/src/main.js:30` | HIGH CONFIDENCE (Gemini, Deepseek, Claude) |
| | The Marketcheck API key is hardcoded in the `ds-jjkane` actor. The Maestro API key and subscription key are hardcoded in the `ds-allsurplus` actor. If these actors' source code is compromised or made public, these keys will be exposed, leading to service abuse, potential data exfiltration, and financial costs. | | |
| **C-02** | **Broken Access Control (IDOR) in Outcomes API** | `webapp/routers/outcomes.py:91-93`<br>`webapp/routers/outcomes.py:255-257` | HIGH CONFIDENCE (Gemini, <br>**UNCONFIRMED: Claude (partially, focuses on unauthenticated, not IDOR)**) |
| | The `create_outcome` and `create_bid_outcome` endpoints verify user authentication but fail to perform an ownership check on the `opportunity_id`. `_fetch_opportunity` is called without the `require_user_id` parameter. This allows any authenticated user to create or modify outcomes for any opportunity in the system, not just their own. | | |
| **C-03** | **Unauthenticated Financial Summary Endpoint** | `webapp/routers/outcomes.py:199`<br>`outcomes.py` (L92-120) | HIGH CONFIDENCE (Gemini, Claude) |
| | The `/outcomes/summary` endpoint has no authentication. It exposes sensitive aggregate financial data, including total gross margin, average ROI, and deal volume by outcome, to any unauthenticated party. This is a critical information disclosure vulnerability. | | |
| **C-04** | **Systemic Business Rule Bypass for Vehicle Age & Rust State** | `webapp/routers/ingest.py:1552-1560`, `1805-1812`<br>`apify/actors/ds-govdeals/src/main_api.js:93`<br>`apify/actors/ds-govplanet/src/main.js:154-156`<br>`apify/actors/ds-jjkane/src/main.js:336`<br>`apify/actors/ds-municibid/src/main.js:189-191`<br>`apify/actors/ds-bidspotter/src/main.js:379`<br>`webapp/routers/ingest.py` (~3260)<br>`webapp/routers/ingest.py` (passes_basic_gates)<br>`webapp/routers/ingest.py`, multiple<br>`apify/actors/ds-municibid/src/main.js`<br>`apify/actors/ds-jjkane/src/main.js`<br>`ingest.py` (L1138-1144) | HIGH CONFIDENCE (Gemini, Deepseek, GPT-4.1, Claude) |
| | Multiple layers of the ingest pipeline violate the Max Age (4 years) and High-Rust State rules. <br> • **Ingest Backend (`ingest.py`)**: Allows vehicles from "gov sources" to be up to 20 years old and bypasses rust state rules for vehicles up to 8 years old. This directly contradicts the non-negotiable 4-year age and 2-year rust bypass rules. <br> • **Scrapers**: Most scrapers implement their own wildly incorrect age gates (e.g., GovDeals: 12 yrs, GovPlanet: 25 yrs, JJKane: 15 yrs, Municibid: 15 yrs) and rust bypass logic (e.g., Municibid: 8 yrs, GovPlanet: 18 yrs), flooding the ingest pipeline with non-compliant vehicles. `ds-bidspotter` has no rust state filtering at all. | | |
| **C-05** | **Privilege Escalation Risk via Supabase Service Key** | `webapp/routers/rover.py:27-29`<br>`webapp/routers/ingest.py:108-111`<br>`webapp/routers/ingest.py`, throughout<br>`rover.py` (L48-55) | HIGH CONFIDENCE (Gemini, GPT-4.1, Claude) |
| | The Rover service and potentially the ingest pipeline use the `SUPABASE_SERVICE_ROLE_KEY`, which bypasses all Row Level Security (RLS). The code comment explicitly warns about this. While application-level checks are present (`auth_user_id != user_id`), this is an extremely fragile security model. A single mistake in application logic could allow any user to access or modify data for all other users. This is a critical risk, especially for a multi-tenant platform, and the service key should never be used in a request-response context. | | |
| **C-06** | **Incorrect Gross Margin Calculation** | `backend/ingest/score.py:166`<br>`webapp/routers/ingest.py:3174-3200` | HIGH CONFIDENCE (Gemini, <br>**UNCONFIRMED: Deepseek (partially, references margin on `patch_outcome` which is different)**) |
| | The core `score_deal` function calculates `gross_margin = mmr - bid`. However, the 'all-in' cost must include fees. The `build_opportunity_row` function calculates `buyer_premium` and `auction_fees`, but this happens *after* scoring. This means the `gross_margin` used for gating (`>= $1500`) and the ROI for `investment_grade` is inflated, which can lead to purchasing vehicles that do not meet the minimum profit requirements. | | |
| **C-07** | **Mileage gate: gov sources cap at 200k, not 50k as per BR** | `webapp/routers/ingest.py`, 2096–2137 | UNCONFIRMED (GPT-4.1) |
| | For non-gov sources, cap is enforced, but BR says "*all* vehicles max 50k". Discrepancy; enforcement not uniform/strict. | | |
| **C-08** | **VIN deduplication logic: only dedups if dos_score increases. Allows score reduction** | `webapp/routers/ingest.py`, 475–520 | UNCONFIRMED (GPT-4.1) |
| | Should always block re-ingest of matching VIN unless explicit record update intended (danger of lowering prior arbitrage grade). | | |

### 3. MEDIUM Findings (Correctness Issues, Edge Cases)

| ID | Finding | File(s) + Line Number(s) | Model Agreement |
| :--- | :--- | :--- | :--- |
| **M-01** | **Unsafe Type Coercion Can Crash Ingest Pipeline** | `webapp/routers/ingest.py:1533-1534`, `1539`, `1544`<br>`webapp/routers/ingest.py` (L1324-1330)<br>`backend/ingest/score.py` | HIGH CONFIDENCE (Gemini, Claude, GPT-4.1) |
| | `normalize_apify_vehicle` uses direct type casting like `int(year_raw)` and `float(item.get(...) or 0)`. If a scraper sends a non-numeric or empty string (e.g., "Unknown", "N/A"), this will raise a `ValueError` and crash the processing for that item. The entire function should be wrapped in a try/except block, and individual coercions should be defensive. | | |
| **M-02** | **Bypass of Ownership Check in Outcomes API Patch** | `webapp/routers/outcomes.py:151-152` | UNCONFIRMED (Gemini) |
| | `patch_outcome` checks for user ownership via `_fetch_opportunity(opportunity_id, require_user_id=user_id)`. However, it then proceeds to perform an `upsert` on the `dealer_sales` table using only the `opportunity_id` as a conflict key. It does not verify that the existing record in `dealer_sales` (if any) is owned by the same user, creating a potential vector for one user to overwrite the sales record of another user's opportunity. | | |
| **M-03** | **Permissive CORS Policy in Debug Mode** | `webapp/main.py:73-74` | UNCONFIRMED (Gemini) |
| | When `settings.debug` is true, the CORS policy allows all origins (`["*"]`). While intended for development, this is overly permissive. It poses a risk if debug mode is ever accidentally enabled in a staging or production-like environment. The allowed origins should be explicitly configured even for development. | | |
| **M-04** | **Inaccurate DOS Formula Component** | `backend/ingest/score.py:9` | HIGH CONFIDENCE (Gemini, <br>**UNCONFIRMED: Claude (partially, notes reliance on grade adjustment for manipulation but not formula deviation)**) |
| | The `_compute_dos_v2` function includes a `grade_adjustment` in the `Segment` component (`(segment + grade_adjustment) * 0.20`). This adjustment is not specified in the business rule's DOS formula, altering the final score from the defined standard. | | |
| **M-05** | **Inconsistent Rust State Bypass Logic** | `webapp/routers/ingest.py:1535-1541`<br>Multiple scrapers | HIGH CONFIDENCE (Gemini, Claude) |
| | In `normalize_apify_vehicle`, the rust state bypass age is defined as `max_rust_age = 8 if source_check in gov_rust_bypass else 2`. The `else 2` matches the business rule (`currentYear - 2`), but the `8` for government sources is a major deviation. This logic is duplicated in `passes_basic_gates`. This rule should be defined in one place and match the business requirements exactly. | | |
| **M-06** | **Data Integrity (VIN Parsing)** | `webapp/routers/ingest.py` (extract_vin) | UNCONFIRMED (Deepseek) |
| | Falls back to regex if VIN field missing. Risk of false positives. | | |
| **M-07** | **Margin Calculation Risk** | `webapp/routers/outcomes.py` (patch_outcome) | UNCONFIRMED (Deepseek) |
| | Uses `current_bid=0` if unset, corrupting ROI. | | |
| **M-08** | **AI Validation Fails Open** | `webapp/routers/ingest.py` (ai_validate_hot_deals) | UNCONFIRMED (Deepseek) |
| | API errors mark deals as valid. | | |
| **M-09** | **Investment grade ROI thresholds use ">= 20" and ">= 12" but may round up** | `backend/ingest/score.py` (score_deal) | UNCONFIRMED (GPT-4.1) |
| | E.g., ROI=19.95 → not platinum. Use `>=20.0` in code and doc. | | |
| **M-10** | **Null/empty/odd states (especially imported data) may sneak through scraper logic** | `webapp/routers/ingest.py`, 3631 etc | UNCONFIRMED (GPT-4.1) |
| | Add explicit fallback to reject/normalize any non-2-letter US. | | |
| **M-11** | **Commercial vehicle (fleet/cargo/box) exclusion regexes might miss some edge cases** | `apify/actors/*/src/main.js` | UNCONFIRMED (GPT-4.1) |
| | Try to keep blacklist ahead of abusive patterns, monitor drift. | | |
| **M-12** | **Scraper source-site-based gates spread through code: maintain a single config** | `webapp/routers/ingest.py`, 961–1016 | UNCONFIRMED (GPT-4.1) |
| | DRY up/centralize list of "gov" sources, and their rules. | | |
| **M-13** | **Inconsistent Bid Ceiling** | `score.py` (L186-204) | UNCONFIRMED (Claude) |
| | The bid ceiling rule (88% of MMR) is properly set via `COST_TO_MARKET_MAX = 0.88` but the final bid ceiling percent in `bid_ceiling_pct` could be miscalculated depending on data integrity. | | |
| **M-14** | **API Risk - Dependence on proprietary GovDeals API keys** | `ds-govdeals/main_api.js` (L75-95) | UNCONFIRMED (Claude) |
| | Reliance on capturing proprietary API keys from GovDeals could break if they change their authentication. | | |

### 4. LOW Findings (Code Quality, Maintainability)

| ID | Finding | File(s) + Line Number(s) | Model Agreement |
| :--- | :--- | :--- | :--- |
| **L-01** | **Deprecated Entrypoint in Use** | `webapp/main.py:2`<br>`main.py` (L1) | HIGH CONFIDENCE (Gemini, Claude) |
| | The `main.py` file is marked as deprecated, yet it is the functional entry point for the application. This is confusing and creates maintenance debt. The codebase should be refactored to use the non-deprecated entry point. | | |
| **L-02** | **Logging Overhead / PII Risk** | `webapp/routers/rover.py`<br>`webapp/routers/rover.py` | HIGH CONFIDENCE (Deepseek, GPT-4.1) |
| | Verbose logging of full vehicle titles (PII risk) or partial IDs in logs. Mask/hide PII in logs by default. | | |
| **L-03** | **Code Duplication** | `apify/actors/ds-*/src/main.js`<br>Various scrapers | HIGH CONFIDENCE (Deepseek, Claude) |
| | Repeated rust state logic across scrapers. Common functionality like state parsing is duplicated. | | |
| **L-04** | **Large/monolithic function blocks** | `webapp/routers/ingest.py` | UNCONFIRMED (GPT-4.1) |
| | Refactor into smaller reusable helpers. | | |
| **L-05** | **_Partially disabled, dead code present_** | `apify/actors/ds-hibid/src/main.js` | UNCONFIRMED (GPT-4.1) |
| | Remove/no deploy to production bundles. | | |
| **L-06** | **Some duplicate logic for error construction/record-delivery** | `webapp/routers/ingest.py` | UNCONFIRMED (GPT-4.1) |
| | Refactor for DRY and consistency. | | |
| **L-07** | **Unclear Error Handling** | `ingest.py` (L1965-1972) | UNCONFIRMED (Claude) |
| | Error messages are not always clearly communicated to the client. | | |
| **L-08** | **Magic Values** | Various files | UNCONFIRMED (Claude) |
| | Hard-coded magic values could be moved to constants. | | |

### 5. Business Rule Compliance Table

| Rule | Status | Notes |
|---|---|---|
| Bid ceiling: 88% of MMR all-in (COST_TO_MARKET_MAX=0.88) | **PARTIAL** | Enforced via `score_deal` and gating logic but issues with "all-in" calculation and potential miscalculation of `bid_ceiling_pct`. |
| Min gross margin $1,500 | **PARTIAL** | Applied pre-scoring and in ceiling logic, but `gross_margin` calculation is flawed as it excludes fees. |
| Min ROI: hot >20%, good >12% | **PARTIAL** | Logic uses `>=20`, `>=12`, but there's a risk of rounding edge-case errors. |
| Max vehicle age: 4 years | **MISSING/PARTIAL** | Consistently bypassed for government/fleet sources (up to 20 or 25 years) in ingest and scrapers. |
| Max mileage: 50k | **PARTIAL** | Loosened (200k) for gov sources (ingest.py & scrapers). |
| High-rust states REJECTED | **PARTIAL** | Bypass up to 8 years for gov sources vs. BR: 2 years. Inconsistent bypass logic across scrapers (e.g., -8, -15, -18 years). `ds-bidspotter` has no filtering. |
| Rust bypass: model year >= currentYear-2 | **PARTIAL** | Loosened to 8 years for gov sources; not per BR. |
| DOS >=80 triggers alert, >=65 shown, >=50 saved | **ENFORCED** | Gated at all entry points and alert logic is present. |
| DOS Formula | **PARTIAL** | Formula in `score.py` appears largely correct but includes an unspecified `grade_adjustment` causing deviation. |
| Scraper dedup | **PARTIAL** | VIN deduplication logic only dedups if `dos_score` increases; allows score reduction. VIN fallback weak. |

### 6. Final Verdict

**HOLD / NEEDS IMMEDIATE REVIEW**

#### Blocking Issues
The DealerScope codebase presents **critical security vulnerabilities and systemic failures to enforce core business rules**. Hardcoded API keys, unauthenticated endpoints exposing sensitive financial data, and broken access control for outcomes pose immediate risks of data breaches, financial loss, and unauthorized system manipulation. The pervasive and inconsistent bypasses of vehicle age, mileage, and rust state rules across the entire ingest pipeline will lead to the acquisition of non-compliant inventory, directly impacting profitability goals. The use of the Supabase service role key in a request-response context creates an unacceptable privilege escalation risk for a multi-tenant platform.

#### Remediation and Next Steps
1.  **Immediate Remediation**: Address all CRITICAL findings, especially hardcoded API keys, authentication/authorization gaps, and consistent enforcement of all business rules for age, mileage, and rust state.
2.  **Security Review**: Conduct a dedicated security review focused on API key management, authentication mechanisms (including multi-tenant considerations for Supabase RLS), and input validation.
3.  **Business Logic Alignment**: Synchronize all business rule logic across the scrapers, ingest pipeline, and scoring functions, ensuring a single source of truth and strict enforcement. Any deviations must be explicitly approved and documented.
4.  **Code Quality**: Prioritize refactoring of monolithic functions, addressing type safety, and eliminating duplicated code to improve maintainability and reduce the likelihood of future bugs.

**Deployment of DealerScope with the current issues carries unacceptable risks and must be halted until these critical items are thoroughly addressed and re-audited.**