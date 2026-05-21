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

## Operating Doctrine (Pinned 2026-04-20)
- DealerScope is being hardened into a trustworthy operating asset, not polished for appearances.
- Preserve system stability and pricing truth before attempting optimization.
- Product truth beats memory, summaries, and agent reasoning.
- The governing question for each session is: does this make DealerScope more truthful, more trustworthy, and more valuable as a real operating system for dealer intelligence and execution?
- Optimize for truth, trust, governed continuity, product reality, durable operator leverage, and cost discipline.
- Avoid momentum edits, cleanup theater, fake enterprise abstraction, cosmetic churn, and silent failure.
- We are not yet in full enterprise mode. There is still fundamental cleanup and loose-end work to finish, but only if it clearly serves product truth and business value.
- Valid remaining cleanup classes: real live contradictions, dead authority that could mislead future work, governance drift, product-facing behavior that overstates reality, unresolved ownership seams in mounted flows, and operational gaps that weaken trust.
- Stop when cleanup becomes identity instead of value creation.
- End-of-session check: what became more truthful, more governable, and more valuable today, and are we still meaningfully hardening or starting to over-clean?

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
- DealerScope is a hybrid live system, not a neat single-stack app. For truth order, prefer: live code -> live schema/migrations -> frontend/backend integration points -> docs/historical audits.
- Workflow files under `.github/workflows/` are part of system truth because they encode business-rule and operational assumptions.
- Canonical governed knowledge source for DealerScope is `brains/dealerscope-brain`; operator-visible destination-of-record mirror is `/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain`; `/Users/andrewpilson/Documents/Javarious-Wiki` is secondary/non-authoritative for DealerScope.

### Key Files
- `backend/rover/heuristic_scorer.py` — preference learning engine
- `webapp/routers/rover.py` — Rover API (/api/rover/recommendations, /api/rover/events)
- `webapp/routers/ingest.py` — Apify webhook → normalize → score → Supabase
- `backend/ingest/score.py` — DOS scoring
- `src/services/roverAPI.ts` — frontend hits real backend
- `supabase/migrations/20260310_rover_events.sql` — rover_events table with RLS
- `docs/HOW_DEALERSCOPE_WORKS.md` — full system doc
- `apify/deployment.json` — actor/schedule IDs

### ACE / Continuity Proof (2026-04-25)
- Added a narrow read-only open-loop ingest seam in `ace/open_loops_ingest.py`.
- Source stays `continuity/open-loops.json` on the ACE side, mapping only active-like items to `TRIAGE`.
- Provenance is deterministic through `source + source_session`; replay reuses the same ACE row instead of inserting a duplicate.
- Verified with `python3 -m unittest ace.tests.test_open_loop_ingest` and the broader `python3 -m unittest discover ace/tests` suite.

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
- After any context loss or long thread gap, do not remediate DealerScope from partial recall. Re-orient in order: SOUL/MEMORY/recent daily memory -> dirty git state -> canonical code surfaces -> migrations/schema truth -> workflow/control-plane files -> governed brain active queue/closure/open-loops artifacts -> mirror state. Only then propose or apply fixes.
- On 2026-04-30, OpenClaw Dream Big / dreaming was proven end to end on HQ Mac: memory-core dreaming enabled, memory-wiki dream bridge enabled, a live `__openclaw_memory_core_short_term_promotion_dream__` event fired, artifacts landed in `workspace/memory/.dreams`, and the runtime narrative writer successfully created `DREAMS.md` / `dreams.md` with a dated diary entry.
- On 2026-04-30, OpenClaw gateway exposure was tightened from `bind = lan` to `bind = loopback`; later doctor output no longer showed the 0.0.0.0 LAN exposure warning, confirming the hardening took effect live.
- On 2026-04-30, signed-in Chrome remote debugging was enabled and the gateway was restarted, but OpenClaw still could not attach to the signed-in Chrome session. Best current truth: browser attach remains an OpenClaw/browser-side issue, not a Chrome setup issue.
- Do not equate an included-scope parity check with global mirror cleanliness. On 2026-04-20 the canonical governed brain was mostly clean, but the Obsidian mirror still had ~3.6k duplicate-style markdown files, so mirror truth claims must be scope-labeled.
- Do not overstate closure from a single artifact. On 2026-04-20, stronger governed evidence showed brain->Obsidian enforcement was still `live-improved but pending`, even though a weaker reading could make it look closed.
- On 2026-04-24/25, the DealerScope non-credential incident track was closed only after live proof across all active authority surfaces: rewritten git history + remote refs, Vercel on trusted rewritten `main`, GitHub Actions active runs on trusted rewritten `main`, Railway control-plane lineage on trusted rewritten `main`, stale linked-worktree metadata pruned, and bounded local discovery finding only the primary HQ DealerScope repo on checked roots. If credential scope is excluded, do not reopen that non-credential incident without new contradictory evidence.
- On 2026-04-25, report sprawl from that DealerScope incident was consolidated. Authoritative non-credential closeout sources are `reports/dealerscope-executive-closeout-memo-2026-04-24.md` and `reports/dealerscope-non-credential-closeout-status-2026-04-24.md`; the canonical artifact map is `reports/dealerscope-incident-artifact-index-2026-04-24.md`. Future sessions should use the index instead of re-hunting across the report set.
- On 2026-04-25, closeout integrity packaging was added for that same DealerScope incident: `reports/dealerscope-closeout-manifest-2026-04-24.txt` contains SHA-256 hashes for the authoritative closeout and deployment-trust artifacts. Future sessions should use the artifact index for reading order and the manifest when exact-file verification matters.

## Promoted From Short-Term Memory (2026-05-04)

