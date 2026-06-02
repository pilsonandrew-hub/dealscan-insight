# Pricing Substrate Remediation Plan

## Goal

Restore trustworthy market-comp pricing evidence so clean scraper rows can graduate from proxy pricing without weakening DealerScope's alert/save gates.

Current status labels:

- Active high-DOS VIN/mileage surface: **live-confirmed** clean.
- GovDeals/PublicSurplus pushed-row source quality: **live-confirmed** clean for bounded proofs.
- GovPlanet detail VIN enrichment: **locally and live tested, yield-blocked** because sampled list/detail HTML did not expose VIN.
- Pricing substrate: **live-confirmed blocker**. `public.market_prices` is missing and `public.dealer_sales` has only weak/stale rows, so current clean rows are rejected by `ceiling:pricing_maturity_proxy`.

## Non-Goals

- Do not loosen `pricing_maturity_proxy`, alert gating, DOS scoring, or ceiling checks to create artificial yield.
- Do not seed `market_prices` from proxy-only MMR estimates.
- Do not treat stale or unproven dealer-sales rows as market-comp evidence.
- Do not continue broad scraper cleanup unless a source produces a live contradiction against the current quality gates.

## Evidence

- `/api/internal/pipeline-truth` now exposes `pricing_substrate` via commit `ec26b5d`.
- Production truth at the time of diagnosis:
  - `market_prices_table = missing`
  - `dealer_sales_table = present`
  - `dealer_sales_rows = 2`
  - `latest_dealer_sale_date = null`
  - `ready_for_market_comp_pricing = false`
- `backend/ingest/retail_comps.py` already prefers:
  1. `market_prices`
  2. `dealer_sales`
  3. empty result, allowing the proxy path to remain gated.
- `supabase/migrations/20260314_retail_comps.sql` adds comp columns to `opportunities`, but does not create `market_prices`.

## Implementation Steps

### 1. Schema Contract

Add a migration that creates `public.market_prices` with the fields the retail-comp service already reads:

- `id`
- `year`
- `make`
- `model`
- `state`
- `avg_price`
- `low_price`
- `high_price`
- `sample_size`
- `last_updated`
- `expires_at`

Add provenance columns before using it operationally:

- `source`
- `source_run_id`
- `source_url`
- `confidence_notes`
- `created_at`
- `updated_at`

Add indexes for the live query shape:

- `(year, make, model, state, last_updated desc)`
- `(year, make, model, last_updated desc)`
- `expires_at`

### 2. Verifier Coverage

Add a verifier that checks:

- `public.market_prices` exists.
- Required columns and indexes exist.
- `public.market_prices` has at least one non-expired row only when the rows are provenance-backed.
- `public.dealer_sales` readiness requires non-null recent `sale_date` and positive `sale_price`.
- `/api/internal/pipeline-truth.pricing_substrate.ready_for_market_comp_pricing` turns true only when evidence is usable.

Extend the backend test for `pricing_substrate` with:

- missing `market_prices`
- present but empty `market_prices`
- present non-expired `market_prices`
- stale/expired `market_prices`
- stale `dealer_sales`
- recent usable `dealer_sales`

### 3. Provenance-Safe Seed/Input Path

Build a seed/import path only from evidence that already qualifies as market evidence:

- Rows with `pricing_maturity = 'market_comp'`
- Positive `retail_comp_price_estimate`
- `retail_comp_count >= 2`
- `retail_comp_confidence >= 0.60`
- Non-null make/model/year
- Non-null provenance source

Rejected seed sources:

- Proxy-only MMR estimates
- `pricing_maturity = 'proxy'`
- Rows with null/weak retail comp counts
- Rows with null/weak confidence
- Rows without provenance

### 4. Live Proof

Run the verifier against production after schema/input deployment.

Then prove the actual scoring path with a bounded replay or fresh source run:

- At least one candidate receives `pricing_maturity = 'market_comp'`.
- Candidate has usable `retail_comp_price_estimate`, `retail_comp_count`, and `retail_comp_confidence`.
- `pricing_source` reflects the real evidence path, not proxy fallback.
- No row is saved with missing VIN/mileage.
- No hot alert is sent from proxy-only pricing unless the existing alert policy explicitly allows it.

### 5. Continuity

After proof:

- Update `brains/dealerscope-brain/CONTEXT_BRIDGE.md` with the live status.
- Run wiki compile/lint.
- Import/doctor/search GBrain.
- Run the brain/UI sync healthcheck.
- Record the proof in `memory/2026-06-02.md`.

## Verification Commands

```bash
PYTHON_BIN=.venv-test/bin/python scripts/run_backend_tests.sh -q tests/test_internal_pipeline_truth.py tests/test_business_rules.py tests/test_alert_send_gate.py
git diff --check
```

Add once the verifier exists:

```bash
python3 scripts/verify_pricing_substrate.py
```

## Acceptance Criteria

- `market_prices` has an explicit migration and verifier.
- `pricing_substrate.ready_for_market_comp_pricing` is false when evidence is missing, empty, stale, or unproven.
- `pricing_substrate.ready_for_market_comp_pricing` is true only with usable market/dealer-sales evidence.
- A live bounded proof shows at least one clean candidate can use market-comp pricing.
- No proxy-only row is promoted by seed/import logic.
- Brain/GBrain/Obsidian continuity reflects the new pricing-truth state.
