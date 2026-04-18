# MEMORY.md — Ja'various Long-Term Memory

Last updated: 2026-04-03

---

## Who I Am

- **Name:** Ja'various — named by Andrew. "Cousin of Jarvis from Iron Man, Black side of the family." 😄
- **Role:** Personal AI assistant + lead engineer on DealerScope
- **Running on:** OpenClaw, Mac Computer (HQ), channel: Telegram

---

## Motto
"Money never sleeps, neither do we." — Andrew Pilson

## Who I'm Helping

- **Name:** Andrew Pilson / goes by "Gs Tyd"
- **GitHub:** pilsonandrew-hub | email: pilson.andrew@gmail.com
- **Telegram:** 7529788084
- **Location:** Southern California
- **Vibe:** Sharp on business strategy, understands dealer psychology deeply. Direct communicator — no fluff. Gets frustrated when things are promised and not followed through. Often on phone/away from HQ.
- **Context:** Vehicle industry background. Knows Manheim, MMR, dealer margins intuitively.

---

## The Main Project: DealerScope

### 📌 Pinned For Later — Enterprise Upgrade Direction (2026-04-03)
- Andrew wants DealerScope taken to the next level with enterprise-grade systems, especially around memory, operational continuity, and agent infrastructure.
- Current pinned recommendation direction:
  - build a **first-party memory system** on Supabase/Postgres
  - use **daily logs + nightly long-term consolidation**
  - add **hybrid retrieval with citations**
  - adopt **Ollama** as the local/private inference layer
  - benchmark **Gemma / Qwen / Nemotron** on real DealerScope tasks before standardizing
  - prefer **Relay.app** over GumLoop for controlled human-in-loop workflows
- Not priority/core right now: NotebookLM-style workflow as core infrastructure, MiniMax, TurboQuant.
- Long-form draft report saved at:
  `/Users/andrewpilson/.openclaw/workspace/reports/dealerscope-enterprise-ai-stack-recommendations-2026-04-03.md`

### 📌 ACTIVE — Full Migration: Claude + OpenAI → Open Source LLMs (2026-04-03)
- Anthropic ended subscription-included usage for third-party harnesses on April 4, 2026 at 12pm PT.
- Andrew has directed: move away from BOTH Claude AND OpenAI entirely. Destination is open source LLMs.
- Target stack: Ollama local inference, OpenRouter for provider-neutral routing, Qwen/Gemma/DeepSeek as primary models.
- Master agent handoff file (complete context for any new agent):
  - `/Users/andrewpilson/.openclaw/workspace/reports/MASTER-AGENT-HANDOFF-2026-04-03.md`
- Migration inventory: `reports/claude-exhaustive-inventory-2026-04-03.md` (135 files matched)
- Migration checklist: `reports/claude-to-chatgpt-oauth-prioritized-migration-checklist-2026-04-03.md`
- Status as of 2026-04-03: documentation complete. Runtime config not yet changed. Hard migration pending.
- Desired end state:
  - Open source LLM as primary runtime
  - Claude/Anthropic fully removed or emergency-fallback only
  - OpenAI fully removed or emergency-fallback only
  - All memory/docs/workflows updated to reflect new direction


### What It Is
AI-powered wholesale vehicle arbitrage platform. Scrapes government/public auctions (GovDeals, PublicSurplus) every 3hrs, scores deals using institutional dealer logic, surfaces profitable vehicles to buy below MMR and resell to dealers at Manheim.

### Business Logic (Non-Negotiable Rules)
- **Bid ceiling:** 88% of MMR all-in (COST_TO_MARKET_MAX = 0.88)
- **Min gross margin:** $1,500
- **Min ROI:** "hot" = >20%, "good" = >12%
- **Max vehicle age:** 4 years
- **Max mileage:** 50,000
- **MDS threshold:** 35 days (2026 institutional standard)
- **CPO premium:** 10–15% above standard MMR (1–3yr old, clean title)
- **DOS score to save to Supabase:** ≥50; Rover display: ≥65; Alert: ≥80
- **High-rust states REJECTED:** OH, MI, PA, NY, WI, MN, IL, IN, MO, IA, ND, SD, NE, KS, WV, ME, NH, VT, MA, RI, CT, NJ, MD, DE
- **EXCEPTION:** Vehicles ≤3 years old (model year >= current_year - 2) BYPASS the rust state rejection — newer vehicles haven't had time to rust
- **Target states:** AZ, CA, NV, CO, NM, UT, TX, FL, GA, SC, TN, NC, VA, WA, OR, HI