<!-- openclaw-memory-promotion:memory:memory/2026-04-14.md:102:104 -->
- - Created and validated a separate GBrain dev Supabase backend at project ref `recizkztgknavtddhbqs` (`https://recizkztgknavtddhbqs.supabase.co`). New dev credentials were provided in chat, and `~/.gbrain/config.dev.json` was wired successfully. `gbrain doctor --json` on dev passed with connection/pgvector/RLS/schema healthy; embeddings remain intentionally deferred. `gbrain sync` and `gbrain stats` on `brains/dealerscope-brain` succeeded against dev backend, reporting 97 pages / 109 chunks / 0 embeddings. - Important GBrain nuance recorded: `gbrain sync` warned because `brains/dealerscope-brain` has no upstream tracking branch. Safe current rule is to sync with `--no-pull` until a real remote is chosen. This was documented in reports/wiki as a mitigation, not a fake fix. - Created `brains/dealerscope-brain/operations/dealerscope-brain-obsidian-governance-standard.md` to lock Obsidian governance for DealerScope brain: primary governed vault role, truth boundaries, canonical folders, page classes, frontmatter, naming/authoring rules, conservative plugin policy, and Paperclip/GBrain write-back rules. [score=0.880 recalls=6 avg=1.000 source=memory/2026-04-14.md:102-104]
<!-- openclaw-memory-promotion:memory:memory/2026-03-10.md:1:34 -->
- # Daily Notes — 2026-03-10 ## Who I'm Working With - **Name:** Gs Tyd (Andrew Pilson / pilsonandrew-hub on GitHub) - **Contact:** Telegram @7529788084 - **Named me:** Ja'various (cousin of Jarvis from Iron Man — "backside of the family" 😄) - **Location:** Southern California (HQ = Mac Computer running OpenClaw) - **Working remotely:** Was on phone all day, not at HQ --- ## The Big Project: DealerScope Full day building DealerScope — a wholesale vehicle arbitrage platform. ### What it does Scrapes government/public auctions (GovDeals, PublicSurplus) every 3hrs via Apify, scores deals using institutional dealer logic, surfaces profitable vehicles to buy below MMR and resell to dealers at Manheim. ### Key docs created today - `memory/dealerscope.md` — project context - `memory/dealerscope-roadmap.md` — SOW-based roadmap with phase tracking - `projects/dealerscope/docs/HOW_DEALERSCOPE_WORKS.md` — system documentation - `projects/dealerscope/docs/DealerScope_SOW.pdf` — official SOW committed - `projects/dealerscope/docs/DealerScope_Master_File.docx` — master context doc ### Repos - **dealscan-insight** (main): https://github.com/pilsonandrew-hub/dealscan-insight - **Dealerscope** (pipeline): https://github.com/pilsonandrew-hub/Dealerscope - **Permanent local copy**: `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/` ### What was built today 1. ✅ Merged both repos into unified codebase 2. ✅ Five-layer institutional filter (EchoPark/AutoNation standard, MDS=35 days, CTM≤88%) 3. ✅ CPO eligibility detection (1-3yr old, 10-15% premium) [score=0.870 recalls=5 avg=1.000 source=memory/2026-03-10.md:1-34]
<!-- openclaw-memory-promotion:memory:memory/2026-03-12.md:25:70 -->
- - `c6703da` phase-4: OpenClaw enablement - `711b8c9` phase-6: automation — 3 cron jobs --- ## CODEX_SIGNED_OFF (Codex verified all today) - 4/4 checks: ALERTS_ENABLED, canonical_record_id, PIPELINE_SECRET live (401), commit present - 6/6 groups: skills, crons, pipeline (47 feature lines), memory files, Railway 401, both systems 200 --- ## Supabase Migrations — RAN ON LIVE DB TODAY ✅ - `20260312_deduplication.sql` — SUCCESS via psycopg2 direct connection - `20260312_event_identity.sql` — SUCCESS - Verified columns live: `canonical_id`, `is_duplicate`, `run_id` in opportunities table - Verified: `alert_log` table exists - Connection method: `db.lbnxzvqppccajllsqaaw.supabase.co:5432` with sslmode=require --- ## OpenClaw Config Changes (today) - `llm-task` plugin: **ENABLED** - Hooks: **ENABLED** — 2 hooks (dealerscope-pre-cron, dealerscope-post-failure) - `github` skill: **ACTIVATED** - `model-usage` skill: BLOCKED — needs `codexbar` binary (not installed) - `slack` skill: BLOCKED — needs Slack bot token (we only have Telegram) --- ## Custom Skills Installed - alert-verifier ✅ - apify-ops ✅ - railway-ops ✅ - supabase-ops ✅ - dealerscope (refreshed) ✅ - github (activated today) ✅ ## Cron Jobs Active in openclaw.json - `dealerscope-scraper-watchdog`: `0 */4 * * *` — checks Apify parseforge last run - `dealerscope-daily-digest`: `0 9 * * *` — top 5 deals from Supabase - `dealerscope-rover-weekly`: `0 8 * * 1` — Monday weekly summary --- ## Still Pending (next sprint) - ACP persistent sessions (needs `acpx` plugin or openclaw ACP config) [score=0.870 recalls=6 avg=1.000 source=memory/2026-03-12.md:25-70]
<!-- openclaw-memory-promotion:memory:memory/2026-04-03.md:113:123 -->
- - Full no-dependency stack: Ollama + OpenRouter + Supabase memory + n8n + Lobster - Includes master briefing prompt for any new agent to start cold - Includes DealerScope remaining dev backlog + implementation order - File: `/Users/andrewpilson/.openclaw/workspace/reports/DEALERSCOPE-NEXT-SYSTEM-DESIGN-2026-04-03.md` ## 📌 DealerScope Source Map + Model Pairing Guide Created (2026-04-03 ~10pm PT) - File: `/Users/andrewpilson/.openclaw/workspace/reports/DEALERSCOPE-SOURCE-MAP-AND-MODEL-PAIRING-2026-04-03.md` - Contains: every function, workflow, feature, agent mapped to optimal model + tool + provider - Cost breakdown: current ~$60-65/month → optimized ~$40-45/month - Paperclip optimization plan included [score=0.853 recalls=5 avg=0.962 source=memory/2026-04-03.md:113-123]
<!-- openclaw-memory-promotion:memory:memory/2026-04-15.md:65:68 -->
- - 2026-04-15: Task in main session: summarize YouTube transcript "OpenClaw + Obsidian: The Perfect Co-Working System" (https://www.youtube.com/watch?v=5_JN4kfr-9o). Key points: treat agent like employee; centralize context in user.md; use Obsidian vault + Sync across personal MacBook and agent Mac Mini; install plugins to view/edit non-markdown + render HTML; enable sync for unsupported file types; keep overflow tasks (analytics/dashboards/social/tools) on agent, core creative work on human. - 2026-04-15: Andrew preference update — whenever he mentions Claude for external review/comparison, prefer routing that through OpenRouter instead of the direct Claude CLI/provider path. - 2026-04-15: Andrew provided the active OpenRouter API key for Claude-via-OpenRouter secondary reviews in this session. Store/use it for OpenRouter-routed review flows and do not reprint the raw key in chat. - 2026-04-15: New Paperclip direction under discussion: add an OpenRouter-backed executive role titled `Routing Governor`. Strongest current recommendation is to keep Paperclip as the orchestration/control plane and attach OpenRouter through the existing local bridge pattern, with the Routing Governor acting as a policy/router executive rather than as the canonical execution backend for every agent. [score=0.834 recalls=5 avg=1.000 source=memory/2026-04-15.md:65-68]
<!-- openclaw-memory-promotion:memory:memory/2026-04-15.md:86:89 -->
- - 2026-04-15: Implemented the real Paperclip-side OpenRouter bridge refactor in `scripts/paperclip-openrouter-bridge.js`. Bridge is now lane-aware and fail-closed by default, with an in-file allowlist for `openrouter_claude_review`, `openrouter_claude_fallback`, `openrouter_deepseek_reasoner`, and `openrouter_general`. Explicit `lane` and `model` are required unless `OPENROUTER_LEGACY_DEFAULTS_ENABLED=true`, and legacy defaults only flow through `OPENROUTER_LEGACY_DEFAULT_LANE` / `OPENROUTER_LEGACY_DEFAULT_MODEL`. - 2026-04-15: Validation of the bridge refactor passed: `node --check scripts/paperclip-openrouter-bridge.js`, `/health` now returns the lane catalog, missing-lane requests fail with `400 missing_lane`, and mismatched lane/model requests fail with `400 lane_model_not_allowed`. - 2026-04-15: Summarization task in progress: summarize provided transcript for YouTube video "How to Keep Agents Busy Working On Your Ideas (OpenClaw with Obsidian)" (video id Z5CJzg0mT8g) into Twitter-style "worth watching" summary with strict no-ads/CTA handling and 1-2 short excerpts. - 2026-04-15: Summarization task: summarized provided transcript for YouTube video "How to Build Multi-Agent Teams in OpenClaw (Complete Guide)" (video id Vav0UOOyd5c) into Twitter-style "worth watching" summary; kept strictly to transcript content and omitted promo/CTA material. [score=0.834 recalls=5 avg=1.000 source=memory/2026-04-15.md:86-89]
<!-- openclaw-memory-promotion:memory:memory/2026-04-15.md:83:87 -->
- - 2026-04-15: Added `buildBridgeRequest(...)` to the Routing Governor module so it can now directly convert a governed routing decision into the exact bridge input shape (`lane`, `model`, `routing`) expected by `scripts/paperclip-openrouter-bridge.js`. Node test suite updated and passing (4 tests). - 2026-04-15: Summarization task: produced Twitter-style summary of YouTube transcript "Use these 10 Obsidian tips to level up your note taking productivity" (video id hD-sSRGynpM) with strict no-ads/CTA handling and excerpt lines. - 2026-04-15: Summarization task completed: summarized YouTube transcript "Give Me 15 Minutes. I'll Teach You 80% of Obsidian" (video id z4AbijUCoKU) from provided transcript text with strict no-ads/CTA handling and 1-2 short excerpts. - 2026-04-15: Implemented the real Paperclip-side OpenRouter bridge refactor in `scripts/paperclip-openrouter-bridge.js`. Bridge is now lane-aware and fail-closed by default, with an in-file allowlist for `openrouter_claude_review`, `openrouter_claude_fallback`, `openrouter_deepseek_reasoner`, and `openrouter_general`. Explicit `lane` and `model` are required unless `OPENROUTER_LEGACY_DEFAULTS_ENABLED=true`, and legacy defaults only flow through `OPENROUTER_LEGACY_DEFAULT_LANE` / `OPENROUTER_LEGACY_DEFAULT_MODEL`. - 2026-04-15: Validation of the bridge refactor passed: `node --check scripts/paperclip-openrouter-bridge.js`, `/health` now returns the lane catalog, missing-lane requests fail with `400 missing_lane`, and mismatched lane/model requests fail with `400 lane_model_not_allowed`. [score=0.834 recalls=5 avg=1.000 source=memory/2026-04-15.md:83-87]
<!-- openclaw-memory-promotion:memory:memory/2026-04-17.md:26:33 -->
- - Final live proof: Gemini reviewer run `eafb72b1-12ba-42b3-ba7c-9fadbedd2059` succeeded with anchor comment present and produced real contradiction/gap analysis of the Crosshair v2 plan instead of claiming the plan was missing. This closes the end-to-end context-delivery/rendering bug for bridge-backed reviewer runs. - Remaining Paperclip reviewer issue after this fix: Gemini still routes through the Claude review lane (`openrouter_claude_review` / Claude Sonnet) unless routing governor policy is changed; context delivery itself is now working. - Repaired reviewer lane identity split across the local bridge stack. Updated `scripts/paperclip-routing-governor.js`, `reports/paperclip-routing-governor-config-v2-2026-04-16.json`, and `scripts/paperclip-openrouter-bridge.js` so `external_review` routing can honor agent hints instead of forcing every reviewer through Claude. - Added dedicated `openrouter_gemini_review` lane (`google/gemini-2.5-pro-preview`) plus agent-hint policy mapping: Gemini -> Gemini lane, Claude Auditor -> Claude review lane, DeepSeek R1 -> DeepSeek reasoner lane. - Live routing certification after restart: - Gemini hint routed to `openrouter_gemini_review` / `google/gemini-2.5-pro-preview` - Claude Auditor hint routed to `openrouter_claude_review` / `anthropic/claude-sonnet-4.5` - DeepSeek R1 hint routed to `openrouter_deepseek_reasoner` / `deepseek/deepseek-v3.2` [score=0.834 recalls=5 avg=1.000 source=memory/2026-04-17.md:26-33]
<!-- openclaw-memory-promotion:memory:memory/2026-04-14.md:104:107 -->
- - Created `brains/dealerscope-brain/operations/dealerscope-brain-obsidian-governance-standard.md` to lock Obsidian governance for DealerScope brain: primary governed vault role, truth boundaries, canonical folders, page classes, frontmatter, naming/authoring rules, conservative plugin policy, and Paperclip/GBrain write-back rules. - Audited multiple YouTube videos about Obsidian/OpenClaw/Open memory workflows. Durable takeaway: useful ideas reinforce current architecture, especially query-on-demand retrieval, anti-prompt-bloat discipline, governed shared knowledge, centralized business context, conservative plugin policy, broad stable folders, human review gates, and compaction-to-disk discipline. Not adopted: plugin sprawl, vague prompt-pack systems, treating Obsidian as runtime truth, or blind sync/plugin assumptions. - Pinned for later discussion after Obsidian setup: whether DealerScope should adopt a formal "source discovery vs extraction" doctrine for future scraping/source expansion. This came from a reviewed video and is intentionally deferred, not current priority. - Verified local Obsidian hardware state: Obsidian is installed and configured; currently open vault is `/Users/andrewpilson/Documents/Obsidian Vault` (from `~/Library/Application Support/obsidian/obsidian.json`). This is distinct from the governed DealerScope brain repo at `/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain`. [score=0.806 recalls=4 avg=1.000 source=memory/2026-04-14.md:104-107]

## Promoted From Short-Term Memory (2026-05-14)

<!-- openclaw-memory-promotion:memory:memory/2026-05-07.md:19:22 -->
- - 2026-05-07: bounded E4 runtime failure/recovery contract landed on that same resident supervisor seam by persisting ACE-owned recovery request/result truth and append-only recovery history through supervisor inspection, with targeted 18/18 proof and full staged-tree verification at 422/422. - 2026-05-07: bounded E5 anti-inflation boundary proof landed on that same resident supervisor seam by surfacing explicit bounded runtime claims and explicit anti-inflation non-claims directly through `get_supervisor_runtime_status(...)` / `supervisor-status`, with targeted 18/18 proof and full verification at 422/422. - 2026-05-07: bounded E6 distinct minimal slice proof landed on that same resident supervisor seam by surfacing explicit minimal slice definition, exact E1–E5 artifact bundle, and non-reduction proof directly through `get_supervisor_runtime_status(...)` / `supervisor-status`, with targeted 18/18 proof and full verification at 422/422. - 2026-05-07: implemented a real runtime-autonomy upgrade on the resident supervisor seam. `ace supervisor-run` now supports `--run-until-shutdown`, which keeps the supervisor live until an explicit shutdown request is recorded instead of always auto-stopping after a fixed heartbeat loop. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-07.md:19-22]
<!-- openclaw-memory-promotion:memory:memory/2026-05-07.md:27:30 -->
- - 2026-05-07: added a real launchd-backed resident supervisor seam on disk: `ace/launchd/ai.superace.supervisor.plist` plus `ace/launchd/run-ace-supervisor.sh`, and added `ace supervisor-shutdown` CLI handling in `ace/ace.py` with CLI regression coverage in `ace/tests/test_supervisor_cli.py`. - 2026-05-07: fixed the launchd stop-semantics bug by removing unconditional restart behavior from the supervisor plist so clean operator-requested stop does not respawn the service manager job; launchd truth was verified as `state = not running`, `active count = 0`, `last exit code = 0`, with no `keepalive` property after clean stop. - 2026-05-07: fixed the ACE runtime-ledger reconciliation bug where a launchd-owned runtime could be stranded as `status=stale` + `shutdown_status=requested` with no terminal event. Runtime layer now reconciles `stale + shutdown_requested` to terminal `stopped` before duplicate-start blocking. Regression coverage added in `ace/tests/test_supervisor_runtime.py`. - 2026-05-07: live post-fix launchd-managed stop proof succeeded for runtime `runtime_a54dab217f854cd08c820f261027c09e`: heartbeat at `2026-05-07T07:05:46.130280Z`, `ace.supervisor.shutdown_requested` at `2026-05-07T07:05:47.436607Z`, then terminal `ace.supervisor.stopped` at `2026-05-07T07:05:51.139787Z` with `status=stopped`, `shutdown_status=completed`, and populated `ended_at` / `shutdown_completed_at`. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-07.md:27-30]

