# DealerScope — Project Memory

## What It Is
Wholesale vehicle arbitrage system. Buys vehicles from government/municipal auctions (GovDeals, PublicSurplus) and resells to CA dealers at a margin.

## Owner
Gs Tyd (Andrew Pilson) — pilson.andrew@gmail.com

## Repos
- **Dealerscope** (backend/pipeline): https://github.com/pilsonandrew-hub/Dealerscope
  - Python FastAPI + SQLite
  - Scrapers, deal scoring, pipeline orchestration
  - Status: Blueprint stage, 10 bugs to fix before it runs
- **dealscan-insight** (frontend + ML): https://github.com/pilsonandrew-hub/dealscan-insight
  - React 18 + TypeScript + Tailwind + shadcn/ui
  - Supabase backend, ML scoring models
  - Status: More complete, active development
- **Unified work dir**: /tmp/dealerscope-unified (cloned dealscan-insight)

## Tech Stack
- **Frontend**: React 18, TypeScript, Vite, Tailwind, shadcn/ui
- **Backend**: Python FastAPI (modular routers)
- **Database**: Supabase (PostgreSQL) + SQLite for local pipeline
- **ML**: price_predictor.py, opportunity_scorer.py, risk_assessor.py
- **Scraping**: Python async scrapers + Playwright (TypeScript)
- **Auth**: JWT + TOTP (2FA)
- **Infra**: Docker, Redis, Celery, Prometheus

## Architecture Plan (Unified)
```
dealerscope/
├── backend/          ← Python FastAPI
│   ├── src/ingest/   ← scrapers (GovDeals, PublicSurplus)
│   ├── src/score/    ← deal scoring + ML
│   └── webapp/       ← routers, models, security
├── frontend/         ← React/TypeScript
└── infra/            ← Docker, monitoring
```

## Key Business Logic
- **Rust state filter**: Only buy from dry/low-rust states (AZ, CA, NV, CO, NM, UT, TX, FL, etc.)
- **Transport cost calc**: Mileage bands ($/mile) + fly-drive option
- **Deal scoring**: margin = MMR_CA - bid - buyer_premium - doc_fee - transport
- **Score**: margin / max(1000, bid) — higher = better opportunity
- **Min net**: $1,500 default (NET_MIN env var)

## Auction Sources
- GovDeals (12.5% buyer premium, $75 doc fee)
- PublicSurplus (10% buyer premium, $50 doc fee)

## Current Status (as of 2026-03-10)
- Agent running fixes on dealscan-insight (session: tidy-orbit)
- Tasks: fix backend bugs, add stateClassification.ts + useSniperTargets.ts, clean doc clutter
- Next: Notion integration for mobile deal tracking
- Backend still needs Redis/Celery server to run pipeline

## Common Commands
```bash
# Frontend dev
cd /tmp/dealerscope-unified && npm install && npm run dev

# Backend dev
cd /tmp/dealerscope-unified/webapp && pip install -r requirements.txt
uvicorn webapp.main:app --reload

# Offline pipeline test
OFFLINE_MODE=1 python -m src.ingest.scrape_all

# Run tests
npm test
pytest tests/
```

## Integrations Planned
- Notion — deal tracker database, dev board, daily briefing
- Telegram alerts — hot deal notifications
- Manheim API — real MMR/market values

## Coding Agent Failover (added 2026-03-10)
- Primary: Claude Code (`claude --permission-mode bypassPermissions --print`)
- Fallback: Codex CLI at `~/.local/bin/codex` (v0.113.0)
- OpenAI key in ~/.zshrc + ~/.bash_profile + openclaw.json
- Codex config: ~/.codex/config.toml (model: codex-mini-latest)
- Failover script: workspace/scripts/code-agent.sh
- Claude Code rate limit resets at 1pm PT daily

## Apify Integration (added 2026-03-10)
- Account: Javariousthebot
- Plan: FREE ($5 compute units/mo — upgrade to $49 Starter for production)
- Token: stored in openclaw.json integrations.apify
- Webhook secret: stored in openclaw.json integrations.apify
- Actors to build: ds-govdeals, ds-publicsurplus, ds-gsa, ds-manheim
- Webhook endpoint: POST /api/ingest/apify → normalize → five-layer filter → Supabase
