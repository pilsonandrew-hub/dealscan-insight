# DealerScope Current Authority Index

Date: 2026-05-26
Owner: Ja'various
Status: Control-tower authority map / not a product-status proof
Purpose: define which DealerScope sources win when code, docs, memory, reports, workflows, and mirrors disagree.

---

## Executive rule

DealerScope truth is not decided by the newest narrative or the cleanest report.

When sources conflict, use this order:

1. **Live production/runtime evidence** — deployed endpoint behavior, live database/schema inspection, CI/check-run truth, Apify/Railway/Vercel/Supabase run evidence.
2. **Current source-of-record repo code** — canonical backend/frontend/ingest/workflow code at the active branch/commit.
3. **Live schema and migrations** — Supabase schema/migrations and live read-only inspection output.
4. **GitHub Actions / deployment workflows** — because they encode operational gates, business-rule assumptions, and release behavior.
5. **Current authority docs/registers** — this index, workflow authority register, product truth register, and explicitly current product truth memos.
6. **Governed brain / continuity artifacts** — useful for intent and history, but subordinate to live code/runtime truth.
7. **Daily memory logs** — useful chronology and context, not proof by themselves.
8. **Historical reports, plans, audits, and mirrors** — preserved for audit trail; not current authority unless explicitly promoted and still consistent with live truth.

If a source is not live-verifiable and affects money, alerts, pricing, product claims, or operator workflow, classify it as **unproven** until verified.

---

## Canonical repo and project surfaces

| Surface | Current authority role | Notes |
|---|---|---|
| `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope` | Primary DealerScope working repo | Contains backend, frontend, ACE, tests, workflows, Apify actors, continuity artifacts. Has its own git root. |
| `https://github.com/pilsonandrew-hub/dealscan-insight` | Remote source-of-record | Push/CI status must be checked here when claiming shipped or green. |
| `/Users/andrewpilson/.openclaw/workspace/reports` | Workspace-level report archive | Mixed current and historical. Must be status-labeled before treated as authority. |
| `brains/dealerscope-brain` | Governed knowledge source | Useful continuity source; not stronger than live repo/runtime evidence. |
| Obsidian DealerScope Brain mirror | Operator-visible mirror | Mirror status must be scope-labeled; do not assume global cleanliness. |

---

## Canonical code surfaces

| Area | Primary current authority | Truth use |
|---|---|---|
| Backend app entry | `projects/dealerscope/backend/main.py` | FastAPI/runtime entrypoint truth. |
| Ingest/webhook path | `projects/dealerscope/webapp/routers/ingest.py`, `projects/dealerscope/backend/ingest/*` | Source normalization, scoring, save behavior, alert gating. |
| Scoring/pricing | `projects/dealerscope/backend/ingest/score.py`, `retail_comps.py`, `manheim_market.py`, fallback/pricing helpers | Money-decision truth; highest scrutiny. |
| Condition/VIN/identity | `condition.py`, `vehicle_identity.py`, `canonical_identity.py`, listing/raw identity helpers | Data-trust and dedupe truth. |
| Alerts | `telegram_alerts.py`, `alert_gating.py`, `alert_thresholds.py`, `delivery_log.py`, alert tests | Operator interruption and trust truth. |
| Rover | `backend/rover/*`, `webapp/routers/rover.py`, frontend Rover services/components | Recommendation/event truth; not full autonomous intelligence unless proven. |
| Crosshair/search | frontend Crosshair surfaces + service/API route usage | Deterministic search/filter truth. |
| SniperScope | `webapp/routers/sniper.py` and related UI/service surfaces | Target/watch/follow-up truth; not automated bidding unless proven. |
| Analytics/outcomes | `webapp/routers/analytics.py`, `webapp/routers/outcomes.py`, outcome tests | Execution/outcome/trust reporting truth. |
| Workflows/CI | `.github/workflows/*`, `projects/dealerscope/.github/workflows/*` | Operational gate truth; workflow theater risk must be classified. |

---

## Current authority documents

| Document | Status | How to use |
|---|---|---|
| `reports/DEALERSCOPE-PRODUCT-TRUTH-MEMO-2026-04-20.md` | Current product-definition baseline, unless contradicted by newer live truth | Use for safe language around what DealerScope is/is not. |
| `reports/DEALERSCOPE-CURRENT-AUTHORITY-INDEX.md` | Current authority map | Use to resolve conflicts and stop cleanup theater. |
| `reports/DEALERSCOPE-WORKFLOW-AUTHORITY-REGISTER.md` | Current workflow classification register | Use to decide whether a workflow is gate/advisory/legacy. |
| `reports/DEALERSCOPE-PRODUCT-TRUTH-REGISTER.md` | Current money/product truth register | Use to decide what product claims are live-proven vs pending. |
| Older ACE/DealerScope plans | Historical unless explicitly current | Preserve, banner if risky, do not treat as proof. |

---

## Decision labels

Use these labels in all DealerScope status claims:

- **live-confirmed** — verified against production/runtime/CI/live DB or deployed service behavior.
- **source-confirmed** — verified in current repo code/tests, but not live runtime.
- **locally validated only** — tests or local smoke pass, no live proof.
- **historical** — useful archive; not current authority.
- **superseded** — contradicted by newer live/source truth.
- **unproven** — claim may be plausible, but lacks current evidence.
- **theater risk** — looks like proof or governance but does not actually protect product truth, money decisions, alerts, operator workflow, or future-agent correctness.

---

## Cleanup admission rule

A cleanup item is valid only if it reduces risk to at least one of:

- money decisions
- pricing/scoring truth
- alert trust
- live operator workflow
- future agent correctness
- investor/diligence credibility
- governed continuity accuracy

If it only makes old archives prettier, do not do it.
