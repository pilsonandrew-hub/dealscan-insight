# DealerScope — Phase 1 Forensic Reconnaissance (Cursor)

**Scope:** Read-only audit of repository state as of static analysis. **No code was changed.** Nothing herein claims remediation.

**Evidence standard:** Each item is labeled **CONFIRMED** (directly read in source), **HYPOTHESIS** (strong inference, not fully provable without runtime/infra), or **UNKNOWN** (cannot establish from repo alone).

---

## 1. System map

### 1.1 Runtime entrypoints (CONFIRMED)

| Role | Path | Notes |
|------|------|--------|
| **Canonical API** | `backend/main.py` | `uvicorn backend.main:app` per `nixpacks.toml` L60–61. Loads routers via `importlib`; registers `FastAPI` with lifespan, CORS, optional middleware. |
| **Deprecated** | `webapp/main.py`, `webapp/main_minimal.py`, `webapp/simple_main.py` | Present; `.cursorrules` states `webapp/main.py` deprecated. |
| **Frontend** | `src/main.tsx` → `App.tsx` | Vite/React; lazy-loads `EnterpriseSystemOrchestrator` after render. |
| **Packaging** | `nixpacks.toml` | Python 3.11, `requirements.txt`, Playwright Chromium install, start command above. |
| **Compose** | `docker-compose.yml` | Local multi-service layout (not re-read in full this pass; exists). |

### 1.2 HTTP routers mounted from `backend/main.py` (CONFIRMED)

Dynamic import of `webapp.routers.{auth,vehicles,opportunities,upload,ml,admin,ingest,rover,outcomes,analytics,sniper,saved_searches,vin,recon}` with prefix map L254–269:

- `/api/auth`, `/api/vehicles`, `/api/vehicles`, `/api/opportunities`, `/api/upload`, `/api/ml`, `/api/admin`
- **ingest:** prefix `""` → router defines `prefix="/api/ingest"` in `webapp/routers/ingest.py` L34
- **rover:** prefix `""` → `prefix="/api/rover"` in `webapp/routers/rover.py` L22
- **sniper / saved_searches / outcomes / analytics:** empty prefix in map; each router file sets its own `/api/...` prefix
- **vin:** `/api/vin` + router internal paths
- **recon:** `/api` + router paths
- **Alias route** on app: `POST /api/opportunities/{opportunity_id}/pass` → `ingest.pass_opportunity` L282–290

### 1.3 Background / scheduled jobs (CONFIRMED)

| Job | Location | Cadence |
|-----|----------|---------|
| Apify webhook processing | `webapp/routers/ingest.py` — `BackgroundTasks.add_task(_process_webhook_items, ...)` L1347–1354 | Per webhook |
| Sniper check | `webapp/scheduler.py` → `_run_sniper_check_internal` L16–23 | Every 5 minutes |
| GovDeals sold scraper | `scheduler.py` L26–33 | Daily 02:00 UTC |
| GovDeals active scraper | `scheduler.py` L36–44 | Cron hours `0,3,6,9,12,15,18,21` at :15 |

Scheduler starts in `backend/main.py` lifespan if import succeeds L199–201.

### 1.4 Config and environment (CONFIRMED partial list from code)

