# DealerScope Product Truth Register

Date: 2026-05-26
Owner: Ja'various
Status: Control-tower product truth register / requires live verification for live-confirmed claims
Purpose: map DealerScope product surfaces to current evidence, risk, and proof requirements so money/alert/operator claims do not outrun reality.

---

## Current safe product label

DealerScope is a **dealer-intelligence and execution platform** for identifying, filtering, scoring, prioritizing, evaluating, and managing vehicle opportunities across auction/acquisition workflows.

Current safe posture:

- real product surfaces exist
- deterministic scoring/filtering logic exists in source
- ingest, alert, analytics, and operator modules exist
- maturity varies by surface
- live proof must be refreshed before production-grade claims

Do not describe DealerScope as a fully autonomous buying engine, complete enterprise SaaS, or production-proven AI operating system unless that is proven live end to end.

---

## Truth-critical surfaces

| Surface | Business risk if wrong | Current source authority | Current status label | Proof required for live-confirmed |
|---|---|---|---|---|
| Opportunity ingest | Bad inventory, duplicate rows, missed deals, source drift | `webapp/routers/ingest.py`, `backend/ingest/*`, Apify actors | source-confirmed / needs live refresh | Recent webhook logs, saved opportunities, source counts, validation of skipped/processed semantics. |
| Pricing/MMR/fallback pricing | Direct money-decision risk | `backend/ingest/score.py`, `retail_comps.py`, `manheim_market.py`, fallback scoring/pricing helpers | source-confirmed / high-risk | Tests and live sample proving bid ceiling, margin floor, pricing provenance, and missing-price behavior. |
| DOS/opportunity score | Bad prioritization and alert eligibility | `backend/ingest/score.py`, scoring tests | source-confirmed / high-risk | Deterministic tests and live sample distribution with violations count. |
| Rust-state/newer-vehicle rules | False rejects or unsafe buys | scoring/gating code and tests | source-confirmed / high-risk | Tests for high-rust rejection and newer-vehicle exception. |
| Alerts/Telegram | Operator trust, missed opportunities, false interruptions | `telegram_alerts.py`, alert gating/threshold/delivery code | source-confirmed / needs live delivery proof | Alert log + Telegram receipt verification for current route. |
| Rover | Recommendation trust and operator preference capture | `backend/rover/*`, `webapp/routers/rover.py`, frontend Rover service | source-confirmed | API smoke, event write proof, fallback-vs-personalized behavior proof. |
| Crosshair | Operator search/filter workflow | frontend Crosshair + service/API path | source-confirmed | Browser/API smoke proving filters, result display, save/watch/export behavior as claimed. |
| SniperScope | High-intent opportunity follow-up | `webapp/routers/sniper.py`, UI/service surfaces | source-confirmed / not automated bidding | API/UI smoke and DB proof for target lifecycle. |
| Analytics/outcomes | Operator and diligence credibility | `webapp/routers/analytics.py`, `outcomes.py`, analytics tests | historically live-improved but needs current live refresh | Live route output, schema consistency, nonzero outcomes/execution logic proof. |
| Apify actors | Source coverage and freshness | `apify/actors/*`, deployment manifest, Apify runs | needs live actor proof | Actor health, recent run status, dataset sample, webhook delivery. |
| Deployment | Whether any local/source truth is actually live | Railway/Vercel/GitHub run evidence | needs current live proof | Current endpoint smoke + deploy/run status. |

---

## Product modules and safe language

| Module | Safe current description | Do not claim without proof |
|---|---|---|
| Dashboard | Routed operator shell hosting DealerScope modules. | Complete executive BI cockpit or enterprise command center. |
| Crosshair | Deterministic opportunity filtering/search layer. | AI search engine or autonomous buyer. |
| Rover | Recommendation layer with event tracking and fallback inventory behavior. | Self-optimizing ML portfolio manager. |
| SniperScope | Targeted action/follow-up layer for high-interest opportunities. | Automated bidding or trading engine. |
| Recon | Assisted vehicle/deal evaluation surface. | Autonomous underwriting guarantee. |
| Sonar | Specialized scanning/search workflow. | Main system-of-record search authority unless proven. |
| Analytics | Operator-facing measurement and health surface. | Complete enterprise BI/data warehouse. |
| Outcomes | Manual/assisted outcome tracking and writeback path. | Fully automated sales execution ledger unless live-proven. |
| Upload/Ingest | Controlled validation/ingestion support surface. | Universal data ingestion guarantee. |

---

## Money-decision invariants

These are non-negotiable truth gates for any feature touching buy/sell decisions:

1. Bid ceiling must respect the 88% MMR/all-in ceiling where MMR/proxy data supports it.
2. Minimum gross margin and ROI rules must not be silently bypassed.
3. Rust-state rejection and newer-vehicle exception must be deterministic and tested.
4. Missing/weak pricing provenance must downgrade confidence or block alerting, not silently masquerade as reliable value.
5. Alert eligibility must be stricter than display eligibility.
6. Frontend labels must not imply stronger certainty than backend provenance supports.
7. Historical reports cannot override live source/schema truth.

---

## Current known caution points

These are not final bug claims; they are risk areas that require live/source proof before strong status language:

- Analytics has a history of schema mismatch and execution/outcome contradiction; refresh before diligence claims.
- Workflow inventory visible in this workspace is ACE-heavy; do not claim full product CI coverage from ACE CI.
- Obsidian/mirror cleanliness has historically been scope-limited; do not generalize mirror parity claims.
- Old DealerScope reports may contain completion/finalization language that is historical, not current authority.
- Apify/source health must be checked live; actor lists in memory are not current proof by themselves.
- Composio/OpenClaw config/security work is separate from DealerScope product truth unless it affects current integrations.

---

## Proof checklist before saying “green”

For any future DealerScope closeout, require at least one relevant proof from each applicable category:

- **Source proof:** exact files/commit changed and diff reviewed.
- **Test proof:** targeted tests for the affected product rule.
- **Build proof:** frontend/backend build or import smoke where relevant.
- **Live proof:** endpoint, DB, Apify, alert, or deployment evidence when claiming live behavior.
- **Workflow proof:** GitHub Actions URL/check-run status when claiming CI.
- **Operator proof:** screenshot/browser/Telegram/alert evidence when claiming user-facing behavior.

No single artifact substitutes for all categories.

---

## Next recommended product-truth pass

Run a narrow, read-only live refresh in this order:

1. Current git/branch/dirty state.
2. Current GitHub check runs for active branch.
3. Current backend health endpoint and route inventory.
4. Supabase read-only aggregate for recent opportunities, alerts, webhooks, outcomes.
5. Apify recent actor run status for active sources.
6. Frontend build and one browser smoke for Dashboard/Crosshair/Rover/Analytics.

Only after that should stale reports be edited or banners added.
