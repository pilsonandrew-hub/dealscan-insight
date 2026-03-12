# DealerScope Roadmap (from SOW)
_Last updated: 2026-03-10_
_SOW stored at: projects/dealerscope/docs/DealerScope_SOW.pdf_

## Vision
Enterprise-grade AI-powered deal intelligence platform for wholesale auto arbitrage.
- Reduce deal identification time: 5-10 hrs → <30 min
- Increase monthly transaction volume: 5-10 → 20+ vehicles
- Netflix-grade personalized recommendations
- Eventually: SaaS platform for the broader wholesale community

## Target Users
1. Independent wholesale buyers (primary — Andrew)
2. Buyer agents
3. Small dealership groups
4. Large dealership managers
5. Independent dealers

---

## PHASE 1 — Foundation ✅ COMPLETE
- [x] Technical architecture
- [x] React 18 + TypeScript + Vite + Tailwind + shadcn/ui
- [x] Supabase auth + JWT + TOTP 2FA + RLS
- [x] Database schema design
- [x] Security audit + hardening (rate limiting, SSRF, XSS, audit log)
- [x] Docker containerization

---

## PHASE 2 — Core Development 🔄 IN PROGRESS

### Data Aggregation ✅
- [x] GovDeals scraper (Apify actor deployed)
- [x] PublicSurplus scraper (Apify actor deployed)
- [x] Data normalization engine
- [x] Webhook ingest endpoint
- [x] Apify 3-hour scrape schedules
- [ ] **Manheim API integration** ← HIGHEST PRIORITY
- [ ] GSA auctions scraper

### ML / AI ✅
- [x] Price prediction model
- [x] Opportunity scoring model
- [x] Risk assessment model
- [x] Five-layer institutional filter (EchoPark/AutoNation standard)
- [x] CPO eligibility detection
- [x] Scarcity index proxy
- [ ] Personalized recommendation engine (collaborative filtering)
- [ ] Market trend analysis + seasonal adjustment

### Dashboard ✅
- [x] Real-time opportunity feed with score ranking
- [x] Deal inbox (EnhancedDealInbox)
- [x] CrosshairDashboard
- [x] Opportunity filtering (location, price, mileage, condition)
- [x] ML model dashboard
- [ ] Deal comparison tool (side-by-side)
- [ ] Export functionality (CSV, PDF)

### Alerts & Notifications ⏳
- [x] Telegram alert framework (in ingest endpoint)
- [ ] **Real-time WebSocket push notifications** ← HIGH PRIORITY
- [ ] Bid reminders (alert X hours before auction closes)
- [ ] Auction end time alerts in user timezone

---

## PHASE 3 — Advanced Features ⏳

### Search
- [x] Crosshair targeting mode (partial)
- [ ] Complete crosshair: save specific make/model/trim searches
- [ ] Passive discovery mode (continuous background monitoring)
- [ ] Saved intents with automated alerts
- [ ] VIN scanning (mobile) ← HIGH VALUE at auctions

### Mobile / PWA
- [x] Responsive design
- [ ] PWA with offline functionality
- [ ] Voice search
- [ ] Photo capture integration

### Analytics
- [ ] Business KPI dashboard (deal volume, profit margins, win rates)
- [ ] Historical performance analysis
- [ ] Custom report generation

---

## PHASE 4 — Deployment & Launch ⏳

### Infrastructure
- [ ] **Deploy FastAPI backend to production server** ← BLOCKING EVERYTHING
- [ ] Update Apify webhook URL to real endpoint
- [ ] Set Supabase service role key in production env
- [ ] Redis + Celery in production
- [ ] CDN for static assets

### Testing
- [ ] Comprehensive test suite (frontend + backend)
- [ ] End-to-end pipeline test (scrape → ingest → score → alert)
- [ ] Load testing

### SaaS (Phase 2 business)
- [ ] Multi-tenant architecture
- [ ] Stripe billing integration
- [ ] Subscription tiers
- [ ] API access for premium users
- [ ] White-label options

---

## PRIORITY ORDER (Next Actions)
1. 🔴 Deploy backend to production (Railway, Render, or VPS)
2. 🔴 Manheim API integration (OAuth) — primary data source
3. 🟠 Real-time WebSocket notifications
4. 🟠 Complete crosshair targeting mode
5. 🟡 VIN scanning for mobile
6. 🟡 Bid reminders + auction end time alerts
7. 🟡 Notion integration (mobile deal tracking)
8. 🟢 CSV/PDF export
9. 🟢 Deal comparison tool
10. 🟢 Personalized recommendation engine

---

## Key Metrics to Track
- Deal identification time (target: <30 min)
- Monthly transaction volume (target: 20+)
- ML prediction accuracy (target: 87%+)
- API response time (target: <200ms)
- System uptime (target: 99.9%)
