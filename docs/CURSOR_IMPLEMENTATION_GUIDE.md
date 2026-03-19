# DealerScope × Cursor — Master Implementation Guide
Created: 2026-03-19 | Owner: Andrew Pilson

---

## WHAT THIS IS

This document is the complete blueprint for integrating Cursor into DealerScope as a
**Protocol OS + Repo Intelligence + Engineering Manager + PR Quality Gate.**

Cursor is NOT a code editor for you. You don't code.
Cursor is your **visual command center** between strategy and deployment.

---

## THE STACK — HOW EVERY TOOL FITS

| Tool | Role | Used How |
|------|------|----------|
| **Claude (this chat)** | Architecture, strategy, deep analysis | Design features, audit system |
| **Ja'various (OpenClaw/Telegram)** | Operations, monitoring, deal alerts | From your phone, always on |
| **Claude Code (terminal)** | Quick edits, git, one-off commands | Background, via Ja'various |
| **Codex (OpenAI API)** | Implementation, coding tasks | Background, via Ja'various |
| **Cursor (IDE)** | Visual command center, multi-file changes, MCP | At your Mac |

**The flow:**
Claude designs → Cursor applies across files → You review visually → Claude Code handles git → Ja'various operates live

---

## WHY CURSOR FOR DEALERSCOPE (NON-CODER PERSPECTIVE)

### 1. Plain-English Repo Interpreter (Your #1 Use Case)
Ask Cursor in plain English, get instant answers with file + line highlighted:
- "Where is the bid ceiling calculated?"
- "Show me every place Crosshair affects scoring"
- "Did Ja'various wire the VIN scanner all the way through to frontend?"
- "Explain the Rover learning loop from event to recommendation"
- "Find every place where pipeline promotion can fail"
- "Compare current scoring logic to our 88% doctrine"

**Why this matters:** DealerScope has 40+ files across backend/frontend/actors/config.
Owner visibility without owner coding.

### 2. Composer — Multi-File Deployment Weapon
Instead of handing Claude Code files one at a time:
- Open Composer in Cursor
- Describe what you want in plain English
- Cursor reads the ENTIRE project, understands existing patterns
- Makes changes to multiple files simultaneously
- You see every diff with red/green highlighting
- Accept all, reject any, modify individual changes

**Example:** "Wire the Recon module. Add recon.py to main.py's router loop. Add ReconPanel.tsx to components. Add 'recon' to the View union in Index.tsx. Match the Rover tab patterns."

One command. Four files. Done correctly.

### 3. Visual Code Review (No More Flying Blind)
When Claude Code pushes a commit:
- Cursor shows exact diff — what was removed (red), what was added (green)
- You approve visually without reading code
- Cursor flags if anything violates .cursorrules business rules

### 4. Audit Applicator
When an AI reviews your code and gives 15-20 findings:
- Paste findings into Cursor Composer
- Say "apply all applicable findings"
- Cursor proposes changes across every affected file
- You review visually: yes / no / skip
- 10 minutes instead of 1 hour

---

## WHAT'S ALREADY BUILT (In The Repo Right Now)

### `.cursorrules` — 105 lines of DealerScope Constitutional Law
Location: `dealscan-insight/.cursorrules`
Committed: `8f0125f`

Contains permanently:
- Bid ceiling: 88% of MMR (COST_TO_MARKET_MAX = 0.88)
- Minimum gross margin: $1,500
- Rust state rejection list (22 states)
- DOS formula: Margin×0.35 + Velocity×0.25 + Segment×0.20 + Model×0.12 + Source×0.08
- Architecture decisions (5 tabs only, Rover in FastAPI, no automated bidding)
- Cross-review protocol (Codex ↔ Claude Code ↔ Cursor)
- All 14 Apify actor names and webhook rules
- Security rules (no hardcoded secrets, SECRET_KEY must be set)
- What NEVER to do

Every AI that opens this repo reads these rules first. Automatically. Forever.

### `.cursor/mcp.json` — Live Data Integration
Location: `dealscan-insight/.cursor/mcp.json`
Committed: `6e95914`

Connects Cursor to:
- **Supabase** — query live deal database directly from Cursor
- **GitHub** — review PRs, see diffs, merge branches inside Cursor

### `cursor-review.yml` — Business Rule Validation
Location: `.github/workflows/cursor-review.yml`
Committed: `9be840b`

Runs on EVERY commit. Blocks merge if:
- Bid ceiling constant (0.88) is changed
- localhost appears in frontend services
- API keys are hardcoded in source
- SECRET_KEY weak default is present

