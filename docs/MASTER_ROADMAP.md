# DealerScope + OpenClaw Master Upgrade Roadmap
**Co-signed by: Ja'various + Codex (gpt-5.4)**
**Date: 2026-03-11**
**Status: APPROVED**

---

## Guiding Principle
> OpenClaw is an accelerator for a stable DealerScope system — not the mechanism that makes the system stable. Fix the foundation first, then amplify.

---

## PHASE 0 — Control Plane Lockdown
**Timeline: Immediate (Days 1-2)**
**Owner: Codex leads, Ja'various verifies**

The foundation every other phase depends on. Nothing else is reliable until this is done.

- [ ] Remove all hardcoded secret defaults from source (Telegram token, webhook secret in actors)
- [ ] Standardize ONE ingest contract: all actors → Apify dataset webhook only → Railway (deprecate direct POST path)
- [ ] Fix 5 actors still posting direct payload (`ds-bidcal`, `ds-auctiontime`, `ds-municibid`, `ds-gsaauctions`, `ds-hibid`) — migrate to dataset webhook pattern
- [ ] Choose ONE alert control plane: FastAPI Telegram OR OpenClaw messaging (not both)
- [ ] Require explicit env var validation at startup — crash if missing, no silent fallbacks
- [ ] Fix dedup to be transactional (INSERT ... ON CONFLICT instead of read-then-write)
- [ ] Clean health endpoint — remove router metadata from public response
- [ ] Add exec sandbox policy to `openclaw.json`

**Exit criteria:** Every ingest call uses the same contract. No hardcoded secrets in source. Startup fails loudly if env is missing.

---

## PHASE 1 — Event Identity + Observability
**Timeline: Days 3-5**
**Owner: Codex leads, Ja'various verifies**

Without run IDs and message IDs, everything downstream is guesswork.

- [ ] Add `run_id` to every ingest request (Apify run ID passed through webhook)
- [ ] Add `source_run_id`, `step`, `status`, `processed_at` to opportunities table
- [ ] Add `alert_id`, `message_id`, `sent_at`, `delivery_state` to Supabase alert ledger (new table: `alert_log`)
- [ ] Add idempotency key to webhook endpoint — reject duplicate run_ids
- [ ] Log each pipeline step: received → normalized → scored → saved → alerted
- [ ] Run the dedup migration against live Supabase DB

**Exit criteria:** Every alert traceable back to one pipeline run and one source record. No duplicate processing.

---

## PHASE 2 — Alert Reliability
**Timeline: Days 5-8**
**Owner: Codex leads, Claude Code supports**

- [ ] Build `alert-verifier` custom skill (after alert_log table exists)
- [ ] Route all Telegram alerts through ONE control plane (decided in Phase 0)
- [ ] Verify Telegram delivery by reading message ID back from API response
- [ ] Store message_id in `alert_log` table
- [ ] Add alert suppression policy: max 1 alert per vehicle per 6hrs
- [ ] Add alert kill switch: env var `ALERTS_ENABLED=false` stops all outbound
- [ ] Add Buy / Watch / Ignore Telegram reaction buttons (only after ledger maps callback → alert_id → opportunity_id)
- [ ] Alert cost guardrail: max N alerts per scrape run

**Exit criteria:** Every hot deal alert has a receipt. Duplicate alerts impossible. Can silence all alerts with one env var.

---

## PHASE 3 — Scraper Triage (By Business Value)
**Timeline: Week 2**
**Owner: Codex + OpenClaw browser for SPA sites**

Fix scrapers in order of inventory coverage value, not convenience:

1. **GovDeals** — Highest volume. Use OpenClaw browser + token capture approach (REVERSE_ENGINEER.md)
2. **GSAauctions** — Federal fleet. React SPA. Browser recon needed.
3. **PublicSurplus** — Just needs rebuild trigger + contract fix
4. **Municibid** — Selector validation against live site
5. **AllSurplus** — Remove direct POST, fix selectors
6. **AuctionTime** — Selector validation
7. **BidCal** — Selector validation
8. **HiBid** — Was running, 0 items — selector investigation

**Per-scraper acceptance checklist:**
- [ ] Extraction accuracy (real vehicle data, not site chrome)
- [ ] Delivery contract compliance (dataset webhook only)
- [ ] Dedup behavior (canonical_id correctly generated)
- [ ] Alert behavior (hot deals fire exactly once)
- [ ] Runtime cost within Apify free plan memory envelope

**Cancel parseforge** only after GovDeals replacement passes 5+ consecutive live runs.

---