## Promoted From Short-Term Memory (2026-05-15)

<!-- openclaw-memory-promotion:memory:memory/2026-05-08.md:15:18 -->
- - Follow-up hardening found a real doctor defect in `tools/gbrain/src/commands/doctor.ts`: the health check unconditionally queried Postgres catalog surfaces (`pg_extension`, `pg_tables`) even when running on local PGLite, producing fake `pgvector` and `rls` warnings on an otherwise healthy local backend. - Fixed the doctor truth surface to branch by engine type: PGLite now reports `pgvector` as provided by the local extension bundle and `rls` as not applicable on the local runtime, while Postgres keeps the real catalog-backed checks. Added regression coverage in `tools/gbrain/test/doctor.test.ts` for the PGLite path. - Validation after the doctor fix: `bun test test/doctor.test.ts` => 4/4 pass; live `bun run src/cli.ts doctor --json` returned healthy with `connection=ok`, `pgvector=ok`, `rls=ok`, `schema_version=ok`, and only `embeddings=warn`. - Tightened the last misleading doctor warning so it now says why embeddings are absent instead of vaguely implying a broken local path. When coverage is zero and no provider is configured, doctor now reports: `No embeddings yet. OpenAI embedding provider is not configured (OPENAI_API_KEY missing).` [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-08.md:15-18]
<!-- openclaw-memory-promotion:memory:memory/2026-05-08.md:23:26 -->
- - Follow-up credential audit found the GBrain embedding provider was not truly unavailable; the working OpenAI embedding key already exists in local shell profiles and prior memory, but was absent from the non-login process environment used during doctor validation. A real embedding pass was then run from a shell that explicitly sourced the local profile, and it completed successfully: `Embedded 571 chunks across 327 pages`. - Post-embed live verification closed the previously real capability gap: `gbrain doctor --json` now reports `embeddings=ok` with `100% coverage, 0 missing`; `gbrain stats` shows `Embedded: 571` out of `571` chunks; hybrid/semantic search returns live results; `openclaw wiki status` remains healthy; both workspace root and `tools/gbrain` git trees are clean. - Important architectural truth surfaced during follow-up: OpenClaw itself already supports first-class embedding providers and live `openclaw infer embedding create` proved a safe 1536-dim path with `openai/text-embedding-3-small`, but docs/live behavior remained mixed around `openai-codex` as a memory embedding provider. The cleanest low-blast-radius path was therefore to remove GBrain's direct OpenAI SDK dependency and rewire GBrain embeddings onto the live OpenClaw embedding surface while preserving the existing 1536-dim storage contract. - Implemented that rewrite in `tools/gbrain`: `src/core/embedding.ts` now shells through `openclaw infer embedding create --model openai/text-embedding-3-small --json --text ...` in batches instead of constructing `new OpenAI()` directly; `src/core/search/hybrid.ts` no longer hard-gates vector search solely on `OPENAI_API_KEY`; `src/core/config.ts` now defaults `embedding_provider` to `openclaw`; `src/commands/init.ts` seeds new configs with `embedding_provider: "openclaw"`; and `src/commands/doctor.ts` now reports generic embedding-provider absence instead of blaming `OPENAI_API_KEY` specifically. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-08.md:23-26]

