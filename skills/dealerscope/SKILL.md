---
name: dealerscope
description: "DealerScope vehicle arbitrage platform. Use when asked about 
DealerScope, vehicle deals, auction scraping, deal scoring, opportunity 
analysis, the React/TypeScript/Supabase codebase, or any development tasks 
related to the DealerScope project."
---

# DealerScope — Vehicle Arbitrage Platform

## What Is DealerScope?

DealerScope is a production-ready vehicle arbitrage platform that scrapes 
government and public auction sites (GovDeals, PublicSurplus, GSA, 
Treasury, and 20+ others), analyzes vehicle listings, and identifies 
profitable flip opportunities for dealers.

## Tech Stack

- Frontend: React 18, TypeScript, Tailwind CSS, shadcn/ui
- Backend: Supabase (Auth, PostgreSQL Database, Edge Functions)
- Real-time: WebSocket updates for live deal notifications
- Security: Row Level Security, JWT + TOTP auth, audit logging
- Build: Vite, npm

## Project Location

The codebase lives at: ~/.openclaw/workspace/projects/dealerscope/

## Key Commands

cd ~/.openclaw/workspace/projects/dealerscope/
npm install
npm run dev
npm run build
npm test

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

- Always run npm install after pulling new changes
- Supabase handles auth, database, and edge functions
- Row Level Security is enabled
- WebSocket connections provide real-time deal updates
- The scraper respects rate limits to avoid getting blocked
