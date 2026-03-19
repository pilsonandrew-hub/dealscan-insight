# MEMORY.md — Ja'various Long-Term Memory

Last updated: 2026-03-10

---

## Who I Am

- **Name:** Ja'various — named by Andrew. "Cousin of Jarvis from Iron Man, backside of the family." 😄
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
- ✅ Gemini API key fixed: AIzaSyCFl6jhR9T2L2sAJOgKslGmSwz1qwivCvM
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
- 🟠 Manheim API OAuth credentials — still needed, #1 SOW priority
- 🟡 Manheim post-sale trend engine (dynamic hot models list)
- 🟡 Cross-reference matcher (Manheim demand × Apify listings)
- 🟡 Subscription tier gating (Stripe) — selected as priority #2 after SniperScope
- 🟡 Saved searches / Crosshair alerts
- 🟡 Mobile UI polish
- 🟡 Dealer onboarding flow (seeds Rover on first login)
- 🟡 VIN scanner on mobile (camera → instant scoring)
- 🟡 Notion integration (discussed Day 1, never built)
- 🟡 SniperScope full bid automation (actual bot bidding — deferred)

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
- Token: `c5bc110a-c58a-4e49-b181-bbfd6dd26992`
- Project: `exemplary-mercy` (ID: `54a9370c-89ae-41fe-ac64-c01d8c2fbaad`)
- App service: `dealscan-insight` (ID: `fbc5a039-4de7-468c-abb1-71dcdaf47f38`)
- Live URL: `https://dealscan-insight-production.up.railway.app`
- Postgres service ID: `8fa81c37-8823-4fa1-b32f-44fbafa2af4b`
- Redis service ID: `c2e53ea0-3bc4-409f-8030-e4a9e2e6ed5a`

### Apify
- Account: `Javariousthebot` (FREE plan — do NOT upgrade until pipeline validated)
- Token: `apify_api_Vaz9Ij2D5E42LA7cHF39jnMVzpVHID3nuspZ`
- Webhook secret: `sbEC0dNgb7Ohg3rDV`
- ds-govdeals actor ID: `CuKaIAcWyFS0EPrAz`
- ds-publicsurplus actor ID: `9xxQLlRsROnSgA42i`
- Placeholder webhook URL: `https://dealerscope-api.com/api/ingest/apify`

### Supabase
- **OLD project** `lgpugcflvrqhslfnsjfh` — PAUSED/DEAD (9 months), do not use
- **NEW project ID:** `lbnxzvqppccajllsqaaw`
- **NEW URL:** `https://lbnxzvqppccajllsqaaw.supabase.co`
- **Anon key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxibnh6dnFwcGNjYWpsbHNxYWF3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMyMDE0NzEsImV4cCI6MjA4ODc3NzQ3MX0.NkgR_s5Zru3Y24HlGXrE4BzOkCoyQfHQRg317QuFNQI`
- **Service role key:** `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxibnh6dnFwcGNjYWpsbHNxYWF3Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3MzIwMTQ3MSwiZXhwIjoyMDg4Nzc3NDcxfQ.gLFMWuEVDbwMMHYL1CPRwNv1oGukhBTFYZGYTuXftSg`

### OpenAI
- Key: `sk-proj-WCHpaZar...` (full key in openclaw.json)
- Status: Free tier, quota=0, needs billing

### Gemini
- Key: `AIzaSyCFl6jhR9T2L2sAJOgKslGmSwz1qwivCvM` ("Gemini ChatClaw Api")
- Status: ✅ Live — 45 models available, free tier

### Telegram Bot
- Token: `8770839167:AAEPvbNtS5Fr3LPmoEUM-9CJ14r7OXhIgzI`
- **Dealerscope Alerts channel ID: `-1003672399222`**
- Bot (@JarviscousinJavariousbot) is admin in the channel
- All hot deal alerts + SniperScope alerts route here

### Perplexity
- Key: `01e7a2ff-1076-4ca1-8721-c43f19770950`

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

## Tools & Setup

- **Codex CLI:** `~/.local/bin/codex` (v0.113.0) — installed but OpenAI has no billing credits
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
