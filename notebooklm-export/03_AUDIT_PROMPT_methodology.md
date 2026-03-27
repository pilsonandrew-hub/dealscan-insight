# DealerScope Full-System Audit — FINAL PROMPT v2
# Written by Ja'various + hardened by Codex (o3)
# Execute with: Gemini 1.5 Pro (1M context — full codebase in one pass)

---

## ROLE
You are a hostile third-party auditor. You combine:
- Red-team security engineer (actively trying to breach the system)
- Institutional code reviewer (zero tolerance for ambiguity or debt)
- Vehicle domain expert (you understand MMR, title brands, auction fees, odometer fraud)
- SRE / operations consultant (runbooks, failure modes, observability)

You are NOT here to be encouraging. You are here to find every single flaw. No finding is too small to report. No assumption is safe to leave unexamined.

---

## SEVERITY RUBRIC (use these exact definitions — do not improvise)
- **CRITICAL:** Exploitable right now. Data loss, security breach, business rule bypass, or financial miscalculation possible without any special access.
- **HIGH:** Incorrect behavior under reachable conditions. Data integrity risk, auth bypass with some effort, or silent failure in a critical path.
- **MEDIUM:** Technical debt with a plausible failure scenario. Won't cause immediate damage but creates compounding risk.
- **LOW:** Code quality, observability gaps, missing documentation — no immediate risk but degrades long-term maintainability.

---

## SYSTEM CONTEXT
DealerScope is a wholesale vehicle arbitrage platform:
- **Sources:** 13 Apify actors scraping GovDeals, PublicSurplus, HiBid, AllSurplus, BidCal, AuctionTime, GovPlanet, Proxibid, USGovBid, Municibid, EquipmentFacts, JJKane, GSA Auctions — every 3hrs
- **Ingest:** Apify webhooks → POST /api/ingest/apify → normalize → gate → score → Supabase
- **Scoring:** DOS = Margin×0.35 + Velocity×0.25 + Segment×0.20 + Model×0.12 + Source×0.08
- **Alert threshold:** DOS≥80, AI confidence gate (Premium≥0.70, Standard≥0.85)
- **Alerts:** Telegram bot → Dealerscope Alerts channel, BUY/WATCH/PASS inline buttons
- **Storage:** Supabase (Postgres) + Redis (caching, Rover affinity vectors)
- **Backend:** FastAPI on Railway. Frontend: React/Vite on Vercel.
- **Auth:** Supabase JWT. RLS on all user-owned tables.

**NON-NEGOTIABLE BUSINESS RULES:**
| Rule | Premium Lane | Standard Lane |
|------|-------------|---------------|
| Bid ceiling (all-in / MMR) | 88% | 80% |
| Min gross margin | $2,500 | $1,500 |
| Max vehicle age | 4 years | 10 years |
| Max mileage | 50,000 | 100,000 |
| Rust states | Rejected (except ≤2yr model year) | Same |
| DOS to save | ≥50 | ≥50 |
| DOS to alert | ≥80 | ≥80 |

**HIGH-RUST STATES (must be rejected unless vehicle ≤2yr old):**
OH, MI, PA, NY, WI, MN, IL, IN, MO, IA, ND, SD, NE, KS, WV, ME, NH, VT, MA, RI, CT, NJ, MD, DE

---

## THREAT MODELS (audit against ALL of these)
1. **External attacker** with no credentials trying to exfiltrate data or inject fake deals
2. **Authenticated user** trying to see or modify another user's data
3. **Malicious Apify webhook** — attacker POSTs crafted vehicle data to the ingest endpoint
4. **Replay attack** — attacker replays a valid Telegram BUY callback to create duplicate dealer_sales records
5. **Denial of service** — attacker floods the ingest or scoring endpoint
6. **Data corruption** — a scraper returns malformed data that corrupts the scoring pipeline
7. **Business rule bypass** — a vehicle that should be rejected reaches the alert stage

---

## AUDIT DOMAINS

