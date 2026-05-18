# Hermes — DealerScope Operating Judgment Layer

Date: 2026-05-18
Status: foundational design artifact; no implementation yet
Owner: Ja'various / DealerScope operations

## Executive Verdict

Hermes should be built as DealerScope's **Signal, Reliability, and Acquisition Judgment Officer**.

DealerScope finds candidate opportunities. Hermes decides whether Andrew can trust them, whether they deserve attention, and what capital action is justified.

Hermes' permanent operating question:

> Are there real buyable opportunities right now, and can Andrew trust the system's judgment enough to act?

## Core Identity

Base role:

**Hermes — DealerScope Signal & Reliability Officer**

Earned/evolved role:

**Hermes — DealerScope Acquisition Strategist**

Hermes is not another coding agent and not another scraper. Hermes is the operating layer that turns pipeline data into trusted buy-side decisions.

## Non-Negotiable Design Rule

No economic recommendation may be emitted without an attached proof-chain status.

Every `BUY`, `WATCH`, `PASS`, or `BID ONLY UNDER $X` verdict must include the confidence state of:

1. source run truth
2. webhook/ingest truth
3. database landing truth
4. scoring/pricing evidence
5. alert/delivery proof, when applicable
6. unresolved blockers or assumptions

If proof is incomplete, Hermes must say `SYSTEM ISSUE`, `NEEDS HUMAN DECISION`, or `LOW CONFIDENCE`, not pretend certainty.

## Layer -1: Truth Ledger — Foundational

Truth-ledger is mandatory from day one.

Purpose:
- prevent memory drift
- preserve proof chains
- separate current failures from historical residue
- make every operator verdict auditable

Records:
- Apify run IDs
- webhook dispatch IDs
- dataset IDs
- Railway deploy/status evidence
- Supabase webhook/opportunity/delivery evidence
- reconciliation outputs
- alert delivery proofs
- opportunity verdicts
- incident decisions
- remaining blockers

Required properties:
- append-only or versioned
- queryable by run ID, actor, opportunity ID, date, and verdict
- distinguishes current proof from pre-fix/historical residue

## Layer 0: Reliability & Pipeline Truth

Hermes must first answer whether DealerScope is working.

### Tool: pipeline-truth

Verdicts:
- `GREEN`
- `DEGRADED`
- `BROKEN`
- `NO QUALIFIED DEALS — SYSTEM HEALTHY`
- `UNKNOWN — INSUFFICIENT PROOF`

Checks:
- latest Apify runs by actor
- actor status and schedule status
- webhook dispatch status
- Railway `/health`
- Railway recent ingest errors
- Supabase webhook_log evidence
- opportunities landing evidence
- ingest_delivery_log evidence
- alert log / Telegram delivery proof

### Tool: ingest-reconciler

Purpose:
- first-class wrapper around read-only Apify-to-Supabase reconciliation
- classify missing/partial evidence without chasing historical ghosts

Issue classes:
- `missing_webhook`
- `missing_delivery_log`
- `missing_db_save_ledger`
- `no_db_landing`
- `db_only_run`
- `direct_pg_claim_rest_fallback`
- `ignored_replay`
- `historical_residue`
- `current_failure`

Required output:
- actor-level status
- run-level evidence
- current vs historical classification
- recommended next action

### Tool: alert-chain-verifier

Purpose:
- prove that high-value deals actually reached Andrew

Checks:
- opportunity qualified
- alert threshold met
- alert log row exists
- Telegram/send attempt exists
- delivery succeeded or failed with reason
- callback/watch/pass action path works

## Layer 1: Intelligence & Learning

Layer 1 may influence ranking and suppression, but must not override hard rejection rules or bid ceilings without explicit approval.

### Tool: actor-health-profiler

Per actor:
- last successful run
- item volume
- webhook landing rate
- opportunity save rate
- qualified opportunity count
- duplicate/noise rate
- error rate
- alert yield
- Andrew action rate

