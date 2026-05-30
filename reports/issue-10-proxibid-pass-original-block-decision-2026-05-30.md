# Issue #10 — Proxibid PASS_ORIGINAL Block Decision

Date: 2026-05-30
Owner posture: Ja'various / Andrew owner-orchestrator
Status: **BLOCK under PASS_ORIGINAL**
Next issue: **Issue #11 remains frozen until explicit owner stop/go**

## Decision

Issue #10 is not a code-pass and not a caveated pass. It remains **BLOCK** under the accepted `PASS_ORIGINAL` standard.

The current evidence shows:

1. The Proxibid actor is extracting enrichment data.
2. The actor emits `current_bid`, source metadata, run lineage, and `source_quality_proof` records.
3. Ingest accepts `currentBid/current_bid` and preserves `run_id`, `source_run_id`, `actor_run_id`, and `apify_run_id`.
4. Sanitized live inspection shows webhook/delivery processing occurs.
5. Rows are rejected before opportunity persistence by existing strict gates, normalization, or ceiling logic.
6. The source-quality proof correctly fails because the latest actor run has zero accepted Supabase opportunities with actor-run lineage.

Therefore the failure mode is currently classified as **source quality / low-yield truth under strict DealerScope gates**, not a proven actor mapping bug, ingest lineage bug, or proof-query mismatch.

## Non-negotiable acceptance criteria

A clean PASS requires all of the following, without loosening gates or thresholds:

- recent live Supabase accepted opportunities for Proxibid
- exact `source_site=proxibid`
- actor-run lineage proven for accepted opportunity rows
- pricing/provenance completeness
- VIN presence >= 5%
- mileage presence >= 1%
- clean CI/Cursor/live proof
- no buyer-grade filter loosening
- no proxy-pricing trust elevation
- no diagnostic scraper proof counted as accepted-opportunity proof

## Evidence: latest operational proof lane

### Actor run

Workflow: `Run Apify Actor`
Run: `26690689642`
Actor: `ds-proxibid`
Input: `max_items=80`, `max_detail_pages=120`
Actor run ID: `gAoWd3Yn9jx5g4OjY`
Dataset ID: `o8ekBLfHGyrp32myG`
Conclusion: success

Scraper proof:

- dataset items sampled: 24
- detail pages attempted: 80
- detail pages fetched: 80
- detail pages failed: 0
- detail VINs found: 60
- detail mileages found: 59
- enriched rows accepted by actor: 13
- enriched rows rejected by actor: 57
- rejection reasons:
  - `condition_reject`: 21
  - `mileage_over_50k`: 49

Interpretation: extraction is working. This does not prove accepted opportunity persistence.

### Sanitized live inspection

Workflow: `DealerScope Supabase Live Inspection`
Run: `26690840343`
Target run ID: `gAoWd3Yn9jx5g4OjY`
Conclusion: success

Result:

- opportunities for actor run: 0
- delivery rows: 24
- delivery statuses:
  - `skipped_gate`: 22
  - `skipped_norm`: 1
  - `skipped_ceiling`: 1
- sanitized skip reasons:
  - `bid_not_positive ($0)`: 11
  - `age_or_mileage_exceeded`: 11
  - `normalize_rejected`: 1
  - `pricing_maturity_proxy | bid=$17,250 max_bid=$0 mmr=$24,000 headroom=$-17,250 tier=premium`: 1

Interpretation: rows are reaching ingest evidence logs but are rejected before opportunity save.

### Source Quality Proof

Workflow: `DealerScope Source Quality Proof`
Run: `26690854279`
Source: `proxibid`
Sample size: 300
Conclusion: failure by design
Verdict: `BLOCK`

Accepted opportunity sample:

- sample count: 300
- source_site exact: 100%
- pricing raw present: 100%
- provenance present: 100%
- confidence present: 100%
- VIN present: 2.0%
- mileage present: 0.0%
- latest accepted opportunity in sample: `2026-05-28T19:07:27.789554+00:00`

Latest actor-run proof:

- actor run ID: `gAoWd3Yn9jx5g4OjY`
- accepted opportunities for actor run: 0
- run lineage proven: false
- low-yield source truth detected: true

Interpretation: `PASS_ORIGINAL` is not met. The workflow is correctly enforcing the standard.

## Why no patch is currently safe

A patch would only be safe if it fixed a proven implementation defect. Current evidence does not show one.

Unsafe under the current policy:

- weakening buyer-grade filters
- accepting rows with invalid or zero bids
- trusting proxy pricing as capital-ready evidence
- treating rejected enriched rows as opportunities
- reducing VIN/mileage thresholds
- replacing accepted-opportunity proof with scraper telemetry
- moving to Issue #11 while #10 is unresolved or not explicitly re-scoped

## Professional enterprise path forward

The correct next step is an owner decision, not more unbounded patching.

Options:

1. **Accept #10 as BLOCK under PASS_ORIGINAL** and leave it as an operational/source-yield constraint.
2. **Authorize a narrow operational acquisition lane**: keep gates unchanged, run more targeted known-good Proxibid inventory until real publishable rows appear, then rerun source-quality proof.
3. **Explicitly re-scope #10** from accepted-opportunity enrichment proof to scraper/source diagnostics, with new acceptance criteria approved by Andrew.
4. **Produce a one-to-one lot trace proving an implementation bug** (for example, a valid positive bid collapsed to zero, a valid mileage wrongly normalized, or a valid accepted row missed by proof query). Only then patch.

Recommendation: choose option 1 or option 2. Do not patch gates. Do not move to #11 unless Andrew explicitly accepts #10 as BLOCK or re-scopes it.

## Current stop condition

Stop here for Issue #10 unless Andrew chooses one of the above options.