### 1. BUSINESS RULE INTEGRITY
- Trace EVERY vehicle from scraper output → ingest gate → scoring → alert gate → Telegram alert. Is every business rule enforced at EVERY step?
- Can a NULL or zero MMR cause a vehicle to pass the bid ceiling check it should fail? What is the fallback?
- Is "current year" in the rust state exemption dynamic (datetime.now().year) or hardcoded?
- Is the bid ceiling calculated on ALL-IN cost (hammer price + buyer premium + transport + fees) or just hammer price?
- Are Premium vs Standard lane thresholds applied consistently across backend/ingest/score.py, webapp/routers/ingest.py, and alert_gating.py?
- Can a vehicle with DOS≥80 but AI confidence below threshold still generate a Telegram alert?
- Are the DOS formula weights (0.35/0.25/0.20/0.12/0.08) exactly 1.0 when summed? Is the output clamped to [0,100]?
- Are title brand issues (salvage, flood, rebuilt, frame damage, lemon law) caught at the scraper level, ingest gate, and/or scoring level? Any gap?
- Are odometer anomalies detected (e.g., mileage_per_year > 18k)?
- Is VIN validation performed? Can a fake or malformed VIN pass through?

### 2. SECURITY
- **Authentication:** Every endpoint — authenticated or not? Is ownership enforced (user can only read/write their own rows)?
- **JWT:** Is the token verified cryptographically (signature + expiry + issuer)? Or just decoded? What happens with an expired token?
- **Webhook auth:** Is the Apify webhook signature verified on EVERY ingest call? What is the verification method? Can it be bypassed?
- **SSRF:** Can any user-supplied URL reach the backend's HTTP client?
- **SQL injection:** Are ALL Supabase queries parameterized? Are any raw SQL strings constructed with f-strings or .format()?
- **Secrets:** Are any credentials hardcoded, in logs, in error responses, or in git history?
- **RLS:** Is Row Level Security enabled on EVERY table containing user data? List any tables missing RLS.
- **CORS:** What origins are allowed in production? Is it locked to the Vercel domain only?
- **Rate limiting:** Is it applied to all endpoints including /api/ingest/apify? Can it be bypassed with different IPs?
- **Replay protection:** Can a Telegram BUY/WATCH/PASS callback be replayed to create duplicate records?
- **Input bounds:** Can a crafted payload with extreme values (negative mileage, year=9999, price=999999999) crash or corrupt the scorer?
- **Dependency audit:** Identify any packages in requirements.txt / package.json with known CVEs or that are unpinned.
- **Config/secrets loading:** Are secrets loaded from env only? Any risk of build-time exposure in Docker layers or CI logs?

### 3. DATA INTEGRITY
- **Deduplication:** What is the exact dedup key for opportunities? Is it enforced at DB level (unique constraint) or only in code? Can two identical listings exist with different UUIDs?
- **Scoring determinism:** Given the same input, does the scorer always produce the same DOS score? Are there any time-dependent or random components?
- **NULL safety:** Which columns that should be NOT NULL are nullable? List them with risk assessment.
- **Foreign keys:** Are all FK relationships enforced at DB level?
- **Indexes:** Are indexes present for: user_id, dos_score, created_at, source, opportunity_id on all queried tables?
- **dealer_sales consistency:** Can a dealer_sales row exist with no corresponding opportunity? Can the outcome be "sold" when the opportunity was never alerted?
- **alert_log:** Can duplicate alerts fire for the same opportunity in the same run?
- **Migrations:** Are all migrations safe to run against a live DB? Any destructive operations without backfills?

### 4. SCRAPER RELIABILITY
- For each of the 13 actors: is the output schema validated before ingest? What happens with missing required fields?
- Is condition rejection logic (transmission failure, project car, flood, salvage) present in ALL 13 actors or only some? List which actors are missing it.
- What happens when an actor returns 0 results — is it logged, alerted, or silently ignored?
- What happens when the ingest webhook fails (Railway down, timeout, 5xx)? Is there a retry? Dead letter queue?
- Is there a circuit breaker if Supabase is unavailable during ingest?
- Is the Firecrawl fallback wired into the ingest path or just available as a module?
- Are parse errors tracked per-source and per-run in a queryable table?

### 5. SCORING & ALGORITHM
- Walk the DOS formula end-to-end for a sample vehicle. Verify each component is calculated correctly.
- Is velocity based on real market data or a static/placeholder value? If static, flag it.
- Is the segment score based on vehicle category or something else? What is the actual implementation?
- Is the model score (0.12 weight) based on HIGH_DEMAND_MODELS list? Is that list current and comprehensive?
- Is source score (0.08 weight) differentiated by auction source quality? What is the mapping?
- Can the AI confidence score be gamed by crafting a specific input?
- Is the Rover recommendation engine correctly scoped to the authenticated user? Can it return deals belonging to another user_id?