### DOS Formula
Margin×0.35 + Velocity×0.25 + Segment×0.20 + Model×0.12 + Source×0.08

### Three Modules
- **Crosshair** — Active targeting (user specifies what to find)
- **SniperScope** — Precision bid execution (watches specific vehicles)
- **Rover** — Passive AI (learns preferences, surfaces deals autonomously)

### Rover Event Weights
view=0.2, click=1, save=3, bid=5, purchase=8 | Decay half-life: 72 hours

### Repos
- **Main repo:** https://github.com/pilsonandrew-hub/dealscan-insight (PRIMARY)
- **Pipeline repo:** https://github.com/pilsonandrew-hub/Dealerscope (folded in)
- **Local workspace:** `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/`

### Architecture Decisions (Final, Don't Revisit)
- `backend/main.py` = canonical entrypoint; `webapp/main.py` = deprecated
- `src/` = canonical frontend; `frontend/` = deleted duplicate
- Rover is a module inside FastAPI — NOT a separate Express/TypeScript microservice
- `ModernAuthContext.tsx` = the one auth context
- 5 tabs only: Dashboard, Crosshair, Rover, Analytics, Settings
- No automated bidding
- No SaaS/multi-tenant until there are paying users
- Scraping belongs only in backend/Apify — never in browser/frontend

### Key Files
- `backend/rover/heuristic_scorer.py` — preference learning engine
- `webapp/routers/rover.py` — Rover API (/api/rover/recommendations, /api/rover/events)
- `webapp/routers/ingest.py` — Apify webhook → normalize → score → Supabase
- `backend/ingest/score.py` — DOS scoring
- `src/services/roverAPI.ts` — frontend hits real backend
- `supabase/migrations/20260310_rover_events.sql` — rover_events table with RLS
- `docs/HOW_DEALERSCOPE_WORKS.md` — full system doc
- `apify/deployment.json` — actor/schedule IDs

### What's Done (as of 2026-03-10)
- ✅ Both repos merged into unified codebase
- ✅ Five-layer institutional filter
- ✅ DOS scoring formula
- ✅ Apify actors deployed (ds-govdeals `CuKaIAcWyFS0EPrAz`, ds-publicsurplus `9xxQLlRsROnSgA42i`)
- ✅ 3hr scrape schedules + webhook configured
- ✅ Webhook ingest endpoint → Supabase
- ✅ Rover intelligence: heuristic scorer + event weighting + decay
- ✅ Rover backend API endpoints
- ✅ rover_events Supabase table (RLS)
- ✅ 5-tab clean UI
- ✅ ~25 AI noise files deleted
- ✅ Auth consolidated to ModernAuthContext
- ✅ All critical bugs fixed + committed

### Major Session — 2026-03-18 (Full Build Day)
All 4 phases of roadmap completed. Key additions:
- SniperScope bid assistant (T-60/15/5 Telegram alerts, sniper_targets table, GitHub Actions cron)
- Rover fixed (6 silent bugs, body type/price bucket/investment grade all broken, now fixed)
- Deal detail page /deal/:id — Rover click tracking funnel from Telegram alerts
- 13 Apify actors (added proxibid, usgovbid, equipmentfacts, jjkane)
- AllSurplus cracked via Maestro API (3,500+ listings/run)
- Texas state surplus added to PublicSurplus actor
- VIN extraction + dedup protocol
- NHTSA VIN decode + NLP condition scoring
- Redis HSET migration, Telegram alerts enabled, all 7 webhook secrets fixed
- Vercel token + GitHub token saved for permanent access

