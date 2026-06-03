# Devin Competitive Pricing Intelligence Design

## Status

Approved direction for Paperclip task `DEA-53`.

This document is a design/readiness spec only. It does not authorize implementation until the implementation plan is written and reviewed.

## Goal

Build a governed completed-sale evidence path so DealerScope can use real comparable auction-sale data for pricing when enough trustworthy comps exist, without weakening the existing proxy-pricing, alert, or condition gates.

## Current Context

DealerScope already has the correct downstream pricing shape:

- `public.market_prices` exists as the retail comp cache contract.
- `backend/ingest/retail_comps.py` reads `market_prices` first, then legacy `dealer_sales`, then returns an empty result so proxy pricing remains blocked by existing gates.
- `backend/ingest/score.py` already sets `pricing_maturity = "market_comp"` when usable retail comps are present and `pricing_maturity = "proxy"` when they are not.
- `scripts/verify_pricing_substrate.py` and `/api/internal/pipeline-truth` already prove whether market pricing evidence is usable.

The missing part is not another scoring shortcut. The missing part is durable, sale-level evidence that can be safely rolled into `market_prices`.

## Recommended Approach

Use a two-layer evidence model:

1. `competitor_sales` stores raw completed-sale evidence collected by Devin.
2. A deterministic rollup/verifier promotes only qualifying sale clusters into `market_prices`.

Devin is an upstream evidence producer, not a pricing authority. DealerScope remains responsible for validation, dedupe, rollup, and scoring integration.

## Non-Goals

- Do not write Devin output directly into opportunities.
- Do not loosen `pricing_maturity_proxy`, hot-alert, condition, VIN, mileage, or margin gates.
- Do not treat active retail listings as completed-sale evidence.
- Do not use Manheim. Access is hard blocked.
- Do not add paid external APIs.
- Do not replace `RetailCompService` or `score_deal` with a parallel Devin pricing path.
- Do not make the first implementation cover every vehicle class; start with F-150, F-250, and Silverado 1500.

## Data Model

### `competitor_sales`

Create a new Supabase table for raw completed-sale records:

- `id uuid primary key`
- `source_site text not null`
- `source_listing_id text`
- `source_url text not null`
- `source_run_id text not null`
- `devin_run_id text`
- `sold_price numeric not null`
- `auction_end_date timestamptz not null`
- `captured_at timestamptz not null`
- `year integer not null`
- `make text not null`
- `model text not null`
- `trim text`
- `vin text`
- `mileage integer`
- `condition_notes text`
- `location_city text`
- `location_state text`
- `raw_data jsonb not null default '{}'::jsonb`
- `quality_flags jsonb not null default '[]'::jsonb`
- `created_at timestamptz not null default timezone('utc', now())`
- `updated_at timestamptz not null default timezone('utc', now())`

Use a unique index over the stable source identity:

- Prefer `(source_site, source_listing_id)` when `source_listing_id` exists.
- Also guard `(source_site, source_url)` so duplicate URL captures cannot create duplicate comps.
- Keep VIN as evidence, not as the only unique key, because some legitimate auction records may omit VIN or reuse ambiguous source text.

### Rollup Into `market_prices`

Do not change the `market_prices` contract unless implementation proves a required column is missing. The rollup should produce rows using the existing fields:

- `year`
- `make`
- `model`
- `state`
- `avg_price`
- `low_price`
- `high_price`
- `sample_size`
- `source`
- `source_run_id`
- `source_url`
- `confidence_notes`
- `metadata`
- `last_updated`
- `expires_at`

Rollup source should be `competitor_completed_sales`.

`metadata` should include:

- `competitor_sales_ids`
- `source_sites`
- `vehicle_class`
- `price_method = "median_completed_sales"`
- `year_window`
- `mileage_window`
- `sale_date_range`
- `evidence_count`

## Matching Rules

The pricing query should match the existing business target:

- same normalized make/model
- year within `+/- 2`
- mileage within `+/- 25,000` when both target and comp mileage exist
- completed sale date within the configured freshness window
- positive sold price
- completed/sold status only

The first vehicle classes are:

- Ford F-150
- Ford F-250
- Chevrolet Silverado 1500

Model normalization must be explicit. For example, `F150`, `F-150`, and `F 150` should normalize to one canonical model token for matching. The same applies to `Silverado`, `Silverado 1500`, and `1500` only when make is Chevrolet.

## Quality Gates

A competitor sale is eligible for rollup only when all of these are true:

- `sold_price > 0`
- `auction_end_date` is present
- `source_url` is an HTTP(S) URL
- source identity is present through `source_listing_id` or stable `source_url`
- `year`, `make`, and `model` normalize cleanly
- `mileage` is positive when present
- `source_site` is one of `govdeals`, `publicsurplus`, or `govplanet`
- record is completed/sold, not active listing evidence

A rollup is usable for `market_prices` only when:

- at least 5 eligible sale records match the vehicle class/window
- price spread is not obviously malformed
- `low_price <= avg_price <= high_price`
- `source_run_id` identifies the rollup batch
- `confidence_notes` clearly states completed-sale evidence and source coverage

If fewer than 5 comps exist, preserve the raw `competitor_sales` rows but do not write a usable `market_prices` row.

## Pricing Integration

The downstream integration should stay mostly unchanged:

1. Devin captures completed-sale evidence.
2. DealerScope stores it in `competitor_sales`.
3. A rollup script writes provenance-backed rows into `market_prices`.
4. `RetailCompService` reads `market_prices`.
5. `score_deal` receives `retail_comp_price_estimate`, `retail_comp_count`, `retail_comp_confidence`, and `pricing_source`.
6. Existing scoring marks rows as `market_comp` only when comps are present.
7. Existing alert/save gates continue to reject proxy-priced rows.

The only scoring-facing addition should be a transparent divergence flag when a proxy estimate and completed-sale comp estimate differ by more than 15%.

The divergence flag should be informational at first. It should not automatically accept, reject, or alert a deal until live evidence proves the right operational behavior.

## Devin Handoff

Devin should receive the verbatim prompt already tracked in Paperclip task `DEA-53`, plus an implementation clarification:

Devin should return structured completed-sale JSON that conforms to the `competitor_sales` evidence shape. Devin should not directly mutate `market_prices`, `opportunities`, or scoring code.

The expected Devin output for each source run is:

```json
{
  "source_site": "govdeals",
  "source_run_id": "devin-2026-06-02-f150-govdeals",
  "captured_at": "2026-06-02T00:00:00Z",
  "records": [
    {
      "source_listing_id": "12345",
      "source_url": "https://www.govdeals.com/asset/123/456",
      "sold_price": 18500,
      "auction_end_date": "2026-05-30T18:00:00Z",
      "year": 2022,
      "make": "Ford",
      "model": "F-150",
      "trim": "XL",
      "vin": "1FTFW1E50NFA12345",
      "mileage": 42100,
      "condition_notes": "Runs and drives",
      "location_city": "Phoenix",
      "location_state": "AZ",
      "raw_data": {}
    }
  ]
}
```

## Error Handling

Importer behavior:

- Reject invalid records with explicit reasons.
- Insert valid records idempotently.
- Print summary counts: `valid`, `inserted`, `duplicate`, `rejected`, and rejection reasons.
- Never fail the entire batch because one record is bad.
- Fail the run if all records are invalid.

Rollup behavior:

- No-op when fewer than 5 eligible comps exist.
- No-op when source evidence is stale or malformed.
- Print a dry-run preview before applying by default.
- Apply only with an explicit flag.
- Use Supabase REST service-role write path if direct DB credentials are stale.

## Observability

Add read-only proof surfaces before relying on this operationally:

- Import summary for `competitor_sales`.
- Rollup summary for `market_prices`.
- Pipeline truth counts:
  - `competitor_sales_rows`
  - `competitor_sales_usable_rows`
  - `competitor_sales_by_source`
  - `market_prices_from_competitor_sales_rows`
  - `pricing_comp_divergence_samples`

The production proof should show which rows are `live-confirmed`, `live-improved but pending`, `locally validated only`, or `hypothesis`.

## Testing Strategy

Use TDD for implementation.

Required test coverage:

- competitor sale validation accepts valid completed-sale evidence
- validation rejects active-listing evidence, missing sold price, missing URL, missing auction end date, bad vehicle identity, and duplicate source identity
- importer inserts valid rows and skips duplicates
- importer preserves rejected-row reasons
- rollup requires at least 5 eligible comps
- rollup computes median/low/high and writes a `market_prices` row with provenance metadata
- rollup does not write `market_prices` from proxy or active-listing evidence
- `RetailCompService` can consume the resulting `market_prices` row without code-path changes
- scoring emits market-comp maturity only through existing comp fields
- divergence flag appears when proxy and completed-sale comp estimate differ by more than 15%
- pipeline truth reports competitor-sales readiness counts

## Live Proof Plan

Implementation is not complete until all of this is proven:

1. Local tests pass.
2. `py_compile` passes for changed Python files.
3. `git diff --check` passes.
4. GitHub DealerScope CI passes.
5. Cursor review passes.
6. Production schema is applied.
7. A governed Devin/sample evidence import inserts or previews completed-sale evidence.
8. A governed rollup creates at least one `market_prices` row only when at least 5 comps qualify.
9. A live pricing proof shows `RetailCompService` returns `pricing_source = "retail_market_cache"` or the chosen completed-sale source for one target vehicle class.
10. A live scoring proof shows no alert gate was loosened and no proxy-only row was promoted.
11. Brain/bridge/memory continuity is updated and wiki compile/lint is run.

## Open Questions For Implementation Planning

These do not block the design, but the implementation plan must answer them:

- Whether `competitor_sales` should be queried directly by `RetailCompService` or only through `market_prices`. The recommended first release is rollup-only through `market_prices`.
- Whether the first Devin run should be live browser automation or a governed sample JSON import. The recommended first release is sample/import contract first, then Devin live source runs.
- Whether divergence flags live in `score_provenance`, `risk_flags`, or a dedicated pricing field. The recommended first release is `score_provenance` plus pipeline-truth samples.

## Acceptance Criteria

- Paperclip task `DEA-53` has a design-backed implementation path.
- Raw Devin completed-sale evidence is stored separately from rolled-up pricing cache rows.
- Existing pricing maturity and alert gates remain intact.
- Completed-sale comps can improve pricing truth only through validated evidence and deterministic rollup.
- Live proof labels are explicit and no completion claim is made without production evidence.