| Variable / area | Seen in |
|-----------------|---------|
| `SECRET_KEY` | `config/settings.py` L11–13 raises `RuntimeError` if unset at import; `backend/main.py` L90 also reads with dev default for separate local use |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `VITE_*` fallbacks | `webapp/routers/ingest.py` L116–121, `rover.py` L30–33, `sniper.py` L36–41 |
| `APIFY_WEBHOOK_SECRET`, `APIFY_WEBHOOK_SECRET_PREVIOUS` | `ingest.py` L101–102, `backend/main.py` L97–114 |
| `APIFY_TOKEN` / `APIFY_API_TOKEN` | `ingest.py` L165–166; `backend/main.py` L177–180 exits prod if missing |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `ingest.py` L103–104; `sniper.py` L42; `saved_searches.py` (grep) |
| `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` | `ingest.py` L105–110 (**defaults embedded — see fractures**) |
| `PIPELINE_SECRET`, `PIPELINE_BASIC_AUTH_*` | `backend/main.py` L87–89, L362–368 (`/api/pipeline/run` returns **410 Gone**) |
| `SNIPER_CHECK_SECRET` | `sniper.py` L45, L79–87 — HTTP `/api/sniper/check` only |
| `ALERTS_ENABLED` | `ingest.py` L2114–2116 kill switch for Telegram |
| `NOTION_TOKEN`, Notion DB id | `ingest.py` Notion sync (read region ~1950–2080) |
| `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` | `ingest.py` L2283–2284 |
| `ALLOWED_ORIGINS` | `backend/main.py` L237–242 |
| `DEBUG` | Docs/redoc gating `backend/main.py` L216–217 |
| `ENVIRONMENT` | Production checks in `backend/main.py`, `ingest.py` |
| Rate limits | `config/settings.py` L45–51; logged in `backend/main.py` L139–147 |

### 1.5 External integrations (CONFIRMED)

- **Apify:** dataset fetch `https://api.apify.com/v2/datasets/{id}/items` `ingest.py` L922–926; actors catalogued in `apify/deployment.json`.
- **Supabase:** Python client `create_client` in ingest, rover, sniper; direct Postgres optional via `SUPABASE_DB_*` `ingest.py` L169–198.
- **Telegram:** `api.telegram.org/bot.../sendMessage` ingest L2231; sniper L99.
- **DeepSeek:** `https://api.deepseek.com/v1/chat/completions` `ingest.py` L2354.
- **Notion:** REST `api.notion.com` `ingest.py` ~2057+.
- **Slack:** `slack.com/api/chat.postMessage` `ingest.py` L2294–2297.

---

## 2. End-to-end flow traces (code-backed)

### 2.a Apify webhook → ingest → score → Supabase (CONFIRMED)

1. **Ingress:** `POST /api/ingest/apify` `ingest.py` L1263–1276 validates `X-Apify-Webhook-Secret` via `_match_webhook_secret`.
2. **Payload:** JSON parsed L1286–1292; metadata extracted; replay/stale handling L1301–1339; `insert_webhook_log` L1341–1345.
3. **Async work:** `background_tasks.add_task(_process_webhook_items, ...)` L1347–1354 — response returns immediately L1355.
4. **Dataset pull:** `_process_webhook_items` uses `dataset_id` from metadata, GET Apify API with bearer token L918–928.
5. **Per item:** `normalize_apify_vehicle` L972–976 → optional `govdeals-sold` branch → `passes_basic_gates` L1028 → `score_vehicle` L1046–1048 calling `backend.ingest.score.score_deal` L1763–1821.
6. **Business filters:** Margin floor, Bronze reject, ceiling checks L1052–1110.
7. **Dedup:** `check_and_handle_duplicate` when `dos_score >= 50` L1113–1114.
8. **Persist:** `save_opportunity_to_supabase` L1124; **min DOS 50** to persist L2974–2978; Supabase insert or direct PG fallback L3022–3075.
9. **Downstream:** Notion sync when saved, not duplicate, `dos_score >= 65` L1175–1178.

### 2.b Frontend auth → API → data display (CONFIRMED)

1. **Auth:** `src/contexts/ModernAuthContext.tsx` — Supabase `onAuthStateChange`, `getSession`, `signInWithPassword` / `signUp` L31–112.
2. **Opportunity data:** `src/services/api.ts` L9 — `VITE_API_URL` or default Railway URL; uses `supabase` client for data paths (file continues beyond L120 with mappers/fetchers — pattern: Supabase for opportunities, Railway for ML/rover per header comment L1–4).
3. **Rover API:** `src/services/roverAPI.ts` L81, L110 — same `VITE_API_URL` default; attaches `Authorization: Bearer <access_token>` when session exists L82–89, L105–114.