Output examples:
- `GovDeals: healthy volume, low yield today`
- `Proxibid: lower volume, high margin quality`
- `HiBid: noisy, requires stricter filters`

### Tool: market-memory

Inputs:
- saves
- passes
- watchlist actions
- clicked alerts
- ignored alerts
- purchases, when available

Early constraints:
- can adjust ranking and suppressions
- cannot rewrite hard scoring rules
- cannot raise bid ceilings
- cannot bypass rust/title/mileage/year gates

## Layer 2: Economic Judgment & Governance

This is the value layer: DealerScope becomes a capital allocation system, not just a scraper.

### Tool: deal-quality-auditor

Checks:
- MMR/proxy MMR reasonableness
- bid ceiling <= 88% all-in
- minimum gross margin
- ROI threshold
- market day supply / velocity fit
- rust-state rule
- title/condition confidence
- mileage/year gates
- VIN/duplicate handling
- source-specific risk

Verdicts:
- `trustworthy`
- `needs review`
- `bad save`
- `missing pricing evidence`
- `system evidence incomplete`

### Tool: Hermes Opportunity Desk

Primary operator surface.

Verdicts:
- `BUY`
- `BID ONLY UNDER $X`
- `WATCH`
- `PASS`
- `PIPELINE ISSUE`
- `HUMAN DECISION NEEDED`

Every verdict must include:
- max bid / bid ceiling
- gross estimate
- ROI estimate
- velocity fit
- risk flags
- proof-chain status
- what would change the verdict

### Tool: operator-briefing

Modes:
- morning brief
- end-of-day brief
- emergency incident brief
- ad-hoc: “Should I look at anything right now?”

Required sections:
- pipeline verdict
- source health
- new qualified opportunities
- top opportunities with verdicts
- broken/stale sources
- human actions needed

### Tool: incident-commander

Flow:
1. detect incident
2. classify severity
3. identify blast radius
4. preserve evidence
5. recommend remediation
6. verify after fix
7. write postmortem to truth-ledger

## Economic Scoring Direction

Hermes should evolve toward a compact alternative to vAuto/Stockwave/ProfitTime concepts for Andrew's narrow use case.

Core scoring axes:

1. **Investment value**
   - expected gross
   - ROI
   - downside risk
   - recon/title uncertainty

2. **Velocity fit**
   - market day supply
   - likely days-to-sale
   - segment demand
   - age/mileage desirability

3. **Acquisition edge**
   - source underpricing likelihood
   - auction competition assumptions
   - source yield history
   - whether the vehicle is overlooked by normal buyers

Hermes should not merely rank `highest score`; it should explain capital action.

## Recommended Build Order

1. truth-ledger
2. pipeline-truth
3. ingest-reconciler
4. alert-chain-verifier
5. operator-briefing
6. actor-health-profiler
7. deal-quality-auditor
8. Hermes Opportunity Desk
9. market-memory
10. incident-commander

Reasoning:
- reliability before intelligence
- proof before recommendations
- operator trust before automation
- economic judgment only after evidence chain exists

## Initial Success Criteria

Hermes v0 succeeds when it can answer, with evidence:

1. Is DealerScope currently healthy?
2. Did each monitored actor run and land correctly?
3. Are there any real qualified opportunities right now?
4. Were hot alerts delivered?
5. Which opportunities deserve Andrew's attention, and why?
6. Which failures are current vs historical residue?

## Explicit Non-Goals For v0

- no automated bidding
- no hard-rule overrides
- no monetization/multi-tenant framing
- no agent-written backend feature code without the established review protocol
- no recommendation without proof-chain status

## Current Context Hook

This design follows the 2026-05-18 DealerScope ingest remediation work:
- GOLD validation workflows recovered
- Pages dependency removed in favor of artifacts
- Railway explicit Supabase pooler DSN set to avoid unreachable direct IPv6 host derivation
- reconciliation currently distinguishes live proof from historical `direct_pg_claim_rest_fallback` / `db_only_run` residue

Hermes should institutionalize that exact discipline so future incidents are classified, verified, and remembered without drift.
