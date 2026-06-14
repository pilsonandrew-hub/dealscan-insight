# Pricing Substrate Live Recovery Design

## Purpose

DealerScope now exposes market-data quality truthfully. Current live proof shows the next hardening problem: pricing quality is degraded because active high-score rows still rely on fallback pricing and stale evidence.

This lane must close the production pricing-evidence loop without weakening scoring or alert gates. The goal is to convert clean active pricing gaps into governed evidence acquisition and safe market-pricing refreshes, while preserving the rule that proxy-only pricing cannot masquerade as market-comp evidence.

## Current Truth

The prior lane is live-confirmed closed:

- PR #308 merged into main at `724d0956a5fef5ac0058806e9141cd8979a7f181`.
- Fresh Supabase Live Inspection run `27488239013` succeeded on main.
- `market_data_quality.status` reported `degraded`, with `fallback_share=1.0`, `live_share=0.0`, and `latest_pricing_age_hours=116.84`.
- Degraded reasons were `manheim_live_share_below_threshold` and `pricing_evidence_stale`.

Fresh read-only proof on current main sharpened the gap:

- Pricing Source Skip Proof run `27488554184` succeeded on main and reported `pricing_proxy_source_candidates=54`, including `42` `active_clean_pricing_gap` rows, `1` `dirty_source_row`, and `11` `expired_pricing_gap` rows.
- Pricing Coverage Gap Proof run `27488554187` succeeded on main and reported `clean_proxy_candidates=42`.
- The clean active coverage candidates were delivery pricing skips. Almost all had `market=0/0`, `dealer_sales=0/0`, `history=0/0`, and `evidence=blocked_no_internal_comp_evidence`.
- One Ford F-150 row had `history=2/2`, but that is still below the existing seed threshold and must remain `insufficient_internal_history`.
- Competitor Sales Scraper run `27482877857` succeeded earlier, but wrote only one row. That proves the scraper can write, not that current production coverage is adequate.

This is a product-hardening lane, not an alert defect and not a scoring defect. The live system is now honest about weak pricing evidence; the next job is to make the evidence pipeline operationally useful.

## Scope

Build a governed pricing substrate recovery loop around existing proof surfaces and evidence tables.

The loop must answer:

- Which active clean listings are blocked only because trusted market pricing is missing?
- Which year/make/model/state groups have no market-prices, dealer-sales, competitor-sales, or seedable internal history?
- Which groups are repeated enough to justify evidence acquisition first?
- Which groups have enough trusted completed-sale evidence to refresh `market_prices` safely?
- Which groups remain blocked because evidence is absent, stale, sparse, or dirty?
- Did a refresh change live `market_data_quality` without exposing private listing details?

The first implementation should be narrow and proof-first:

1. Improve the read-only coverage proof into an actionable grouped recovery report.
2. Add a dry-run promotion path from trusted completed-sale evidence into `market_prices` only when evidence thresholds are met.
3. Add workflow proof that can run read-only by default and apply only with explicit confirmation.
4. Prove post-merge that live `market_data_quality` and pricing-gap reports changed truthfully.

## Non-Goals

- No scoring threshold relaxation.
- No alert eligibility relaxation.
- No proxy-to-market-comp promotion.
- No blind seed from one or two historical rows.
- No public UI.
- No raw listing, VIN, URL, title, or payload output in operator aggregate proof.
- No claim that a successful scrape means coverage is healthy.
- No attempt to fake live Manheim availability.

## Approaches Considered

### Approach 1: Loosen Pricing Gates

Allow proxy-priced rows with clean identity or high DOS to pass market-comp gates.

Rejected. This would make DealerScope less truthful. It would turn the new degraded signal into a bypass rather than fixing the missing evidence.

### Approach 2: Blind Market-Price Seeding From Weak History

Lower the existing internal-history seed threshold and insert `market_prices` rows from sparse opportunity history.

Rejected. Current live proof shows one candidate with only `history=2/2`. That is not enough to support a market-price row. The threshold exists for a reason and should not be reduced in this lane.

### Approach 3: Evidence-Acquisition And Safe Refresh Loop

Group clean active pricing gaps, classify coverage by evidence source, generate operator-safe evidence requests for uncovered groups, and allow `market_prices` refresh only from trusted completed-sale evidence that meets minimum sample and freshness rules.

Selected. This keeps truth gates intact and turns the live degraded state into a governed recovery mechanism.

## Selected Design

Add a pricing substrate recovery contract with three surfaces:

1. **Read-only grouped gap proof**
   - Extend `scripts/report_pricing_coverage_gaps.py` or add a focused helper that groups active clean pricing gaps by normalized `year`, `make`, `model`, `state`, and source family.
   - Report aggregate counts, current evidence status, and recommended next action.
   - Keep candidate-level detail available for debugging, but default workflow output should emphasize grouped aggregate recovery.

2. **Trusted evidence promotion dry-run**
   - Add a script path that reads trusted completed-sale evidence and previews market-price rows that would be inserted or refreshed.
   - Candidate evidence can come from `competitor_sales`, `dealer_sales`, or already-governed external comp evidence.
   - The script must require minimum sample count, positive price bounds, freshness, source tag, source run id, and TTL.
   - Apply mode must require an explicit confirmation string and must write provenance fields.