**UNKNOWN:** Full list of which dashboard widgets call Supabase vs REST without reading entire `api.ts` and every page component.

### 2.c “DOS 80+” → alert gate → DeepSeek → Telegram (CONFIRMED with nuance)

**Nuance (CONFIRMED):** Ingest does **not** alert on DOS ≥ 80 alone. `hot_deals` is appended only when `save_succeeded`, listing is new (not `is_existing_listing`), save status in `{saved_supabase, saved_direct_pg}`, and `_alert_gate_for_vehicle(vehicle)` returns `eligible` L1189–1197. `_alert_gate_for_vehicle` calls `evaluate_alert_gate` from `backend/ingest/alert_gating.py` L1574–1576.

**Alert gate rules (CONFIRMED):** `evaluate_alert_gate` requires among other things: `score >= min_score` (default 80 via `AlertThresholds` / env `HOT_DEAL_MIN_SCORE` ingest L94), investment grade **Gold or Platinum** `alert_gating.py` L131, `pricing_maturity` in `{proxy, market_comp, live_market}` L133–134, trust score and confidence thresholds L136–146, positive bid headroom and several non-zero cost fields L148–157.

**AI validation (CONFIRMED):** `ai_validate_hot_deals` L2345+ posts to DeepSeek `deepseek-reasoner` L2372–2373; **INVALID** drops deal L2407–2412; **unparseable response** or **API exception** → deal **kept** (fail-open) L2413–2426.

**Telegram (CONFIRMED):** `send_telegram_alerts(validated_deals)` L1210–1211; per-deal `send_telegram_alert` enforces `ALERTS_ENABLED=="true"` L2114–2116, tokens present L2118–2120, 6h suppression, per-run cap 5 L2141–2148, **re-checks** `alert_gate` eligible L2160–2170, posts to `TELEGRAM_CHAT_ID` L2233 (not per-user).

**HYPOTHESIS:** Operational docs saying “Telegram alert ≥ DOS 80” understate dependency on pricing/trust/confidence signals populated by `score_deal` / row shape; many high-DOS deals may be blocked by gate or never reach `hot_deals`.

### 2.d Rover recommendation flow (CONFIRMED)

1. **Events:** `POST /api/rover/events` `rover.py` L274+ — JWT via `supa.auth.get_user(token)` L130–151; rate limit 10/min L287–292; insert `rover_events` L323–329; optional Redis dedup + `increment_affinity` L311–348.
2. **Recommendations:** `GET /api/rover/recommendations?user_id=&limit=` L154+ — auth must match `user_id` L162–164; query `opportunities` `dos_score >= 65`, future `auction_end_date` or null L175–181; load last 200 `rover_events`, `build_preference_vector` L214; optional Redis affinity boost L221–249; serialize via `_serialize_recommendation` L254.

### 2.e SniperScope alert flow (CONFIRMED)

1. **Arm:** `POST /api/sniper/targets` — JWT, validates opportunity and auction not ended `sniper.py` L205+.
2. **Scheduler:** `webapp/scheduler.py` calls `_run_sniper_check_internal` every 5 minutes (no HTTP secret).
3. **Check logic:** Loads active `sniper_targets`, batch-fetches `opportunities` L428–456; ceiling exceeded → status update + Telegram to **per-target** `telegram_chat_id` L477–485; T-60/T-15/T-5 windows with CAS flags on target row L535–593; `asyncio.gather` on Telegram tasks L595–599.
4. **HTTP trigger:** `POST /api/sniper/check` requires `Bearer SNIPER_CHECK_SECRET` L615–624.

**HYPOTHESIS:** In production, both in-process scheduler and external cron could theoretically double-fire if both are configured; code uses DB CAS flags to reduce duplicate alerts — **mitigation partial, not verified under load.**

---

## 3. Top 15 fractures (file + line + evidence)

