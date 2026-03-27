# DealerScope Service Integration Audit
Last updated: 2026-03-27

## Summary: What's Wired vs What's Missing

---

### 1. OpenRouter ✅ Wired / ⚠️ Key Not Set in Railway

**Status:** Code reads `OPENROUTER_API_KEY` from env (ingest.py line 95). Used for AI validation of hot deals.

**What's working:** LLM fallback chain (Claude → GPT → Gemini → DeepSeek)
**What's missing:** `OPENROUTER_API_KEY` not confirmed set in Railway env vars
**Untapped potential:**
- Multi-model deal scoring comparison
- "Why hot" deal rationale generation per alert
- Condition description NLP parsing from listing text

**Action:** Set `OPENROUTER_API_KEY=sk-or-v1-0e46f077...` in Railway dashboard

---

### 2. Notion ✅ Wired / ⚠️ Env Vars Not Set

**Status:** `sync_to_notion()` is fully built in ingest.py. Triggers on every DOS≥50 deal insert.

**What's working:** Code is complete, deduplication logic exists
**What's missing:** `NOTION_TOKEN` and `NOTION_DEALS_DB_ID` not set in Railway
**Untapped potential:**
- PSR drop zone (NOW BUILT: database ID `8281ab65-987e-4090-80b6-707633a9ba1a`)
- Deal review workflow in Notion (comment, tag, status update)
- Weekly digest page auto-generated from top deals

**Action:** Set in Railway:
```
NOTION_TOKEN=[NOTION_TOKEN_REDACTED]
NOTION_DEALS_DB_ID=32034c00de4c80fdae18eb02848a9f39
```

---

### 3. Slack ✅ Wired / ✅ Likely Working

**Status:** Slack bot token + channel ID are in ingest.py. Channel `C0ALM52FV25` = Dealerscope workspace.

**What's working:** Alert notifications wired
**Untapped potential:**
- Slash commands (`/deals`, `/status`, `/scraper-health`)
- Scraper run summaries posted to Slack automatically
- Deal inbox digest at 7am PT daily

**Action:** Confirm `SLACK_BOT_TOKEN` is set in Railway env

---

### 4. Cursor ✅ Fully Working

**Status:** Two GitHub Actions workflows running:
- `cursor-review.yml` — runs on every PR, reviews diff for security/business rule violations
- `cursor-audit-12hr.yml` — runs every 12hrs, full Gemini red team + Cursor review

**What's working:** Both workflows confirmed passing
**Untapped potential:**
- Auto-fix suggestions on failed CI (not just review)
- Cursor review on scraper output anomalies

---

### 5. Firecrawl ✅ Key Valid / ✅ Module Built

**Status:** `firecrawl_fallback.py` just created. Key `fc-51b150a3...` confirmed valid.

**What's working:** Module ready for use
**What's missing:** `FIRECRAWL_API_KEY` not set in Railway (manual step needed)
**Untapped potential:**
- Auto-fallback when Apify actor returns 0 results
- Manheim spec page fetching (Cloudflare-blocked)
- One-off listing enrichment for detail pages

**Action:** Set `FIRECRAWL_API_KEY=[FIRECRAWL_KEY_REDACTED]` in Railway dashboard

---

## Railway Env Vars to Set Manually

Go to: railway.app → dealscan-insight → Variables

| Variable | Value |
|----------|-------|
| OPENROUTER_API_KEY | [OPENROUTER_KEY_REDACTED] |
| NOTION_TOKEN | [NOTION_TOKEN_REDACTED] |
| NOTION_DEALS_DB_ID | 32034c00de4c80fdae18eb02848a9f39 |
| FIRECRAWL_API_KEY | [FIRECRAWL_KEY_REDACTED] |
| SLACK_BOT_TOKEN | [SLACK_TOKEN_REDACTED] |

---

## Manheim PSR Drop Zone
- Notion database created: https://www.notion.so/8281ab65987e409080b6707633a9ba1a
- Fields: Report Name, Sale Date, VIN, Year, Make, Model, MMR, Sale Price, Condition Grade, Lane, Location, Buyer Premium, All-In Cost, Gross Margin, Notes, Status
- Drop PSR data manually or we can build a PDF parser script to auto-populate
