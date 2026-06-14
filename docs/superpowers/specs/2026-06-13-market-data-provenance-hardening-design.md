# Market-Data Provenance Hardening Design

## Purpose

DealerScope already blocks proxy-pricing rows from capital-ready scoring paths, and current main is green. The remaining Phase 2 gap is visibility: a healthy ingest or alert run can still make the pricing substrate look normal while live market evidence is absent, stale, sparse, or proxy-heavy.

This lane makes pricing evidence quality explicit across internal verification and live-inspection proof. It is a product-hardening lane, not a live red incident. The goal is to prevent silent market-data quality erosion from hiding behind green workflow status.

## Current Truth

Current code already stores and reports several pricing fields:

- `pricing_maturity`
- `pricing_source`
- `pricing_updated_at`
- `retail_comp_count`
- `retail_comp_confidence`
- `mmr_confidence_proxy`
- `manheim_source_status`
- `manheim_updated_at`
- `pricing_trust_blocked`
- `pricing_trust_reason`

`GET /api/internal/pipeline-truth` currently reports pricing-maturity counts and a `pricing_substrate` section for `market_prices` and `dealer_sales`. `scripts/supabase_live_inspection.py` reports recent opportunity truth and seller recovery audit truth. Those surfaces are useful but incomplete for P2.3 because they do not present one operator-grade market-data status with source status, freshness age, fallback share, degraded reasons, and explicit proof boundaries.

## Scope

Add a governed market-data quality contract to the internal truth and live-inspection proof surfaces.

The contract must answer:

- Is current pricing evidence healthy, degraded, unavailable, or unknown?
- What share of sampled rows uses proxy pricing?
- What share of high-score sampled rows uses proxy pricing?
- How fresh is the latest market-pricing evidence?
- Are live Manheim values, market comps, retail comps, or model proxies driving current rows?
- Which degraded reasons are present?
- Which fields are missing from the schema or sample, if any?

The first implementation target is proof and observability, not new pricing behavior. Alert and score gates should not be relaxed in this lane.

## Non-Goals

- No new bidding behavior.
- No new alert eligibility rule in this pass unless the design review proves current alert gating has a live defect.
- No public UI.
- No seller-facing report copy.
- No market index or benchmark claims.
- No attempt to fabricate live Manheim evidence when the provider is absent.
- No schema migration unless current persisted fields are insufficient for truthful proof.

## Approaches Considered

### Approach 1: Endpoint-Only Summary

Add a compact `market_data_quality` section only to `GET /api/internal/pipeline-truth`.

This is the smallest change, but it leaves the production proof path weaker than the endpoint. It would not satisfy the roadmap requirement that verification output and health bundles expose degraded market-data states.

### Approach 2: Score-Time Rewrite

Refactor scoring so every opportunity gets a normalized pricing-provenance object at write time.

This is directionally strong, but too broad for the next safe pass. It risks changing scoring behavior while the immediate gap is proof visibility. It may be a later follow-up if the proof contract exposes missing persisted fields.

### Approach 3: Shared Read-Only Quality Contract

Create a deterministic market-data quality summary from existing persisted fields, expose it in internal pipeline truth, and mirror it in Supabase live inspection.

This is the recommended approach. It is safest, testable, and aligned with current hardening practice: first prove what the system knows, what it does not know, and whether a degradation state is visible to operators.

## Selected Design

Add a `market_data_quality` section to both:

- `GET /api/internal/pipeline-truth`
- `scripts/supabase_live_inspection.py` truth audit output

The section is computed from sanitized opportunity rows and pricing-substrate rows only. It must not print titles, VINs, listing URLs, raw payloads, user data, tokens, or descriptions.

Example shape:

```json
{
  "status": "degraded",
  "sample_size": 1000,
  "active_sample_size": 42,
  "high_score_sample_size": 7,
  "pricing_maturity_counts": {
    "market_comp": 30,
    "proxy": 12
  },
  "high_score_pricing_maturity_counts": {
    "market_comp": 5,
    "proxy": 2
  },
  "manheim_source_status_counts": {
    "live": 3,
    "fallback": 20,
    "unavailable": 19
  },
  "fallback_share": 0.31,
  "proxy_share": 0.29,
  "high_score_proxy_share": 0.29,
  "latest_pricing_updated_at": "2026-06-14T03:00:00+00:00",
  "latest_pricing_age_hours": 0.7,
  "freshness": {
    "status": "fresh",
    "threshold_hours": 24
  },
  "degraded_reasons": [
    "proxy_pricing_share_above_threshold",
    "manheim_live_share_below_threshold"
  ],
  "unavailable_dimensions": [],
  "truth_boundary": "Sanitized aggregate pricing-evidence quality from persisted rows; does not prove external provider uptime unless provider status is stored on sampled rows."
}
```

## Status Rules

`market_data_quality.status` is deterministic:

- `healthy`: sample exists, proxy share is below threshold, latest pricing evidence is fresh, and at least one non-proxy pricing source is present.
- `degraded`: sample exists but proxy/fallback share is high, live source share is weak, latest pricing evidence is stale, or retail comps are sparse.
- `unavailable`: no sampled active opportunities or no pricing fields are available to compute quality.
- `unknown`: the query itself is unavailable or schema fields required for the contract are missing.

Initial thresholds:

- `proxy_share > 0.25` degrades.
- `high_score_proxy_share > 0` degrades because high-score proxy rows are exactly where operator trust matters most.
- latest `pricing_updated_at` or `manheim_updated_at` older than 24 hours degrades.
- `retail_comp_count < 2` on all sampled non-live rows degrades as sparse comp evidence.
- `manheim_source_status` all `fallback` or `unavailable` degrades when the field exists.

These thresholds are proof thresholds, not investment rules. They make weakness visible. They do not authorize or reject a bid.

## Degraded Reasons

Use stable reason keys:

- `no_active_pricing_sample`
- `pricing_fields_missing`
- `proxy_pricing_share_above_threshold`
- `high_score_proxy_pricing_present`
- `pricing_evidence_stale`
- `retail_comps_sparse`
- `manheim_live_share_below_threshold`
- `market_prices_unusable`
- `dealer_sales_sparse`

Reason keys must be counted and testable. Avoid prose-only degradation.

## Data Flow

Internal endpoint:

1. Query recent opportunities using existing pipeline-truth row selection.
2. Reuse `pricing_substrate` from `_pricing_substrate_truth()`.
3. Build `market_data_quality` from active rows, high-score rows, and pricing substrate.
4. Return it beside `pricing_substrate` and `opportunities`.

Live inspection:

1. Query recent opportunities with the same pricing fields when columns exist.
2. Query current pricing substrate tables only when available.
3. Build the same sanitized aggregate contract.
4. Print it under `market_data_quality` in the read-only truth audit.

## Truth Boundaries

Top-level or section-level boundaries must state:

- The status is based on sampled persisted rows, not a real-time provider ping.
- A fallback or proxy-heavy state is not a workflow failure by itself.
- A healthy state does not guarantee a specific deal is safe to buy.
- Missing schema fields must be reported as unavailable or unknown, not silently ignored.

## Privacy And Sanitization

The new contract is aggregate only. It must not output:

- VINs
- listing URLs
- titles
- raw payloads
- seller-private data
- user data
- tokens or credentials

Allowed output:

- counts
- shares
- timestamps
- age in hours
- stable reason keys
- compact source-status counts
- truth-boundary text

## Error Handling

The endpoint must preserve the current truth endpoint behavior:

- If opportunity rows are available but optional pricing-substrate tables are not, return `status="degraded"` or `status="unknown"` with reasons, not HTTP failure.
- If opportunity rows are unavailable, preserve the existing endpoint failure/degraded behavior and do not invent market-data status.
- If a column is absent in live inspection, include it in `unavailable_dimensions`.
- If timestamp parsing fails, count `pricing_evidence_stale` only when no valid fresh timestamp exists.

No section may silently disappear.

## Testing

Use test-driven development.

Required RED/GREEN tests:

- Internal pipeline truth reports `market_data_quality` with status, counts, shares, freshness, degraded reasons, unavailable dimensions, and truth boundary.
- Proxy-heavy active samples become `degraded`.
- Any high-score proxy-pricing sample adds `high_score_proxy_pricing_present`.
- Fresh market-comp or live-market evidence can produce `healthy` when proxy share is below threshold.
- Missing pricing fields produce `unknown` or unavailable dimensions without exposing raw rows.
- Live inspection mirrors the same contract and sanitization.
- Pricing-substrate unusable rows add `market_prices_unusable` without crashing.

Completion requires:

- Focused RED tests fail for absent contract.
- Focused GREEN tests pass.
- Adjacent internal/live-inspection tests pass.
- Full local suite passes.
- PR checks pass.
- Cursor/Bugbot/Codex review findings are resolved or rejected with evidence.
- Deployment succeeds.
- Fresh production live inspection on current main prints the new `market_data_quality` contract.

## Implementation Boundary

Primary files:

- `webapp/routers/internal.py`
- `scripts/supabase_live_inspection.py`
- `tests/test_internal_pipeline_truth.py`
- `tests/test_supabase_live_inspection.py`

Avoid broad scoring refactors in this pass. If duplicate helper logic becomes large, extract a small pure helper only after tests prove the contract and only inside an existing backend/webapp boundary.

## Exit Criteria

This lane is not complete until the proof surface is live-confirmed:

- PR merged to `main`.
- Main checks green on the merge commit.
- Railway health OK after deployment.
- Fresh Supabase Live Inspection run succeeds on the merge commit.
- Live inspection output includes `market_data_quality.status`, degraded reason counts, proxy/fallback shares, freshness age, unavailable dimensions, and truth boundary.

Until then, classify the lane as product-hardening in progress.