| # | Severity lens | Location | Evidence (CONFIRMED unless noted) |
|---|----------------|----------|-----------------------------------|
| 1 | Security | `webapp/routers/ingest.py` L105–110 | **Default string literals** for `OPENROUTER_API_KEY` and `DEEPSEEK_API_KEY` if env unset — secrets in source; violates project security rules. |
| 2 | Logic vs docs | `webapp/routers/ingest.py` L2339–2341 vs L1189–1197 | Docstring says alerts for “DOS >= 80”; **actual** path requires full `evaluate_alert_gate` eligibility, not DOS alone. |
| 3 | Auth / UX | `src/services/roverAPI.ts` L84–89 | `Authorization` header sent **empty string** when no session; server `_verify_auth` requires Bearer token → **401**; errors swallowed in `trackEvent` catch L97–99 — silent loss of events. |
| 4 | Dual SECRET_KEY behavior | `config/settings.py` L11–13 vs `backend/main.py` L90, L183–187 | Settings import **requires** `SECRET_KEY`; main also uses `os.getenv(..., "dev-secret-change-in-prod")` for separate checks — **cognitive / env drift** risk for operators. |
| 5 | Fail-open AI | `webapp/routers/ingest.py` L2413–2426 | Unparseable DeepSeek output or API errors → deal **still alerted**. |
| 6 | Alert import fallback | `webapp/routers/ingest.py` L37–48 | If `alert_gating` import fails, stub `evaluate_alert_gate` returns **ineligible** always — **no Telegram** from gate path; silent degradation. |
| 7 | In-memory state | `backend/main.py` L151–158, L295–309 | Pipeline status dict in-process; comment says production should use Redis/DB — **lost on restart / wrong for multi-instance** (HYPOTHESIS for Railway scaling). |
| 8 | Global alert cap | `webapp/routers/ingest.py` L2141–2148 | Max 5 alerts per `run_id` per rolling hour — high-volume datasets may **drop** hot deals arbitrarily. |
| 9 | Telegram channel | `ingest.py` L2233 | Hot/platinum alerts go to **single** `TELEGRAM_CHAT_ID`; not per-user (by design in code; **product expectation** may differ — HYPOTHESIS). |
| 10 | RLS / tenancy | `webapp/routers/rover.py` L31–32 | Comment: service role **bypasses RLS**; safe for single-user — **multi-tenant risk** if extended. |
| 11 | Stale webhook = 401 | `webapp/routers/ingest.py` L1310 | `HTTPException(401, "Stale webhook payload")` — **semantic misuse** of 401 vs 400/409 (CONFIRMED code choice; operational impact UNKNOWN). |
| 12 | Deprecated entrypoints still present | `webapp/main.py` (grep) | Multiple apps; risk of wrong deploy target if not enforced in CI/CD — **UNKNOWN** whether any environment still runs them. |
| 13 | `govdeals_active` → ingest telegram | `backend/scrapers/govdeals_active.py` L368–376 (grep) | Imports `send_telegram_alert` from ingest — **tight coupling** and side effects from scraper path; failure mode “skip alerts” if import fails. |
| 14 | Background task errors | `ingest.py` `_process_webhook_items` L1246–1249 | Broad `except` logs error; webhook may already be **200 OK** — caller may assume success (CONFIRMED response pattern L1355). |
| 15 | `.env` in repo workspace | Glob found `.env` | **UNKNOWN** if committed; `.gitignore` includes `.env` L25 — **CONFIRMED** ignore rule; presence on disk is local artifact. |

---

## 4. Five business-logic risks (labeled)

1. **CONFIRMED:** Alert eligibility is **stricter** than “DOS ≥ 80” (see §2.c). Stakeholders expecting alerts for all high-DOS deals may see **none** when grade/pricing_maturity/trust/confidence/headroom signals fail gate checks.
2. **CONFIRMED:** `ai_validate_hot_deals` **fail-open** on errors means bad deals can still alert when validation is down or ambiguous.
3. **CONFIRMED:** `save_opportunity_to_supabase` skips persist when `dos_score < 50` L2974–2978 — deals below threshold **never appear** in DB/Rover pool regardless of other merits.
4. **CONFIRMED:** Bronze investment grade is **dropped before save** in ingest loop L1072–1087 — stricter than “display threshold” rules in `.cursorrules` (constitution mentions Rover display ≥65, etc.) — **alignment** between ingest filters and product rules should be verified externally (UNKNOWN full match).
5. **HYPOTHESIS:** MMR/pricing fields driving `evaluate_alert_gate` may be **proxy-derived** for many listings; gate may **block** alerts on data shape even when business judgment says “hot” (needs production row sampling).