---

## HOW TO ACTIVATE (When You're Ready)

### Step 1 — Prerequisites
- macOS Sonoma 14+ (your current Mac is Monterey 12.7.6 — see Node section below)
- OR: New node with newer hardware

### Step 2 — Install Cursor
- Download from **cursor.com**
- Install normally (it's a Mac app)

### Step 3 — Open DealerScope
- Open Cursor
- File → Open Folder → navigate to `dealscan-insight` local clone
- Cursor automatically reads `.cursorrules`
- Click "Connect MCP" in settings — Supabase + GitHub connect automatically

### Step 4 — Set Local Environment Variables
Cursor MCP needs these in your shell environment:
```bash
export SUPABASE_SERVICE_ROLE_KEY="YOUR_SUPABASE_SERVICE_ROLE_KEY"
export GITHUB_PERSONAL_ACCESS_TOKEN="YOUR_GITHUB_TOKEN"
```
Add to `~/.zshrc` to make permanent.

### Step 5 — First Commands to Try
In Cursor's AI chat (Cmd+L):
- "Explain how a deal flows from Apify webhook to Telegram alert"
- "Show me where the DOS score threshold for alerts is set"
- "What would break if I added a new auction source?"

In Cursor Composer (Cmd+I):
- "Show me all the files that need updating when I add a new router"
- "Apply these audit findings: [paste findings]"

---

## THE NODE STRATEGY (Future)

You're planning 2-3 new nodes with newer hardware. When those arrive:

**Each node running Sonoma unlocks:**
- Full Cursor with all AI features (Background Agents, full Composer)
- Peekaboo (browser vision for Ja'various)
- himalaya email CLI (auto-read Apify alert emails)
- ripgrep + blogwatcher (currently blocked on Monterey)
- Playwright MCP in Cursor (visual scraper testing)

**Distributed DealerScope on nodes:**
- Node 1: Primary OpenClaw + Cursor dev environment
- Node 2: Local Apify actor development/testing (save cloud compute)
- Node 3: Local Redis + heavier ML workloads for Rover

**One macOS upgrade on current Mac also works** — free from App Store,
unlocks everything without waiting for new hardware.

---

## CURSOR'S ROLE IN EACH DEALERSCOPE LAYER

| Layer | Current | With Cursor |
|-------|---------|-------------|
| **Discovery** | 14 Apify actors | Cursor tests scrapers with Playwright MCP visually |
| **Valuation** | Heuristic MMR, transport calc | Cursor queries Supabase for real outcome data, tunes weights |
| **Decision** | DOS formula, 5-layer filter | Cursor validates rules match .cursorrules on every commit |
| **Workflow** | Telegram alerts, Rover | Cursor applies multi-file features in one Composer command |
| **Learning** | Rover event decay | Cursor analyzes Rover events in Supabase, proposes scorer improvements |

---

## QUESTIONS TO ASK CURSOR ABOUT DEALERSCOPE

Save these for when you have Cursor open:

**Architecture questions:**
- "Trace a vehicle from Apify webhook payload to Supabase row, show me every file it touches"
- "Where is the 88% bid ceiling enforced? Show every file"
- "How does Rover learn from a 'save' event? Trace the full path"
- "Show me every place where a Telegram alert can fire"

**Audit questions:**
- "Are there any endpoints missing authentication?"
- "Does any frontend code reference localhost?"
- "Are there any unhandled exceptions in the ingest pipeline?"
- "Show me all the places where we could lose a deal record"

**Business intelligence (via Supabase MCP):**
- "How many opportunities have DOS score above 80 this week?"
- "Which source (GovDeals, PublicSurplus, etc.) is producing the best margin deals?"
- "Show me the distribution of deals by state"
- "How many Rover events have been recorded?"

---

## WHAT CURSOR DOES NOT DO

- Does NOT replace Ja'various for live monitoring and alerts
- Does NOT run in production (it's a dev tool)
- Does NOT automatically bid or take actions on your behalf
- Does NOT work well on macOS Monterey (use on Sonoma+ hardware)

---

## SUMMARY IN ONE SENTENCE

**Cursor sits between Claude's strategy and DealerScope's production — it's the visual review layer where you see every change, approve every diff, and query your live deal data in plain English, without writing a single line of code.**

---

*Guide created by Ja'various | DealerScope Engineering | March 2026*
*Telegram: @JarviscousinJavariousbot | OpenClaw HQ*