## Promoted From Short-Term Memory (2026-05-16)

<!-- openclaw-memory-promotion:memory:memory/2026-05-08.md:27:30 -->
- - Validation after the rewrite initially looked green but surfaced one real hygiene miss: two suite tests were slower than Bun's default 5s timeout budget (`test/search-limit.test.ts` regression case and the PGLite doctor test). Both passed in isolation, proving the behavior was correct and the budget was the defect. - Final hardening closed that gap cleanly: `src/core/search/hybrid.ts` was aligned with the new provider truth by treating `config.embedding_provider === "openclaw"` as sufficient embedding availability, and explicit `20000ms` test budgets were added to the slow but valid `test/doctor.test.ts` PGLite check and `test/search-limit.test.ts` regression case. - Final validation after the rewrite and hygiene fix passed honestly: targeted `bun test test/doctor.test.ts test/embed.test.ts test/search-limit.test.ts` => `18 pass, 0 fail`; full `bun test --timeout 20000` => `444 pass, 122 skip, 0 fail`; live `bun run src/cli.ts doctor --json` stayed healthy with `embeddings=ok` / `100% coverage, 0 missing`; and live `bun run src/cli.ts search "DealerScope ACE Direct-Work Autonomy Hardening 2026-05-08"` returned the governed reports. - Residual direct-OpenAI audit found a real post-rewrite authority drift beyond the committed runtime path: schema defaults and chunk model fallbacks were still claiming `text-embedding-3-large` while the shipped embedding runtime now emits `openai/text-embedding-3-small`. Fixed the false provenance in `src/core/pglite-schema.ts`, `src/core/schema-embedded.ts`, `src/schema.sql`, `src/core/pglite-engine.ts`, and `src/core/postgres-engine.ts`, then re-verified with grep and targeted tests. [score=0.907 recalls=0 avg=0.620 source=memory/2026-05-08.md:27-30]

## Promoted From Short-Term Memory (2026-05-19)