### What's Pending
- ✅ Backend deployed to Railway: `https://dealscan-insight-production.up.railway.app`
- ✅ Apify webhooks updated to live Railway URL
- ✅ VITE_API_URL set in Railway prod (Rover was broken, now fixed)
- ✅ Redis HSET migration done (HINCRBYFLOAT, lazy decay)
- ✅ VIN deduplication wired into ingest pipeline
- ✅ Telegram alerts enabled (ALERTS_ENABLED was false, now true)
- ✅ Heuristic scorer wired into Rover recommendations (was dead code)
- ✅ Crosshair → Rover save/bid tracking live
- ✅ Analytics dashboard built (GET /api/analytics/summary)
- ✅ SniperScope MVP built (2026-03-18) — T-60/15/5 Telegram alerts, sniper_targets table, GitHub Actions cron
- ✅ Rover fixed — 6 silent bugs (body type, price bucket, investment grade, etc.)
- ✅ Deal detail page /deal/:id — Rover click tracking funnel from Telegram alerts
- ✅ 13 Apify actors deployed
- ✅ AllSurplus cracked via Maestro API (3,500+ listings/run)
- ✅ Texas state surplus added to PublicSurplus actor
- ✅ NHTSA VIN decode + NLP condition scoring
- ✅ Scraper alerts + daily digest → Dealerscope Alerts channel (fixed 2026-03-18)
- ✅ Gemini API key fixed: [REDACTED_SECRET]
- ✅ 4-model failover: Claude Max → ChatGPT OAuth → OpenAI API gpt-4.1-mini → Gemini
- ✅ OpenAI Tier 2 unlocked (2M TPM on gpt-4.1-mini)
- ✅ Codex switched to gpt-4.1-mini

### 🔴 MANUAL STEPS REQUIRED (Andrew must do these)
- 🔴 Apply `sniper_targets` SQL in Supabase SQL Editor (table not yet created in prod)
  ```sql
  CREATE TABLE IF NOT EXISTS public.sniper_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    opportunity_id UUID NOT NULL REFERENCES public.opportunities(id) ON DELETE CASCADE,
    max_bid NUMERIC NOT NULL,
    status TEXT DEFAULT 'active',
    alert_60min_sent BOOLEAN DEFAULT FALSE,
    alert_15min_sent BOOLEAN DEFAULT FALSE,
    alert_5min_sent BOOLEAN DEFAULT FALSE,
    telegram_chat_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
  );
  CREATE INDEX IF NOT EXISTS idx_sniper_targets_user ON public.sniper_targets(user_id);
  CREATE INDEX IF NOT EXISTS idx_sniper_targets_status ON public.sniper_targets(status) WHERE status = 'active';
  ALTER TABLE public.sniper_targets ENABLE ROW LEVEL SECURITY;
  CREATE POLICY "Users can manage own sniper targets" ON public.sniper_targets FOR ALL USING (auth.uid() = user_id);
  ```
- 🔴 Add GitHub secret `SNIPER_CHECK_SECRET` = `kH9c_L2n9-pqiA39C0GFmjgZskO9e5Jst9PuUsY4a-w`
  → github.com → dealscan-insight → Settings → Secrets → Actions
- 🔴 Apply `dealer_sales` migration in Supabase SQL Editor (created Mar 14, never confirmed applied)

### 🟠 Pending Features
- 🟠 Manheim API OAuth credentials — still needed, #1 priority
- 🟡 Manheim post-sale trend engine (dynamic hot models list)
- 🟡 Cross-reference matcher (Manheim demand × Apify listings)
- 🟡 Saved searches / Crosshair alerts (built, needs testing)
- 🟡 Dealer onboarding flow (built, needs testing)
- 🟡 SniperScope full bid automation (actual bot bidding — deferred)

### ⛔ DO NOT MENTION (until ~2026-06-19)
- Stripe / subscription gating / charging dealers / onboarding other dealers
- Andrew has decided: NO charging, NO multi-tenant, NO dealer onboarding for foreseeable future (~90 days from 2026-03-19)
- DealerScope is personal use only for now. Do not suggest monetization.

### Apify Actors (as of 2026-03-18) — 9 active
- ds-govdeals `CuKaIAcWyFS0EPrAz` ✅
- ds-publicsurplus `9xxQLlRsROnSgA42i` ✅ (+ Texas state surplus added)
- ds-hibid `e8UeyRvQ6QSnX5fhP` ✅ (fixed to vehicle category URL)
- ds-municibid ✅
- ds-gsaauctions ✅
- ds-allsurplus `gYGIfHeYeN3EzmLnB` ✅ (Maestro API, 3500+ listings/run)
- ds-bidcal ✅
- ds-auctiontime ✅
- ds-govplanet `pO2t5UDoSVmO1gvKJ` ✅
- ds-proxibid `bxhncvtHEP712WX2e` ✅ (new)
- ds-usgovbid `6XO9La81aEmtsCT3g` ✅ (new)
- ds-equipmentfacts `0XjoegYZVcPldLstl` ✅ (new)

### Webhook secret (correct)
`rDyApg2UUIMl0a8ZUz_swOqsHX7HbjN-gly3xHNwiyA` — all 9 actors updated to this

---

## Credentials & Identifiers