3. **Live proof gates**
   - Add or update a workflow that runs read-only by default.
   - The workflow must print grouped recovery counts, not private listing details.
   - Apply mode must be manually dispatched with confirmation.
   - After any apply, run Supabase Live Inspection and Pricing Coverage Gap Proof again.

## Recovery Status Model

Use stable status keys:

- `covered_by_market_prices`: usable market-price row exists and is not expired.
- `covered_by_dealer_sales`: enough recent dealer-sales evidence exists.
- `covered_by_competitor_sales`: enough trusted completed-sale competitor evidence exists.
- `seedable_from_internal_history`: existing opportunity history meets the configured seed threshold.
- `insufficient_internal_history`: history exists but is below threshold.
- `insufficient_competitor_sales`: completed-sale rows exist but are below threshold or stale.
- `blocked_no_internal_comp_evidence`: no trusted evidence source exists.
- `dirty_source_row`: row lacks clean identity or required vehicle fields.
- `expired_pricing_gap`: auction/listing is no longer active enough to justify recovery.

## Recommended Actions

Each grouped gap should produce one recommended action:

- `refresh_market_prices_from_competitor_sales`
- `refresh_market_prices_from_dealer_sales`
- `request_completed_sales_evidence`
- `wait_for_more_internal_history`
- `ignore_dirty_source_row`
- `ignore_expired_listing`

The action is advisory until an apply workflow is explicitly dispatched.

## Promotion Rules

Promotion into `market_prices` must require:

- At least the configured minimum completed-sale sample count. Initial default: `5`.
- Positive average, low, and high prices.
- A bounded price distribution that rejects impossible or non-finite values.
- A fresh evidence window. Initial default: completed sale within `365` days and inserted market-price TTL of `14` to `30` days.
- Normalized year/make/model and optional state.
- Source provenance: `source`, `source_run_id`, `confidence_notes`, `metadata`, `last_updated`, and `expires_at`.
- Idempotent upsert behavior or duplicate-safe insert behavior.

Promotion must not use active auction asking prices, current bids, proxy MMR, titles, or raw payloads as pricing evidence.

## Data Flow

1. Read clean active pricing gaps from `ingest_delivery_log`, `sonar_listings`, and recent `opportunities` through existing report helpers.
2. Normalize each gap into a grouped recovery key.
3. Query evidence tables for each group:
   - `market_prices`
   - `dealer_sales`
   - `competitor_sales`
   - eligible internal opportunity history
4. Classify each group with the recovery status model.
5. Print aggregate grouped proof with counts and recommended action.
6. For groups with enough trusted evidence, preview market-price refresh rows.
7. In explicit apply mode, upsert only those rows and write provenance.
8. Run live inspection and coverage-gap proof to prove whether degraded market-data status improved.

## Truth Boundaries

The recovery loop proves pricing-evidence coverage and freshness. It does not prove:

- A specific vehicle is safe to buy.
- A live Manheim provider is available.
- Every external source has complete sold-listing coverage.
- A proxy MMR is correct.

If evidence is absent, the system must say so. If evidence is sparse, the system must keep the row blocked. If evidence is fresh but narrow, the system must expose that limitation with counts and source tags.

## Privacy And Sanitization

Default workflow output must be aggregate-only:

- Allowed: counts, status keys, grouped year/make/model/state, source family, sample sizes, freshness, source tags, recommended action.
- Disallowed: VINs, listing URLs, titles, raw payloads, descriptions, user data, tokens, and credentials.

Candidate-level debug output can remain in local scripts when explicitly requested, but CI proof should default to sanitized grouped output.

## Testing

Use test-driven development.

Required tests:

- Grouped pricing recovery report classifies active clean pricing gaps by evidence availability.
- Groups with no evidence return `blocked_no_internal_comp_evidence` and `request_completed_sales_evidence`.
- Groups with insufficient history stay blocked and do not become seedable.
- Groups with enough competitor-sales evidence preview a market-price refresh row.
- Promotion rejects rows with sparse samples, zero prices, stale evidence, or missing provenance.
- Apply mode requires explicit confirmation.
- Workflow tests prove read-only default and confirmation-gated apply mode.
- Sanitization tests prove default workflow output does not expose VINs, listing URLs, titles, raw payloads, user data, or secrets.

## Verification Gates

Local gates:

- Focused pricing recovery tests pass.
- Existing pricing coverage report tests pass.
- Competitor pricing and scraper runner tests pass.
- Internal pipeline truth and Supabase live inspection tests pass.
- Full test suite passes before PR.

GitHub gates:

- PR checks pass.
- Cursor/Bugbot review is clean or all findings are fixed with RED/GREEN regression tests.
- Read-only pricing recovery workflow succeeds on PR or main.

Live gates:

- Railway health remains OK after merge.
- Supabase Live Inspection succeeds on current main.
- Pricing Coverage Gap Proof succeeds on current main.
- If apply mode is used, post-apply proof shows the exact groups changed and `market_data_quality` changes only according to real inserted evidence.

## Acceptance Criteria

This lane is complete only when:

- The design and implementation preserve pricing truth gates.
- Operators can see grouped active pricing coverage gaps without private listing leakage.
- Safe refresh candidates are previewed before any write.
- Writes are confirmation-gated, provenance-rich, and threshold-bound.
- Fresh live proof shows whether the degraded pricing state improved or remains blocked by missing evidence.

If no group has enough trusted evidence to refresh, the lane can still be valuable, but it must be classified honestly as an evidence-acquisition hardening lane, not as pricing-quality recovery.