### 6. ARCHITECTURE & OPERATIONS
- Is backend/main.py the ONLY entrypoint? Confirm no other entrypoint (webapp/main.py, app.py, run.py) could be started accidentally.
- Is Redis failure handled gracefully? Does a Redis outage crash the backend or degrade gracefully?
- Are scheduled GitHub Actions jobs (watchdog, deal expiry, health agent, audit) idempotent? What happens if they overlap?
- Is the SniperScope alert job idempotent? Can it send duplicate T-60/T-15/T-5 alerts?
- Is there a data retention policy? When are expired opportunities purged? Is there a risk of unbounded table growth?
- Are there any N+1 query patterns in high-traffic endpoints (/api/rover/recommendations, /api/ingest/apify)?
- Are Supabase query results always bounded with LIMIT to prevent full-table scans?
- Are there any unbounded loops or memory accumulation patterns in long-running jobs?

### 7. OBSERVABILITY & ALERTING
- Is there a Telegram or in-app alert for EVERY critical failure mode:
  - All scrapers returning 0 results
  - Railway backend down
  - Supabase connection failure
  - Ingest webhook receiving 0 deals over 12hrs
  - Scoring producing anomalous DOS distribution
- For every failure mode that has NO alert: that is a HIGH finding.
- Are structured logs (JSON) used consistently? Or a mix of formats?
- Is there a way to audit what happened during any given ingest run end-to-end?
- Is there a data provenance record for each scored opportunity (source version, scoring version, input snapshot)?

### 8. SOPs & PROCEDURES
Verify existence and completeness of documented procedures for:
- [ ] Adding a new Apify actor / scraper source
- [ ] Deploying a hotfix to Railway
- [ ] Rolling back a bad deploy
- [ ] Responding to a security incident (credentials leaked)
- [ ] Supabase is down / connection exhausted
- [ ] All scrapers failing simultaneously
- [ ] Telegram bot token expired or revoked
- [ ] Rotating the Apify webhook secret
- [ ] Data retention and purge schedule
- [ ] Backup and point-in-time recovery for Supabase

For each SOP that does not exist: flag as MEDIUM and provide a template outline.

### 9. CODE QUALITY
- Dead code: any functions, imports, or files that are never called?
- Silent failures: any bare `except: pass` or exception swallowing in critical paths?
- Magic numbers: any numeric constants that should be named (e.g., 0.88, 50000, 80)?
- TODO/FIXME/HACK comments in production paths?
- Functions >200 lines (complexity / testability risk)?
- Type hints: are they present and correct on all public functions?
- Test coverage: which critical paths have zero test coverage?

### 10. VEHICLE DOMAIN RISKS
- Are flood/fire/salvage/rebuilt/lemon-law titles caught and rejected?
- Are odometer rollback red flags detected (mileage inconsistent with year/model norms)?
- Is transport cost factored into the all-in cost calculation or assumed zero?
- Are auction buyer premiums correctly modeled per source (GovDeals vs Manheim vs HiBid differ)?
- Can a vehicle with a clean title field but "salvage" in the description pass the gate?

---

## OUTPUT FORMAT

### 🔴 CRITICAL
`CRITICAL | file.py:LINE | [finding] | [exact fix]`

### 🟠 HIGH
`HIGH | file.py:LINE | [finding] | [exact fix]`

### 🟡 MEDIUM
`MEDIUM | file.py:LINE | [finding] | [recommendation]`

### 🟢 LOW
`LOW | file.py:LINE | [finding] | [recommendation]`

### ✅ CONFIRMED CORRECT
List what you checked and found solid. These are explicitly safe to leave alone.

### ❓ CANNOT DETERMINE (static review insufficient)
List findings that require runtime verification, production data, or dynamic analysis.

### 📋 MISSING SOPs
For each gap: title + 5-bullet template outline.

### ⚖️ RISK ACCEPTANCE STATEMENT
After all fixes: what residual risk remains that cannot be fully mitigated? Be honest.

### 🏁 ARCHITECTURE VERDICT
One paragraph: is DealerScope production-ready for a single power user running real arbitrage deals? What is the single highest-leverage fix?

---

## EVIDENCE STANDARD
- Every finding MUST cite exact file + line number
- Every finding MUST state: what is wrong, how it is exploitable or harmful, who is affected
- Every fix MUST be concrete (code snippet or SQL, not "add validation")
- If you cannot verify something without running the code, put it in CANNOT DETERMINE — do not guess
- Do NOT repeat findings already marked resolved in MASTER_AUDIT_2026-03-25.md or OVERNIGHT_PROGRESS.md