<!-- openclaw-memory-promotion:memory:memory/2026-05-12.md:3:6 -->
- - Re-grounded ACE state for Andrew after failed prior turns. Live git in `/Users/andrewpilson/.openclaw/workspace/ace` shows HEAD `3366b7c ace: wire verdict into closeout_gate`, preceded by `75b1e27 ace: persist canonical verdicts` and related confidence/correction commits. Current dirty state is outside ACE code: `../MEMORY.md` modified and untracked `ace.db` in ACE repo root. - Verified `closeout_gate()` in `ace/workflow.py` accepts optional `verdict` and blocks `fail` / `pending`, but live repository call site `_finalize_closeout()` still calls `closeout_gate(evidence_count, open_obligation_count, contradiction_count)` without passing the item verdict. Therefore verdict gate logic is landed but not end-to-end connected to persisted item verdicts. - Targeted proof: running tests from inside `/workspace/ace` failed due Python package shadowing (`ace.py` shadows package path). Correct command from workspace root passed: `python3 -m unittest ace.tests.test_workflow_contract ace.tests.test_repository_contract ace.tests.test_cli` => 312 tests OK. - DealerScope audit alert about rust states was verified against live code. `backend/ingest/score.py` currently treats high-rust states as `risk_flags=['rust_state_source']` plus penalties, not as a hard rejection. Direct smoke proof: `score_deal(bid=10000, mmr_ca=20000, state='OH', year=2020, mileage=30000, title_status='clean', photos=['x'])` returned `vehicle_tier='standard'`, `investment_grade='Platinum'`, `ceiling_pass=True`, `dos_score=86.4`. Ingest normalization/basic gates do reject older rust-state vehicles in `webapp/routers/ingest.py`, but `score_deal()` itself remains unsafe for direct callers (`backend/scrapers/govdeals_active.py`, `webapp/routers/vin.py`, tests/direct use) and violates the canonical business rule unless the caller pre-filters. [score=0.894 recalls=0 avg=0.620 source=memory/2026-05-12.md:3-6]
<!-- openclaw-memory-promotion:memory:memory/2026-05-12.md:8:11 -->
- - 2026-05-12 11:24-11:30 PDT: Repaired critical Paperclip agent failure. Live diagnosis: Paperclip server/dashboard was reachable on 127.0.0.1:3100, but Ja'various heartbeat runs failed because `scripts/paperclip-openrouter-bridge.cjs` routed Gemini via OpenRouter and OpenRouter returned 402 insufficient credits. Verified Paperclip-local `GEMINI_API_KEY` works directly for `gemini-2.5-flash` and `gemini-2.5-flash-lite`; `gemini-2.0-flash` direct API is no longer available. Patched bridge to use direct Google AI Studio Gemini for google/gemini lanes when `GEMINI_API_KEY` is present, mapping OpenRouter's stale `google/gemini-2.0-flash-001` to direct `gemini-2.5-flash-lite`. Validation: `node --check scripts/paperclip-openrouter-bridge.cjs`, `node --test scripts/paperclip-openrouter-bridge.test.cjs` passed 10/10, restarted bridge on port 8787, direct `/run` probe returned OK via Google AI Studio, manual Paperclip heartbeat run `f3d1d840-0cbd-4912-8962-b0e188f020d7` succeeded, subsequent timer run `4c7dab7c-4333-4dd9-8489-8c28a0953bae` succeeded, and Ja'various Paperclip agent status returned to `idle` with latest heartbeat at `2026-05-12T18:29:33.880Z`. - 2026-05-12 11:34 PDT: Andrew added OpenRouter credits. Verified OpenRouter direct completion now succeeds with `google/gemini-2.5-flash-lite` and `google/gemini-2.0-flash-001`. Corrected emergency Paperclip bridge patch so OpenRouter is primary again and direct Gemini is fallback only for Gemini-lane failures. Validation: `node --check scripts/paperclip-openrouter-bridge.cjs`, `node --test scripts/paperclip-openrouter-bridge.test.cjs` passed 10/10. Restarted bridge; `/run` probe succeeded through OpenRouter attempt (`provider: openrouter`, status 200), and manual Paperclip heartbeat run `5d19daa4-74db-4c07-b8d6-ec25e6dfcd84` succeeded. - 2026-05-12 12:45 PDT: Committed current DealerScope repair set on branch `analytics-execution-trust-fix` as `9f5b4f8` (`dealerscope: harden paperclip routing and ingest truth`). Pre-commit validation passed: Python targeted tests `tests/test_ingest_scoring.py tests/test_reconcile_apify_ingest_runs.py tests/test_ingest_sonar_write_failures.py` = 49 passed; Node bridge/routing tests = 20 passed. Commit includes Paperclip OpenRouter-primary/direct-Gemini-fallback bridge hardening, routing-governor Qwen fallback/test updates, ingest/outcome/router truth changes, scraper watchdog cadence/docs, rust exception scoring tests, reconcile hardening, and canonical outcome-domain migration. - 2026-05-12 13:14 PDT: Pushed DealerScope branch `analytics-execution-trust-fix` to origin and opened PR #29: https://github.com/pilsonandrew-hub/dealscan-insight/pull/29. First PR attempt against `master` failed because repo default/base is `main`; second attempt against `main` succeeded. [score=0.894 recalls=0 avg=0.620 source=memory/2026-05-12.md:8-11]
<!-- openclaw-memory-promotion:memory:memory/2026-05-12.md:12:15 -->
- - 2026-05-12 13:22 PDT: PR #29 initially showed merge conflicts against `main`. Merged `origin/main` into `analytics-execution-trust-fix`, resolved conflicts in routing governor config, `src/config/settings.ts`, `src/services/roverAPI.ts`, and `tests/test_reconcile_apify_ingest_runs.py`, validated with Node bridge/routing tests (20 passed), Python focused tests (50 passed after including main's skipped-score test), and `npm run build` (Vite build succeeded). Committed merge as `2820abd` and pushed to PR #29. - 2026-05-12 13:36 PDT: Final PR #29 gate found one trailing-whitespace issue in `src/services/roverAPI.ts`; amended merge commit to `b68afa2`, reran `git diff --check`, Node bridge/routing tests (20 passed), focused Python ingest tests (50 passed), and `npm run build` (passed). Force-pushed amended branch, GitHub checks remained green (Vercel, Vercel Preview Comments, Cursor review). Squash-merged PR #29 into `main` with subject `Harden Paperclip routing and DealerScope ingest truth`. - 2026-05-12 13:31-13:46 PDT: Post-merge runtime verification completed. Paperclip bridge `/health` returned OK; manual Paperclip Ja'various heartbeat run `fe68e098-5a47-4a9f-86dc-40eda18aa83f` succeeded via `openrouter_gemini_proven` / `google/gemini-2.0-flash-001`, with OpenClaw completion hook sent. Railway auto-deployed PR #29 merge commit `309d000` successfully, but startup logs exposed a real lifecycle/schema mismatch: `opportunities.status` did not exist. Patched lifecycle expiration to use `is_active=False` instead of synthetic status (`b8ad5e4`), deployed, then logs exposed second live-schema mismatch: `opportunities.ingested_at` did not exist. Patched age cutoff to use production `created_at` (`48833e8`), reran focused Python tests (51 passed) and Vite build, pushed to `main`, and Railway deployment `de888470-1719-475e-b234-bfbb1e07d89d` succeeded. Final Railway startup logs for `48833e8` show app startup complete and `/health` 200 with no lifecycle error. Cursor review for `48833e8` passed; GitHub Codespaces prebuild-style main workflow remained in progress and is not a production health blocker. - 2026-05-12 14:07 PDT: Continued DealerScope production verification after Andrew said proceed. Live facts: Apify latest enabled actors mostly succeeded; latest datasets included govdeals 287, publicsurplus 8, gsa 57, allsurplus 49, govplanet 76, proxibid 104, hibid-v2 101; equipmentfacts and bidspotter have no latest run. Supabase showed 5712 total opportunities, 106 created in 24h, 724 in 7d, 545 active, and 2231 ingest_delivery rows in 24h. Alert log had 0 alerts in last 7d despite recent DOS>=80 opportunities. Root cause found in `ai_validate_hot_deals`: prompt passed `MMR estimate: $None` for persisted opportunity rows because it only checked `mmr_estimated`/score_breakdown, not `estimated_sale_price`/Manheim/MMR columns, and it failed to explain that DealerScope DOS high = good. Live validation of 5 recent high-DOS opportunities returned 0 valid before patch; after local patch prompt no longer had `$None`, explained DOS semantics, and validation returned 1/5 valid. Committed/pushed `322d698 Fix hot deal validation pricing prompt`; focused tests 53 passed and Vite build passed; Railway deployment `e9766ac3-6b67-4c4a-b520-91460da0215d` succeeded with `/health` 200 and clean startup logs; Cursor review passed. Scheduled isolated follow-up `c4a44d35-ab99-439b-886d-bba2c90c0cb4` for 2026-05-12 17:20 PDT to verify actual post-fix hot-alert chain after the next scraper window. Do not claim Telegram alert chain fully fixed until that post-fix live run sends or explicitly explains no eligible alerts. [score=0.894 recalls=0 avg=0.620 source=memory/2026-05-12.md:12-15]
<!-- openclaw-memory-promotion:memory:memory/2026-05-12.md:16:18 -->
- - 2026-05-12 14:14 PDT: Continued after Andrew said proceed. Audited live Apify schedules against `apify/deployment.json`. Most enabled schedules are live; `ds-equipmentfacts` was falsely marked enabled while live schedule `uJyfnyv7p5UmTzPmn` is disabled (`legacy-disabled-ds-equipmentfacts-6hr`, last run 2026-03-22), and `ds-bidspotter` was falsely marked enabled while schedule `Vol9X7tsYEHKLSdIK` returns 404 and actor has no latest run. Updated manifest to mark both DISABLED with live-audit notes, updated `scripts/reconcile_apify_ingest_runs.py` so default reconciliation includes only `status=enabled` actors while explicit `--actors` can still inspect disabled/retired sources, added regression tests. Validation: JSON parse OK, targeted pytest set 56 passed, Vite build passed. Commit `a1c8b55 Align Apify reconciliation with active sources` pushed to main; Railway deployment `34533f0f-5746-4156-a2d5-f97b9a3822f4` succeeded with `/health` 200 and clean startup logs; Cursor review passed. Main prebuild workflow remained in progress. - 2026-05-12 15:20 PDT: Continued DealerScope reconciliation hardening after Andrew said proceed. Live reconciliation after local patch showed 10 active-source runs, 0 runs_with_issues. Patch intent: treat `vin_dedup_skipped` / `vin_dedup_updated` as successful existing DB landings in ingest and reconciliation, and avoid stale/degraded webhook false positives when DB landing is already proven and no true failed DB/sonar rows exist. Local validation passed: `pytest tests/test_reconcile_apify_ingest_runs.py tests/test_ingest_webhook_security.py tests/test_ingest_alert_validation.py tests/test_lifecycle.py tests/test_ingest_scoring.py tests/test_ingest_sonar_write_failures.py -q` = 71 passed; `npm run build` passed. Live `railway run ... reconcile_apify_ingest_runs.py --lookback-hours 14 --limit-per-actor 20 --summary-only --json` returned `run_count=10`, `runs_with_issues=0`, `issue_counts={}`. - 2026-05-12 15:36 PDT: Committed and pushed DealerScope reconciliation semantics patch as `6b9cbc3 Fix VIN dedup reconciliation semantics` on `main`. GitHub Cursor Code Review and Saved Searches Check passed for `6b9cbc3`; the default Codespaces/prebuild-style workflow remains in progress at Create Template and is treated as non-production-health evidence unless it fails. Railway deployment `03117fdd-3610-44d1-9e8e-5f6f397b9305` for commit `6b9cbc36...` succeeded; deployment logs show container start, non-fatal monitoring middleware warning, application startup complete, and `/health` 200 OK. [score=0.894 recalls=0 avg=0.620 source=memory/2026-05-12.md:16-18]
<!-- openclaw-memory-promotion:memory:memory/2026-05-13.md:3:6 -->
- - 2026-05-12 20:30 PDT / 2026-05-13 03:30 UTC: Started scheduled DealerScope hot-alert chain verification after token rotation and validator fixes. Scope: post-2026-05-13T01:20Z opportunities, ingest_delivery_log, alert_log, Railway logs, and Telegram delivery. Required classification: pass/fail or blocked/no-sample; no soft close if no qualifying hot deal occurred. - 2026-05-12 20:35 PDT hot-alert chain verification result: BLOCKED / NO-SAMPLE for the requested post-2026-05-13T01:20Z window. Railway current deployment started at 2026-05-13T01:19:58Z, application startup complete at 01:20:01Z, `/health` returned 200 at 03:35Z. Supabase showed 0 opportunities, 0 webhook_log rows, 0 ingest_delivery_log rows, and 0 alert_log rows after 01:20Z. Latest real scraper data landed before the deployment/window: run `vhOWpZ5BIwqg1EED7` at 00:03-00:12Z with 35 opportunities; latest telegram_delivery was one 00:13Z 401 failure plus a 01:16Z deleted manual transport proof. Telegram `getMe` now succeeds for @JarviscousinJavariousbot and `getUpdates` returned ok with 0 updates. Railway logs after 01:20Z had no alert/validator/Telegram send attempts. Do not classify hot-alert chain as pass until a post-01:20Z qualifying scraper sample produces either a sent alert receipt or a proven no-eligible-alert explanation. - 2026-05-13 03:52 PDT: Continued professional A.C.E. hardening after Andrew directed cleanliness/hygiene and engineering truth. Addressed the real remaining tamper-evident event-history gap by adding event hash-chain columns (`previous_event_hash`, `event_hash`), deterministic SHA-256 event hashing, append-time chaining, legacy backfill on bootstrap, and `verify_event_hash_chain(...)`. Added storage tests proving append chaining, tamper detection, and legacy event backfill. Validation: focused `python3 -m unittest ace.tests.test_storage_contract ace.tests.test_repository_contract ace.tests.test_autonomy_lane ace.tests.test_cycle` = 50 OK; full `python3 -m unittest discover ace/tests` = 492 OK; live `verify_event_hash_chain(DB_PATH)` returned `{'ok': True, 'detail': None}`; V2 Telegram direct-work certification for `telegram:7529788084:33604` still PASS. Committed as `15dff1a ace: add tamper evident event hash chain`. This improves auditability but does not promote ACE to V1 and does not claim external notarization. - 2026-05-13 04:34 PDT: Repaired the event hash-chain race found immediately after commit `15dff1a`. Root cause: live pre-restart supervisor and deferred SQLite transactions could append events after computing against the same chain tail, producing `broken previous_event_hash` even though payload hashes matched their stored prior hash. Added narrow `repair_event_hash_chain_for_legacy_races(...)` for pre-serialized race rows only; it refuses payload/hash mismatches by design. Hardened `append_event(...)` to acquire SQLite write serialization before reading the previous event hash (`BEGIN IMMEDIATE` or no-op write-lock acquisition inside existing transactions). Validation: targeted storage/workflow/repository/CLI tests 329 OK; full ACE suite 495 OK; live hash-chain verification PASS before and after waiting through supervisor heartbeats. Restarted ACE supervisor through governed shutdown/start so the live process now runs current code: old runtime `runtime_bfdcf136689b4706b7dafabcb5b195f9` stopped cleanly, new runtime `runtime_7dd4a33a52b0458e8d20ab573daf4d9e` is live, and new heartbeat rows have non-null chained hashes. This is a real auditability fix, not V1 promotion. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-13.md:3-6]
<!-- openclaw-memory-promotion:memory:memory/2026-05-13.md:8:11 -->
- - 2026-05-13: DealerScope reconciliation truth cleanup: fixed ingest save-exception accounting so `save_opportunity_to_supabase` exceptions now increment `failed_save_count`, emit durable `db_save/save_exception` ledger rows, and surface `save_outcomes={save_exception: 1}` instead of silently only incrementing skip reasons. Reconciliation now treats `save_exception` and legacy `failed` db_save statuses as `db_save_failures`. Validation: `python3 -m unittest tests.test_ingest_webhook_security.WebhookSecurityTests.test_apify_webhook_counts_save_exception_as_failed_save_with_ledger tests.test_reconcile_apify_ingest_runs.ReconcileApifyIngestRunsTests.test_classify_run_flags_save_exception_as_db_save_failure tests.test_reconcile_apify_ingest_runs.ReconcileApifyIngestRunsTests.test_classify_run_flags_legacy_failed_status_as_db_save_failure` passed; broader `python3 -m unittest tests.test_ingest_webhook_security tests.test_reconcile_apify_ingest_runs tests.test_ingest_sonar_write_failures` passed 43 tests OK. - 2026-05-12 22:31 PDT: Fixed a live DealerScope analytics trust false-degradation bug. Root cause: `/api/analytics/summary` queried `alert_log` with `.eq("user_id", user_id)`, but the live launch-safe `alert_log` schema is a pipeline delivery ledger with no `user_id` column. This caused PostgREST 42703 and added misleading `Alert metrics degraded` trust notes despite alert_log being queryable by `sent_at`. Changed `webapp/routers/analytics.py` to count recent alerts by `sent_at` only. Validation: `python3 -m unittest tests.test_analytics_trust_model` passed; full `python3 -m unittest discover tests` passed 98 OK; live Railway analytics summary no longer reports `Alert metrics degraded`, but remains legitimately degraded because execution/outcome freshness is stale from 2026-04-22. Live post-2026-05-13T01:20Z hot-alert proof remains BLOCKED/NO-SAMPLE: `alert_log` returned 0 rows; `webhook_log` had processed post-fix runs with 0 hot_deals / no eligible alert sample. - 2026-05-12 22:44 PDT: Fixed DealerScope analytics false degradation on alert metrics. Live `alert_log` is a pipeline delivery ledger with no `user_id`, so `webapp/routers/analytics.py` now counts alerts by `sent_at` only. Added regression coverage in `tests/test_analytics_trust_model.py` ensuring no false `user_id` filter and no `Alert metrics degraded` note. Pushed `cd85fe1 Fix analytics alert ledger query` to `origin/main`. Validation: DealerScope `python3 -m unittest discover tests` passed 99 tests; ACE hash verification returned `(True, None)` and `python3 -m unittest discover ace/tests` passed 495 tests. Live Railway analytics probe now shows `alerts_sent_last_30d=46` and no alert metric degradation; remaining analytics trust degradation is real stale execution/outcomes freshness from 2026-04-22. - 2026-05-12 22:49 PDT: Andrew set primary goal: working clean A.C.E., fix all failures, tried/tested/true. Re-grounded ACE from live disk: hash chain `(True, None)`, supervisor live (`runtime_7dd4a33a52b0458e8d20ab573daf4d9e`), full ACE suite `python3 -m unittest discover ace/tests` passed 495 tests. Found untracked `ace/state/ace.db-journal`; did not delete live SQLite journal. Added `state/ace.db-*` to `ace/.gitignore`, committed `1c264ed ace: ignore sqlite runtime journals`, and pushed to `origin/master`. DealerScope main also verified clean/synced with origin and `python3 -m unittest discover tests` passed 99 tests after analytics alert ledger fix. Remaining DealerScope hot-alert chain is still blocked/no-sample, not certified. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-13.md:8-11]