### Supabase Direct DB
- Project: `lbnxzvqppccajllsqaaw`
- DB password: `ja'varioustheclawbot`
- Connection string: `postgresql://postgres.lbnxzvqppccajllsqaaw:ja'varioustheclawbot@aws-0-us-west-1.pooler.supabase.com:6543/postgres`

### Railway
- Token (old, expired): `c5bc110a-c58a-4e49-b181-bbfd6dd26992`
- Token (new 2026-03-24): `440362cc-6363-4625-aec3-e835a07df266`
- Token (read-only attempt): `f205ac4d-897d-4a80-a12b-1eb1da122fcd`
- ⚠️ Railway personal tokens DO NOT work with GraphQL API or CLI — all return "Not Authorized"
- Railway API access requires Team plan or service tokens (not personal tokens)
- Env var changes must be done manually via dashboard: railway.app → project → service → Variables
- Project: `exemplary-mercy` (ID: `54a9370c-89ae-41fe-ac64-c01d8c2fbaad`)
- App service: `dealscan-insight` (ID: `fbc5a039-4de7-468c-abb1-71dcdaf47f38`)
- Live URL: `https://dealscan-insight-production.up.railway.app`
- Postgres service ID: `8fa81c37-8823-4fa1-b32f-44fbafa2af4b`
- Redis service ID: `c2e53ea0-3bc4-409f-8030-e4a9e2e6ed5a`

### Vercel
- Account API Token: `[REDACTED_SECRET]`
- Project: dealscan-insight — `prj_Ya5LZmAqfQfUKpMDtyAmJQI4DjOY`
- Can manage env vars + trigger redeploys via API (no console needed) ✅

### Supabase Management API
- Token: `[REDACTED_SECRET]`
- Can run SQL migrations directly via API (no SQL editor needed) ✅

### GitHub
- PAT: `[REDACTED_SECRET]` (repo + workflow scope, no expiry)
- Repo: `pilsonandrew-hub/dealscan-insight`
- Can set secrets, trigger workflows, manage repo via API ✅

### Firecrawl
- API Key: `[REDACTED_SECRET]`
- Status: ✅ Live

### Slack (Dealerscope workspace)
- Bot Token: `[REDACTED_SECRET]`
- Channel ID: `C0ALM52FV25`
- Bot: javariousthebot @ Dealerscope workspace ✅

### Apify
- Account: `Javariousthebot` (FREE plan — do NOT upgrade until pipeline validated)
- Token: `[REDACTED_SECRET]`
- Webhook secret: `[REDACTED_SECRET]`
- ds-govdeals actor ID: `CuKaIAcWyFS0EPrAz`
- ds-publicsurplus actor ID: `9xxQLlRsROnSgA42i`
- Placeholder webhook URL: `https://dealerscope-api.com/api/ingest/apify`

### Supabase
- **OLD project** `lgpugcflvrqhslfnsjfh` — PAUSED/DEAD (9 months), do not use
- **NEW project ID:** `lbnxzvqppccajllsqaaw`
- **NEW URL:** `https://lbnxzvqppccajllsqaaw.supabase.co`
- **Anon key:** `[REDACTED_SECRET]`
- **Service role key:** `[REDACTED_SECRET]`

### OpenAI
- Key: `[REDACTED_SECRET]`
- Status: Free tier, quota=0, needs billing

### Gemini
- Key (old, free tier exhausted): `[REDACTED_SECRET]`
- Key (new, paid plan): `[REDACTED_SECRET]` ✅ Active
- Model confirmed working: `gemini-3.1-pro-preview`
- Status: ✅ Live — paid plan

### OpenRouter
- Key (old, dead): `[REDACTED_SECRET]`
- Key (new, active): `[REDACTED_SECRET]` ✅ Active
- Balance: $8.11 (as of 2026-03-26)
- Status: ✅ Live — 350+ models available
- Base URL: https://openrouter.ai/api/v1

### Telegram Bot
- Token: `[REDACTED_SECRET]`
- **Dealerscope Alerts channel ID: `-1003672399222`**
- Bot (@JarviscousinJavariousbot) is admin in the channel
- All hot deal alerts + SniperScope alerts route here

### Notion
- Integration Token: `[REDACTED_SECRET]` ("DealerScope Bot")
- Database ID: `32034c00de4c80fdae18eb02848a9f39` ("Dealerscope Deals")
- Status: ✅ Live — wired to Railway, deals will auto-sync on ingest

