# Seller Recovery Audit Hardening Design

## Purpose

The current seller recovery audit is live-confirmed: it exposes sanitized internal evidence from source health, delivery logs, parse events, opportunity quality, and source-mirror bidder depth. The next step is not to rebuild it. The next step is to harden the existing internal JSON contract so it can support operator decisions and later investor/demo reporting without inventing unsupported claims.

This pass builds the governed data contract first. A human-readable report surface can come later, after the stronger endpoint is live-proved.

## Scope

Enhance `GET /api/internal/seller-recovery-audit` with:

- Ranked recovery candidates with deterministic `recovery_score`.
- Per-candidate evidence details that explain exactly why the candidate ranked.
- Reason rollups across all candidates.
- Source-level recovery rollups across candidates and observability surfaces.
- Explicit truth-boundary metadata for every new section.

Keep the endpoint internal, read-only, and sanitized. Do not add a public UI. Do not weaken pricing, margin, maturity, or capital-risk gates to make the report look cleaner.

## Non-Goals

- No municipality-facing SaaS workflow.
- No investor deck/report generation in this pass.
- No market index claims.
- No claims about seller behavior or auction strategy beyond fields DealerScope can prove.
- No raw VINs, full listing URLs, descriptions, raw payloads, user data, or tokens.
- No new persistence tables unless implementation proves the endpoint cannot be deterministic without them.

## Existing Evidence Surfaces

The hardened contract may use only current governed surfaces:

- `source_health_daily`
- `ingest_delivery_log`
- `parse_events`
- `opportunities`
- `sonar_listings`

Bidder depth may come from `opportunities.bidder_count` or `sonar_listings.bidder_count`. If bidder evidence exists only on the source mirror, the output must say `evidence_surface="source_mirror"`. It must not pretend an opportunity row has bidder evidence when opportunity creation was blocked by a valid gate.

Photo quality may use `opportunities.photo_count`, `risk_flags`, and raw-photo evidence summaries already proven by live inspection. If only a missing-photo risk flag exists, the output must say that the exact photo count is not proven.

## Candidate Ranking

Each value-leak candidate gets:

```json
{
  "recovery_score": 87.5,
  "recovery_tier": "high",
  "score_components": {
    "value_gap": 40.0,
    "listing_quality": 25.0,
    "evidence_strength": 17.5,
    "source_health": 5.0
  }
}
```

`recovery_score` is deterministic and bounded from 0 to 100.

Score inputs:

- `gross_margin` and `bid_headroom` drive `value_gap`.
- Missing VIN, missing mileage, missing auction end, condition uncertainty, proxy pricing, missing photos, zero photo count, and low photo count drive `listing_quality`.
- Governed photo count, source-mirror bidder count, opportunity bidder count, market-comp pricing maturity, and non-proxy pricing drive `evidence_strength`.
- Recent failed runs, skipped counts, and parse-event rejection clusters drive `source_health`.

The score is not a revenue promise. It is a prioritization score for internal recovery review.

## Candidate Output

Each candidate keeps the current sanitized fields and adds:

- `recovery_score`
- `recovery_tier`: `high`, `medium`, or `low`
- `score_components`
- `evidence`: a compact object showing which governed fields were present
- `truth_boundary`: a short string stating what the candidate does and does not prove

Candidate output may include:

- `id`
- `source_site`
- `year`
- `make`
- `model`
- `dos_score`
- `gross_margin`
- `bid_headroom`
- `pricing_maturity`
- `recovery_reasons`

Candidate output must not include:

- VIN
- listing URL
- description
- raw payload
- seller-private fields
- tokens or credentials

## Rollups

Add a `recovery_rollups` section:

```json
{
  "reason_counts": {
    "missing_photos_flag": 5,
    "low_photo_count": 6
  },
  "tier_counts": {
    "high": 2,
    "medium": 4,
    "low": 0
  },
  "source_counts": {
    "allsurplus": 6
  },
  "top_sources_by_score": [
    {
      "source_site": "allsurplus",
      "candidate_count": 6,
      "average_recovery_score": 82.4,
      "top_reasons": ["missing_photos_flag", "low_photo_count"]
    }
  ]
}
```

Rollups must be derived from the same sanitized candidates returned by the endpoint. They must not query broader private fields or raw payloads.

## Source Health Section

Keep the existing `source_health` list, and add a compact `source_health_summary`:

- total observed sources
- sources with recent failed runs
- total processed runs
- total failed runs
- total saved count
- total skipped count
- total parse-event count
- top skipped statuses

This section is operational context, not seller blame.

## Truth Boundaries

The top-level response must include `truth_boundaries`:

```json
{
  "candidate_ranking": "Internal deterministic prioritization, not a recovery guarantee.",
  "bidder_depth": "Uses governed opportunity bidder_count when present; otherwise uses governed source mirror bidder_count when present.",
  "photo_quality": "Uses governed photo_count and missing_photos risk flags; does not infer photo quality from private raw payloads.",
  "source_health": "Aggregates run and parse-event observability; does not prove seller intent."
}
```

Any unavailable dimension remains in `summary.unavailable_dimensions` and `unsupported_dimensions`.

## Error Handling

The current per-section degradation model remains:

- If `opportunities` is unreadable, status is `degraded` because candidates cannot be computed.
- If `source_health_daily`, `parse_events`, `ingest_delivery_log`, or `sonar_listings` is unreadable, keep the candidate section available and mark the affected section unavailable.
- If a score component cannot be computed because a field is absent, assign that component `0` and explain the missing evidence through `truth_boundaries` or `unsupported_dimensions`.

No section may silently disappear.

## Testing

Use test-driven development.

Required focused tests:

- Candidate ranking is deterministic and sorted by `recovery_score`.
- Score components are bounded and sum to the rounded score.
- High/medium/low tiers are assigned from deterministic thresholds.
- Candidate evidence excludes sensitive fields.
- Reason rollups match returned candidates.
- Source rollups match returned candidates and source-health rows.
- Source-mirror bidder depth contributes to evidence strength without claiming opportunity-level bidder evidence.
- Degraded source-health or source-listing sections do not break candidate output.
- Live inspection includes the new hardening sections without printing sensitive fields.

Completion requires:

- Focused tests pass.
- Full local suite passes.
- PR checks pass.
- Cursor review passes or all findings are addressed with evidence.
- Deployment succeeds.
- Fresh production live inspection proves the hardened sections on current main.

## Implementation Boundary

Implementation should stay close to the existing audit:

- `webapp/routers/internal.py` for endpoint scoring, rollups, and response contract.
- `scripts/supabase_live_inspection.py` for read-only production proof.
- `tests/test_internal_pipeline_truth.py` for endpoint contract tests.
- `tests/test_supabase_live_inspection.py` for live-inspection proof tests.

If helper logic grows too large, split only the pure seller recovery scoring helpers into a small module under an existing backend/webapp boundary. Do not do broad refactors.