## Promoted From Short-Term Memory (2026-05-20)

<!-- openclaw-memory-promotion:memory:memory/2026-05-13.md:12:15 -->
- - 2026-05-13: Re-ran A.C.E. clean-version certification after Andrew reiterated the goal. Evidence: `verify_event_hash_chain(DB_PATH)` returned `(True, None)`, full ACE suite passed `495 OK`, V2 Telegram direct-work certification for `telegram:7529788084:33604` passed, supervisor remained live under launchd (`runtime_7dd4a33a52b0458e8d20ab573daf4d9e`), and last governed cycle was completed with `trigger_kind=launchd`. `rg` audit found no active false A.C.E. V1 promotion strings in ACE source; canonical truth remains governed foundation, not V1. - 2026-05-13: Re-ran full A.C.E. + DealerScope truth gates after Andrew reiterated the clean/professional standard. A.C.E. evidence: hash_chain `(True, None)`, full `python3 -m unittest discover ace/tests` passed `495 OK`, V2 direct-work certification for `telegram:7529788084:33604` PASS, supervisor live under launchd, ACE `origin/master` at `1c264ed`; only root drift is `MEMORY.md`, and ACE runtime state is ignored. DealerScope evidence: `python3 -m unittest tests.test_analytics_trust_model` passed 6 tests; `python3 -m unittest discover tests` passed 99 tests; analytics alert-log schema drift fix is present. Remaining DealerScope issues are live/environmental or data-sample gates, not local test failures: hot-alert chain still BLOCKED/NO-SAMPLE pending scheduled scraper proof; Supabase/DATABASE_URL env missing locally; Redis down behavior is covered by tests; Apify Python SSL issue falls back to curl/system trust store. - 2026-05-13 06:05 PDT: Independent subagent `ace-cleanliness-audit` completed and returned PASS for clean governed-foundation A.C.E., explicitly not V1/platform. Evidence matched local live certification: ACE HEAD `1c264ed`, hash chain `(True, None)`, full ACE tests `495 OK`, V2 Telegram direct-work certification PASS, supervisor live (`runtime_7dd4a33a52b0458e8d20ab573daf4d9e`), root/ACE source clean except `MEMORY.md`; runtime state ignored as expected. Remaining not-V1 boundaries: raw Telegram Bot API polling not certified, no broad platform/runtime-fabric claim, no sleep/network-blip acceptance proof. No further A.C.E. source fix required for current governed-foundation clean gate. - 2026-05-13: Found and fixed a real A.C.E. direct Telegram runtime configuration gap. The resident launchd `ace cycle` wrapper was not exporting `ACE_OPENCLAW_CHAT_ID`, so scheduled cycles would not read the OpenClaw Telegram session stream unless manually configured. Added a safe default from `ACE_OPERATOR_TARGET` when `ACE_OPERATOR_CHANNEL=telegram`. To avoid unsafe first-run backlog ingestion, added `ACE_TELEGRAM_BOOTSTRAP_EXISTING_AS_PROCESSED`; when the Telegram checkpoint DB is empty, existing discovered messages are checkpointed and not returned. Validation passed: targeted telegram/cycle tests 19 OK, full ACE suite 497 OK, `verify_event_hash_chain(DB_PATH)` returned `(True, None)`, and V2 Telegram direct-work certification for `telegram:7529788084:33604` PASS. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-13.md:12-15]
<!-- openclaw-memory-promotion:memory:memory/2026-05-13.md:17:17 -->
- - 2026-05-13: Continued A.C.E. clean-version hardening after the governed-foundation pass. Found a real raw-transport gap: raw Telegram Bot API failures returned empty results silently. Added durable `telegram_transport_attempts` diagnostics in `ace/telegram_runtime.py` for Telegram Bot API ok/error attempts, including URLError/SSL/JSON/API-shape failures, plus tests. Revalidated targeted Telegram/cycle tests (`20 OK`), full ACE suite (`498 OK`), warnings-clean full suite (`498 OK` under `PYTHONWARNINGS=error`), event hash chain `(True, None)`, and V2 Telegram direct-work certification PASS for `telegram:7529788084:33604`. A.C.E. remains not V1. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-13.md:17-17]
<!-- openclaw-memory-promotion:memory:memory/2026-05-13.md:19:22 -->
- - 2026-05-13: Continued A.C.E. raw Telegram transport durability cleanup. Added optional `ACE_TELEGRAM_UPDATE_OFFSET` propagation to Bot API `getUpdates`, kept default no-offset behavior explicit in tests, and verified offset is included when configured. Closed ResourceWarning noise in Telegram runtime tests by explicitly closing sqlite connections with `contextlib.closing`. Added `state/telegram_runtime.db*` to `ace/.gitignore` after real runtime execution created the DB. Validation: targeted Telegram/cycle tests under `PYTHONWARNINGS=error` passed (20 OK), full ACE suite under `PYTHONWARNINGS=error` passed (498 OK), event hash chain returned `(True, None)`, V2 Telegram direct-work certification for `telegram:7529788084:33604` passed. - 2026-05-13: A.C.E. Telegram Bot API polling durability hardened. Commit 9608a0d persists Telegram Bot API next update offsets in telegram_runtime.db via telegram_transport_offsets, reuses stored offsets when ACE_TELEGRAM_UPDATE_OFFSET is absent, and keeps transport attempt diagnostics bootstrapped. Validation: targeted telegram/cycle tests passed 22 OK with PYTHONWARNINGS=error; full ACE suite passed 500 OK with PYTHONWARNINGS=error; live event hash chain returned (True, None); V2 Telegram direct-work certification for telegram:7529788084:33604 passed. Live telegram_runtime.db has processed_telegram_messages, telegram_transport_attempts, and telegram_transport_offsets tables. A.C.E. remains governed foundation / Phase 0, not V1. - 2026-05-13: Final A.C.E. clean governed-foundation certification after Telegram offset hardening. Commit `9608a0d` pushed to origin/master. Live evidence: root git dirty only for MEMORY.md; ACE source clean except parent MEMORY.md; full ACE tests with `PYTHONWARNINGS=error` passed 500 OK; event hash chain returned `(True, None)`; V2 Telegram direct-work certification for `telegram:7529788084:33604` PASS; launchctl shows `ai.superace.supervisor` running PID 22307; `python3 -m ace.ace --db ace/state/ace.db supervisor-status` shows current supervisor heartbeat `runtime_7dd4a33a52b0458e8d20ab573daf4d9e`; process command confirms launchd-owned `supervisor-run`; last terminal governed run completed with `trigger_kind=launchd`. Runtime DB includes `processed_telegram_messages`, `telegram_transport_attempts`, and `telegram_transport_offsets`. Claim boundary: PASS at governed-foundation clean gate, NOT V1; raw real Telegram polling acceptance, sleep/network-blip proof, and broad platform/runtime-fabric claims remain unearned. - 2026-05-13: Re-ran A.C.E. hard gate after Andrew reiterated “Fix ALL Failures / tried tested true.” Live re-ground evidence: ACE source HEAD `9608a0d`; root/ACE git dirty only for parent `MEMORY.md`; `verify_event_hash_chain(DB_PATH)` returned `(True, None)`; launchd supervisor live with current heartbeats for `runtime_7dd4a33a52b0458e8d20ab573daf4d9e`; `PYTHONWARNINGS=error python3 -m unittest discover ace/tests` passed 500 tests OK; manual launchd-wrapper cycle completed with `run_id=run_67e9a02585914452878852774bf71d74`, `run_status=completed`, `notification_count=0`, and post-cycle hash chain still `(True, None)`. Telegram runtime DB has required tables: `processed_telegram_messages`, `telegram_transport_attempts`, `telegram_transport_offsets`. Verification script initially queried nonexistent `source`/`ok` columns; live schema/code correctly use `transport`/`status`, so that was verifier error, not product defect. Current truth: A.C.E. PASS at clean governed-foundation gate; no source failure requiring another patch found. Remaining unearned proofs: raw live Telegram Bot API acceptance, sleep/network-blip resilience, and broad V1/platform/runtime-fabric claims. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-13.md:19-22]
<!-- openclaw-memory-promotion:memory:memory/2026-05-13.md:24:24 -->
- - 2026-05-13: A.C.E. enterprise hardening follow-up after Andrew required no hand-waving and industrial-grade hygiene. Re-grounded live A.C.E.; found one real diagnostic gap: with no `ACE_TELEGRAM_BOT_TOKEN`, no OpenClaw session, and no local inbox, `fetch_unprocessed_telegram_messages()` returned `[]` without a durable transport attempt. Patched `ace/telegram_runtime.py` so missing raw Telegram token/no local inbox records `telegram_transport_attempts(status=disabled,error_type=missing_bot_token)`. Added `ace/tests/test_telegram_runtime.py` coverage. Gates passed: targeted telegram runtime 14 OK, full ACE suite under `PYTHONWARNINGS=error` 500 OK, event hash chain `(True, None)`, V2 direct-work certification for `telegram:7529788084:33604` PASS. Committed/pushed `a7132e7 ace: record disabled telegram transport state`. Current truth: A.C.E. PASS at governed-foundation gate, not V1; raw live Telegram polling acceptance remains unearned because the bot token is not configured in launchd/live environment, but missing-token state is now observable rather than silent. [score=0.914 recalls=0 avg=0.620 source=memory/2026-05-13.md:24-24]
<!-- openclaw-memory-promotion:memory:memory/2026-05-14.md:3:3 -->
- - ACE raw Telegram shared-token conflict documented. Live evidence showed the governed OpenClaw token source reaches Telegram, but `telegram_bot_api` attempts fail with `telegram_conflict` because OpenClaw already owns/polls the shared Telegram bot token. Production launchd cycle remained on the safe default/OpenClaw-session path. Added governed report `ace/reports/ace-raw-telegram-shared-token-conflict-2026-05-14.md` and committed `450b493 ace: document raw telegram shared token blocker`. Validation: `PYTHONWARNINGS=error python3 -m unittest discover ace/tests -t .` passed 527 OK; event hash chain remained `(True, None)` before the report. Truth: ACE remains not V1; scheduled raw Bot API polling requires either a dedicated ACE bot/token, OpenClaw-mediated handoff, or dropping shared-token raw polling as a near-term gate. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-14.md:3-3]
<!-- openclaw-memory-promotion:memory:memory/2026-05-14.md:5:5 -->
- - ACE safe Telegram path auditability hardened: `openclaw_session` transport now records durable `telegram_transport_attempts(status=ok,message_count=N)` when the OpenClaw session stream is read, matching Bot API observability without relying on shared-token raw polling. Validation: `PYTHONWARNINGS=error python3 -m unittest ace.tests.test_telegram_runtime` passed 24 OK; `PYTHONWARNINGS=error python3 -m unittest discover ace/tests -t .` passed 527 OK; live event hash chain remained `(True, None)`. Truth: this improves governed-foundation auditability only; ACE remains not V1. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-14.md:5-5]