---

## 5. Five infrastructure risks (labeled)

1. **CONFIRMED:** `nixpacks.toml` runs **Playwright Chromium install** on build — large image, attack surface, build time; **necessary** only if runtime scraping uses it (scope UNKNOWN from this file alone).
2. **HYPOTHESIS:** Railway **multi-instance** replicas: in-memory `alerts_this_run`, `_pipeline_state`, and scheduler **could duplicate** scheduled jobs or diverge unless single instance guaranteed.
3. **CONFIRMED:** `backend/main.py` L167–180 — production **exits** if `SUPABASE_SERVICE_ROLE_KEY`, `TELEGRAM_BOT_TOKEN`, `APIFY_WEBHOOK_SECRET`, or Apify token missing — **hard dependency** for boot.
4. **CONFIRMED:** `PIPELINE_SECRET` missing → pipeline auth routes 404 / disabled L188–189, L315–319 — **legacy automation** may break silently.
5. **UNKNOWN:** Actual **TLS termination, WAF, and Apify IP allowlisting** not in repo — webhook authentication relies on shared secret header (CONFIRMED ingest L1270–1276).

---

## 6. Five suspicious AI-generated / high-churn code areas (HYPOTHESIS)

*Rationale: verbose naming, enterprise scaffolding, or comment style atypical of minimal FastAPI/React cores.*

1. `src/core/EnterpriseSystemOrchestrator.ts` — loaded from `main.tsx` L27–31 with health banner DOM injection.
2. `src/core/ProductionReadinessGate.ts`, `src/core/AdvancedMetricsCollector.ts`, `src/core/UnifiedLogger.ts` — parallel “enterprise” instrumentation (paths from glob / main.tsx imports).
3. `src/utils/elite-rate-limiter.ts`, `src/utils/enhanced-circuit-breaker.ts`, `src/utils/distributedRateLimit.ts` — overlapping resilience abstractions (HYPOTHESIS: redundancy vs `api.ts` usage).
4. `webapp/routers/ingest.py` header block L5–16 — long “fixes applied” changelog in module docstring (maintenance smell; CONFIRMED text exists).
5. `webapp/routers/sniper.py` L625 `# codex_write_test` — stray marker comment (CONFIRMED).

---

## 7. Phase 2 verification commands (suggested; not executed in this audit)

```bash
# Dependency / import sanity
python -c "from backend.main import app; print([r.path for r in app.routes][:30])"

# Tests (if suite green locally)
pytest tests/ -q --tb=no 2>/dev/null | tail -20

# Secret scan (confirm no keys in tracked files)
git grep -n "sk-" -- '*.py' '*.ts' '*.tsx' ':!package-lock.json' || true

# Optional: webhook contract (against staging with mock)
# curl -i -X POST "$BASE/api/ingest/apify" -H "Content-Type: application/json" -H "X-Apify-Webhook-Secret: $SECRET" -d '{}'

# Frontend env
grep -r "VITE_" src/ --include='*.ts' --include='*.tsx' | head -40

# Scheduler registration at runtime (log scrape)
# RAILWAY: verify single replica count; grep logs for "[SCHEDULER] Started"
```

---

## 8. Statement of limitations

- **UNKNOWN:** Production Railway env values, Supabase RLS policies, and real traffic shapes.
- **UNKNOWN:** Whether `DEBUG=true` is ever set in production (would expose `/docs` per `backend/main.py` L216–217).
- No runtime tests were executed; no commits or pushes performed for this report.

---

*End of Phase 1 report — `AUDIT_PHASE1_CURSOR.md`*