### Cursor
- API Key: `crsr_5711f6fab646e32c33cb1daf607187ba48ab7dc8d8d23880eec893b5ca815491`
- Status: ✅ Saved — cursor-review.yml is business rule validation only (no API calls needed)

### DeepSeek
- API Key: `[REDACTED_SECRET]`
- Base URL: `https://api.deepseek.com/v1`
- Status: ✅ Direct account — use instead of OpenRouter for DeepSeek calls
- Models: `deepseek-reasoner` (R1), `deepseek-chat` (V3)

### Perplexity
- Key: `01e7a2ff-1076-4ca1-8721-c43f19770950`

### Moonshot / Kimi
- Key: `[REDACTED_SECRET]`
- Status: ✅ Saved for MetaClaw setup

---

## Coding Agent Strategy
- **Simple tasks** → Claude Code CLI (`claude --permission-mode bypassPermissions --print`)
- **Complex tasks** → Spawn both Claude Code AND Codex, have them work independently, compare/merge best output
- **Never use Sonnet directly for coding** — wastes API quota, burns rate limits
- Codex CLI: `~/.local/bin/codex exec --skip-git-repo-check`

## ⚠️ HARD RULE — Backend Features (PERMANENT, ALWAYS ENFORCE)
**Claude Code and Codex ONLY** for the 3 core DealerScope features:
- **SniperScope** — bid assistant, alert system, sniper targets
- **Rover** — recommendation engine, heuristic scorer, Redis affinity, event tracking
- **Crosshair** — search, filters, results, deal scoring display
Sonnet/subagents handle planning, analysis, config, and deployment only. Never write backend feature code directly.

**Cross-review rule (ALWAYS):** When Claude Code builds something, Codex reviews it. When Codex builds something, Claude Code reviews it. Both must sign off before shipping.

## Paperclip (Mission Control Dashboard) — DO NOT FORGET

- **What it is:** paperclipai.com — open source AI company orchestrator. Sits above OpenClaw. Manages the full agent org chart.
- **Installed via:** `npx paperclipai` — binary at `/Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js`
- **Config dir:** `/Users/andrewpilson/.paperclip/instances/default/`
- **Dashboard URL:** http://127.0.0.1:3100/DEA/dashboard
- **Company name:** DEA (DealerScope Enterprise Agent)
- **Org chart:** 7 agents — Ja'various, Codex, Cursor, Claude Auditor, DeepSeek, Gemini, Grok
- **DB:** Embedded Postgres on port 54329
- **To START (required after reboot):**
  ```
  nohup node /Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/paperclipai/dist/index.js run > /tmp/paperclip.log 2>&1 &
  ```
- **To CHECK if running:** `curl -s http://127.0.0.1:3100/` — should return HTML
- **Logs:** `/tmp/paperclip.log` and `/Users/andrewpilson/.paperclip/instances/default/logs/server.log`
- **Does NOT auto-start** — must be launched manually or I need to add a LaunchAgent for it
- Built/set up on 2026-03-26

## Tools & Setup

- **Codex CLI:** `/usr/local/bin/codex` (v0.116.0) — ChatGPT Plus OAuth, model=gpt-5.4-mini (o3 retired)
- **Failover script:** `workspace/scripts/code-agent.sh`
- **Chromium:** `/Users/andrewpillar/Library/Caches/ms-playwright/chromium_headless_shell-1208`
- **Claude Code rate limit:** resets daily at 1pm PT
- **DealerScope skill:** `/Users/andrewpilson/.openclaw/skills/dealerscope/SKILL.md`
- **OpenClaw config:** `/Users/andrewpilson/.openclaw/openclaw.json`
- **Context compaction:** set to 0.7 threshold (applied 2026-03-10)

---

## Key Lessons

- ChatGPT Pro ≠ OpenAI API credits. Gemini subscription ≠ Gemini API credits. Both need separate billing.
- Bash scripts with apostrophes in doc text will crash (keen-nudibranch agent failure). Always escape or use heredoc.
- Rover should NOT be a separate Express/TypeScript microservice — fold into FastAPI (we analyzed SniperScope spec v1.0 and made this call explicitly).
- Redis HINCRBYFLOAT is the right pattern for affinity vectors, not Postgres writes on every event. (Pending upgrade.)
- dealscan-insight = the house. Dealerscope = the engine. Always merge into dealscan-insight.
- macOS 12 Monterey — Peekaboo will NOT install (requires Sonoma+).
- The `active_users` Redis SET + fanout precompute pattern is the right architecture for Rover at scale.