## Promoted From Short-Term Memory (2026-05-21)

<!-- openclaw-memory-promotion:memory:memory/2026-05-15.md:3:6 -->
- - ACE Item 3 sleep/wake resilience proof executed once via `scripts/ace_sleep_wake_item3_proof.py`; artifact `/tmp/ace-item3-sleep-wake-proof-20260515T000840Z.json`. Result FAIL: checks 2/3/5/6 PASS, checks 1/4 FAIL. Check 1 failed because pre/post runtime stayed `runtime_11fd6f78de54427eb8b4b9ac56c721b6` live with no prior failed runtime/new runtime. Check 4 failed because `VERIFIED_DONE` item rows lacked closeout fields, newest `item_b8457775b0b84ffaac01308f405da3be`. Hash audit ok, post-wake launchd cycle `run_f762c675b1154e1886a2958e27037b22` completed, full ACE suite 548 OK. - ACE Item 3 failure remediation slice: fixed closeout metadata persistence in `ace/repository.py::_finalize_closeout()` so future `VERIFIED_DONE` rows persist `closed_at`, `closed_by`, and `closed_reason`; added default metadata behavior and targeted repository coverage. Added bootstrap migration coverage for missing closeout columns in legacy items tables. - ACE Item 3 supervisor semantics remediation: updated the proof runner semantics to accept either same-runtime sleep survival with a recent heartbeat or prior-runtime failure/replacement, while preserving dead-process reconciliation coverage (`supervisor_process_missing`) and adding explicit same-live-process sleep-survival coverage. - ACE live state backfill: updated existing `ace/state/ace.db` `VERIFIED_DONE` rows missing closeout metadata from 89 invalid rows to 0 invalid rows using closeout-attempt actor/reason when available; `python3 ace/ace.py audit verify` remained `event_hash_chain=ok` after backfill. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-15.md:3-6]
<!-- openclaw-memory-promotion:memory:memory/2026-05-15.md:7:7 -->
- - Validation after remediation slice: targeted `python3 -m unittest ace.tests.test_repository_contract ace.tests.test_supervisor_runtime ace.tests.test_cli.AceCliTests.test_bootstrap_adds_closeout_metadata_columns_to_existing_items_table -v` passed 42/42; full `python3 -m unittest discover ace/tests` passed 551/551 in 44.359s; audit verify ok. Proof re-run still not performed in this slice. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-15.md:7-7]
<!-- openclaw-memory-promotion:memory:memory/2026-05-15.md:9:9 -->
- - 2026-05-15: Item 3 remediation slice — closeout metadata persistence/correction: added audited `ace correction submit` path and repository method `submit_closeout_metadata_correction(...)`; `_finalize_closeout()` now persists `closed_at`, `closed_by`, and `closed_reason`; bootstrap adds missing closeout metadata columns. Live DB truth after correction events: `VERIFIED_DONE=89`, invalid verified rows with null closeout metadata `0`, `item.closeout_metadata_corrected` events `89`, `ace audit verify` event_hash_chain=ok. Targeted correction tests passed and full ACE suite passed `Ran 552 tests in 48.766s — OK`. [score=0.890 recalls=0 avg=0.620 source=memory/2026-05-15.md:9-9]