## PHASE 4 — OpenClaw Enablement
**Timeline: Week 2-3**
**Owner: Ja'various configures, Codex validates**

Now that the system is stable, OpenClaw becomes the amplifier.

### Skills
- [ ] Refresh stale `dealerscope` skill (fix /tmp path, update commands, reflect current repo)
- [ ] Install `github` skill — CI/deploy visibility, issue triage
- [ ] Install `slack` skill — alert delivery foundation, reactions
- [ ] Formalize memory structure:
  - `MEMORY.md` — durable long-term (already exists, needs curation)
  - `memory/dealerscope-incidents.md` — active scraper/pipeline failures
  - `memory/dealerscope-decisions.md` — irreversible architectural decisions
  - `memory/dealerscope-handoffs.md` — latest work state for Codex warm-start

### OpenClaw Config
- [ ] Add exec sandbox policy to `openclaw.json`
- [ ] Enable `llm-task` plugin for structured auction title/VIN parsing
- [ ] Configure Perplexity for market research queries (already have key)

### Warm-Start (Selective, Not Default)
- [ ] Build `dealerscope-bootstrap` script: loads architecture + last 10 changes + active blockers
- [ ] Use before major implementation sessions, not every small task

**Cut entirely from this phase:** Canvas skill, Oracle skill, post-commit memory hooks — add overhead before they add value.

---

## PHASE 5 — Advanced Scraper Ops
**Timeline: Week 3**
**Owner: Codex + Ja'various browser tooling**

Only after scraper failure modes are measured can we apply specialized tools.

- [ ] Set up OpenClaw browser profile for GovDeals (`openclaw browser start --browser-profile govdeals`)
- [ ] Use `requests`, `responsebody`, `trace`, `cookies`, `storage` to capture real maestro.lqdt1.com API contract
- [ ] Persistent ACP session `agent:scrape-govdeals` — accumulates recon findings across runs
- [ ] Same approach for GSAauctions if needed after Phase 3 investigation
- [ ] Configure Firecrawl ONLY if a specific source proves it reduces failure rate

---

## PHASE 6 — Automation + Intelligence
**Timeline: Week 3-4**
**Owner: Codex builds, Ja'various operates**

Force multipliers — only valuable on a working foundation.

### Cron Jobs
- [ ] Stale scraper detection: if no successful run in 4hrs → Telegram alert to Andrew
- [ ] Daily deal digest: 9am PT — top 5 deals from last 24hrs, sorted by DOS score
- [ ] Weekly Rover summary: top makes/models/states from saved deals this week

### Lifecycle Hooks
- [ ] Pre-cron hook: check Railway health + Apify token + Telegram channel before any scheduled job
- [ ] Post-failure hook: snapshot logs + error context to `dealerscope-incidents.md`

### Skills to Build
- [ ] `apify-ops` — actor health, run history, re-trigger, dataset inspection
- [ ] `railway-ops` — deploy status, log tailing, env diff, restart
- [ ] `supabase-ops` — safe table queries, RLS audit, migration status

### Multi-Agent Model (After Run Ownership Proven)
- [ ] `agent:pipeline-supervisor` — monitors run_ids, escalates failures
- [ ] `agent:alert-auditor` — verifies delivery receipts
- Consider `agent:memory-curator` for daily memory maintenance

---

## DEFERRED (Not This Month)
- Canvas visual dashboard
- TTS / voice alerts
- Node management (multi-device)
- ACP persistent Codex sessions (evaluate after Phase 4 warm-start proves value)
- Multi-tenant / SaaS features
- Automated bidding

---

## Decision Log
| Decision | Rationale | Agreed By |
|---|---|---|
| Codex reordered Phase 0 before OpenClaw | Foundation before amplification | Ja'various + Codex |
| One ingest contract (dataset webhook only) | Mixed contracts = broken delivery | Codex |
| Alert routing: one control plane | Two paths = silent failures | Both |
| Scraper order by business value | GovDeals > PublicSurplus for coverage | Codex |
| Canvas deferred | Not justified by current roadmap | Codex |
| Oracle deferred | Meta tool, not directly on revenue path | Codex |

---

## What We're Building Toward
A system where:
1. Every scrape run has an ID and a traceable outcome
2. Every hot deal alert has a receipt and can be acknowledged with one tap
3. Every OpenClaw session starts with accurate context, not repo archaeology
4. Codex knows the codebase before the first line of code
5. Scraper failures are caught automatically, not discovered by Andrew checking Notion

**Revenue path:** Scraper fires → vehicle scored → alert sent → Andrew sees it → bids → wins → profit.
Every phase in this roadmap removes one way that chain can silently fail.
