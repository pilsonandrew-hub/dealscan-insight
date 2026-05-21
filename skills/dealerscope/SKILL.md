---
name: dealerscope
description: "DealerScope vehicle arbitrage platform. Use when asked about 
DealerScope, vehicle deals, auction scraping, deal scoring, opportunity 
analysis, the React/TypeScript/Supabase codebase, or any development tasks 
related to the DealerScope project."
---

# DealerScope — Vehicle Arbitrage Platform

## What Is DealerScope?

DealerScope is a live vehicle-arbitrage platform under active hardening. It scrapes and ingests government/public auction sources, analyzes vehicle listings, and identifies potential dealer flip opportunities. Treat production-readiness claims as evidence-bound: verify current code, Railway/Vercel/Supabase state, and CI before asserting PASS.

## Tech Stack

- Frontend: React 18, TypeScript, Tailwind CSS, shadcn/ui
- Backend/API: FastAPI served from Railway (`backend/main.py` canonical entrypoint)
- Database/Auth: Supabase PostgreSQL/Auth with Row Level Security where configured
- Alerts/automation: Telegram, Apify, GitHub Actions, Railway/Vercel control-plane checks
- Build: Vite, npm

## Project Location

The codebase lives at: ~/.openclaw/workspace/projects/dealerscope/

## Key Commands

cd ~/.openclaw/workspace/projects/dealerscope/
npm install
npm run dev
npm run build
npm test
npx vitest run src/tests/services/ApiRouteContract.test.ts
.venv/bin/python -m pytest tests/test_gates.py tests/test_fallback_score.py tests/test_route_contract_aliases.py -q

## Environment Setup

The project needs a .env file with Supabase credentials:
VITE_SUPABASE_URL=your-supabase-project-url
VITE_SUPABASE_ANON_KEY=your-anon-key

## Database Tables

- public_listings: Scraped vehicle data from auction sites
- opportunities: Analyzed arbitrage opportunities with scoring
- user_settings: User preferences and filters
- security_audit_log: Security event tracking

## Sub-Modules

- SniperScope: opportunity targeting
- Crosshair: filtering and threshold management
- Rover: market scouting and crawling

## Important Notes

- Always verify package scripts before assuming commands; `npm test` is currently defined as the full Vitest run.
- Supabase handles auth/database; FastAPI on Railway handles canonical backend routes
- Row Level Security exists where configured, but verify schema/RLS before claiming coverage
- Verify live routes and CI before making production-readiness claims
- The scraper respects rate limits to avoid getting blocked
