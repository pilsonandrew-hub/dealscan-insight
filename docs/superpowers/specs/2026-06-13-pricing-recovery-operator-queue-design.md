# Pricing Recovery Operator Queue Design

## Purpose

Pricing substrate live recovery is live-confirmed, but it exposed the next operating gap: DealerScope can now identify pricing recovery work, yet the work exists only as transient proof output.

The new lane is to turn live pricing recovery groups into a governed operator queue. The queue must make missing pricing evidence assignable, statused, inspectable, and auditable without weakening scoring gates or turning proxy pricing into market-comp truth.

This is product hardening, not a red incident. The live system is honest; the next step is to make the recovery work durable enough for real operation.

## Current Truth

The previous lane is live-confirmed:

- PR #309 merged pricing substrate live recovery at `13fb64d0914b5301e5c9159829b0e46def03d64a`.
- Post-merge live proof exposed one real proof-output sanitizer gap.
- PR #310 fixed that sanitizer gap and merged at `c6c3643e4266f4d948a55c75e92c5b870829d559`.
- Current main checks on `c6c3643e4266f4d948a55c75e92c5b870829d559` are green.
- Pricing Coverage Gap Proof run `27490986854` passed on current main.
- Supabase Live Inspection run `27490986860` passed on current main.
- Open PRs and open issues were empty at lane selection time.

The current live proof still reports degraded pricing quality:

- `market_data_quality.status=degraded`
- `fallback_share=1.0`
- `live_share=0.0`
- `latest_pricing_age_hours=119.14`
- degraded reasons include `manheim_live_share_below_threshold` and stale pricing evidence.

Pricing Coverage Gap Proof run `27490986854` reports:

- `clean_proxy_candidates=42`
- `pricing_recovery_groups=38`
- most groups are `blocked_no_internal_comp_evidence`
- most recommended actions are `request_completed_sales_evidence`
- one group remains `insufficient_internal_history` and must not be promoted.

Search found existing recovery scripts and confirmation-gated workflows:

- `scripts/report_pricing_coverage_gaps.py`
- `scripts/refresh_market_prices_from_completed_sales.py`
- `.github/workflows/pricing-coverage-gap-proof.yml`
- `.github/workflows/pricing-substrate-recovery.yml`

Search did not find a durable pricing recovery queue with owner, lifecycle status, timestamps, reason codes, proof-run provenance, or audit trail.

## Problem

The live recovery proof answers "what is blocked right now," but not "who owns the recovery work, what changed, when it changed, why it changed, and what evidence closed it."

That leaves four enterprise-grade gaps:

1. **Continuity gap:** Recovery groups disappear into GitHub logs unless someone manually reads them.
2. **Ownership gap:** No operator can claim, defer, block, or resolve a recovery group.
3. **Audit gap:** There is no durable trail from `request_completed_sales_evidence` to evidence acquisition to preview to confirmed market-price refresh.
4. **Governance gap:** There is no stable queue state separating "needs evidence," "evidence received," "preview ready," "applied," "dismissed," and "blocked."

The result is operationally honest but weak. The system tells the truth, yet it does not preserve the work in a form an operator can reliably execute.

## Non-Goals

- No scoring threshold changes.
- No alert threshold changes.
- No proxy-to-market-comp promotion.
- No automatic `market_prices` writes.
- No lowering of completed-sale sample thresholds.
- No public UI.
- No buyer-facing or seller-facing product surface.
- No raw VIN, listing URL, title, description, payload, user data, token, or secret in default proof output.
- No claim that creating a queue improves pricing quality by itself.
- No claim that evidence acquisition has happened until the queue shows evidence-backed state changes.

## Approaches Considered

### Approach 1: Workflow Artifact Queue

Continue writing grouped pricing recovery output as GitHub Action logs or uploaded JSON artifacts.

This is low risk and requires no schema migration, but it is weak for operator continuity. Artifacts expire, are not naturally claimable, and do not provide durable status or audit history.

Verdict: useful as supporting proof, not enough as the primary lane.

### Approach 2: Supabase-Backed Queue

Add a first-class table for pricing recovery requests, then upsert grouped recovery proof into that table. Use stable group keys, status fields, owner fields, proof-run provenance, timestamps, and sanitized evidence counters.

This gives the right durability and audit posture, but it introduces schema and lifecycle design risk. It must be constrained to queue state only and must not become an automatic pricing write path.

Verdict: strong direction, but needs a careful first slice.

### Approach 3: Hybrid Minimal Queue With Dry-Run Proof First

Add a durable queue contract and a dry-run/sync path, but keep market-price writes behind the already gated recovery workflow. The first implementation records grouped recovery work and operator status; it does not mutate pricing evidence except through later explicit confirmation-gated paths.

Verdict: selected. It creates real operator leverage while preserving pricing truth.

## Selected Design

Build a minimal pricing recovery operator queue with three bounded surfaces.

### 1. Queue Record Contract

Each queue record represents one sanitized pricing recovery group.

Stable identity:

- `group_key`: deterministic key from normalized `year`, `make`, `model`, `state`, and source family set.
- `year`
- `make`
- `model`
- `state`
- `source_families`

Live proof snapshot:

- `candidate_count`
- `status`
- `recommended_action`
- `market_prices_usable`
- `market_prices_total`
- `dealer_sales_usable`
- `dealer_sales_total`
- `competitor_sales_usable`
- `competitor_sales_total`
- `internal_history_usable`
- `internal_history_total`
- `latest_proof_run_id`
- `latest_proof_head_sha`
- `last_seen_at`

Operator lifecycle:

- `queue_status`: `open`, `evidence_requested`, `evidence_received`, `preview_ready`, `applied`, `blocked`, `dismissed`
- `owner`
- `priority`
- `blocked_reason`
- `resolution_notes`
- `created_at`
- `updated_at`
- `resolved_at`

The queue status is not the same as recovery proof status. Recovery proof status describes evidence coverage; queue status describes operator handling.

### 2. Queue Sync Path

Add a sync mode to the pricing coverage proof path or a focused helper that:

1. Reads the same grouped recovery rows already used by `Pricing Coverage Gap Proof`.
2. Builds sanitized queue records.
3. Upserts records by `group_key`.
4. Reopens or updates unresolved records when live proof changes.
5. Leaves resolved records intact unless the same group becomes active again with a new proof run.
6. Writes an audit event for each material state transition.

Default mode must be dry-run. Apply mode must require an explicit confirmation string.

### 3. Operator Proof Output

Add a read-only proof command and workflow output that prints queue health:

- total open recovery groups
- new groups this run
- reopened groups this run
- groups by `queue_status`
- groups by recovery proof `status`
- groups by `recommended_action`
- oldest open group age
- blocked groups with sanitized reason counts

The proof must not print VINs, listing URLs, titles, descriptions, raw payloads, user data, tokens, or secrets.

## Status Model

Recovery proof statuses remain:

- `covered_by_market_prices`
- `covered_by_dealer_sales`
- `covered_by_competitor_sales`
- `seedable_from_internal_history`
- `insufficient_internal_history`
- `insufficient_competitor_sales`
- `blocked_no_internal_comp_evidence`
- `dirty_source_row`
- `expired_pricing_gap`

Operator queue statuses are:

- `open`: live proof says work exists and no operator has moved it forward.
- `evidence_requested`: operator has requested or started completed-sale evidence acquisition.
- `evidence_received`: completed-sale evidence exists but no market-price preview has been accepted.
- `preview_ready`: threshold-bound preview exists and awaits confirmation.
- `applied`: an explicit confirmation-gated workflow wrote market pricing evidence.
- `blocked`: operator marked the group blocked with a required sanitized reason.
- `dismissed`: operator intentionally declined the group with a required sanitized reason.

Invalid transitions must be rejected in code. For example, a group cannot move from `open` directly to `applied` without proof of a preview/apply event.

## Data Flow

1. Pricing Coverage Gap Proof computes grouped recovery rows from live Supabase data.
2. Queue sync converts each group into a sanitized queue record.
3. Dry-run mode prints insert/update/reopen/close intentions without writing.
4. Confirmation-gated sync mode upserts the queue record and writes audit events.
5. Operator action updates queue lifecycle fields only.
6. Existing pricing substrate recovery workflow remains the only path for market-price refresh writes.
7. After any queue sync or apply, proof workflows show queue state and pricing quality state separately.

## Schema Direction

Add two narrow tables:

### `pricing_recovery_requests`

Purpose: current durable queue state for grouped recovery work.

Required constraints:

- primary key UUID
- unique `group_key`
- check constraint for allowed `queue_status`
- check constraint for allowed recovery proof `status`
- check constraint for allowed `recommended_action`
- nonnegative integer evidence counters
- no VIN, URL, title, description, raw payload, user data, token, or secret columns

### `pricing_recovery_request_events`

Purpose: immutable audit trail for queue state changes.

Required fields:

- request id
- event type
- previous queue status
- next queue status
- actor
- reason
- proof run id
- head sha
- created at
- sanitized metadata

The event table must not store raw listing details.

## Privacy And Sanitization

Allowed default output:

- year
- make
- model
- state
- source families
- aggregate counts
- status keys
- recommended action
- proof run id
- commit SHA
- queue status
- sanitized reason code

Disallowed default output:

- VIN
- listing URL
- title
- description
- raw payload
- raw completed-sale rows
- user data
- API tokens
- credentials

Tests must assert sanitizer behavior with VIN-like strings, URL-like strings, and title-shaped private values.

## Testing Strategy

Use test-driven development before runtime code.

Required RED/GREEN coverage:

- Queue record builder creates deterministic `group_key` from normalized grouped recovery data.
- Queue record builder rejects private listing fields.
- Queue status enum rejects unknown statuses.
- Recovery proof status enum rejects unknown statuses.
- Dry-run sync prints intended insert/update/reopen actions without writing.
- Apply sync requires explicit confirmation.
- Apply sync writes queue rows and audit events through a fake repository.
- Resolved queue rows are not overwritten incorrectly by repeated proof runs.
- Reopened groups write audit events.
- Workflow defaults to dry-run/read-only.
- Workflow apply mode requires confirmation.
- Queue proof output is aggregate-only and sanitizer-protected.

## Verification Gates

Local gates:

- Focused pricing recovery queue tests pass.
- Existing pricing coverage gap report tests pass.
- Existing market-price refresh preview tests pass.
- Existing workflow tests pass.
- Supabase live inspection tests pass.
- Full local suite passes before PR.
- `git diff --check` passes.

GitHub gates:

- PR checks pass.
- Cursor/Bugbot is clean, or all findings are fixed with RED/GREEN regressions.
- Queue proof workflow succeeds read-only.

Live gates:

- Main checks pass after merge.
- Railway `/healthz` remains OK.
- Fresh Supabase Live Inspection succeeds on current main.
- Fresh Pricing Coverage Gap Proof succeeds on current main.
- Fresh queue proof succeeds on current main and shows open queue counts without private listing leakage.

## Acceptance Criteria

This lane is complete only when:

- The queue contract exists and is tested.
- Recovery groups are materialized into durable queue state or a proven dry-run path ready for confirmation-gated sync.
- Operator lifecycle state is distinct from pricing-evidence status.
- State transitions are validated.
- Audit events exist for material state changes.
- Default proof output is sanitized and aggregate-only.
- Existing pricing gates remain unchanged.
- No market-price writes occur unless an explicit confirmation-gated recovery workflow is invoked.
- Live proof on main shows the queue proof and existing pricing proof both passing.

If the lane only creates a queue while live pricing quality remains degraded, the honest status is: operator recovery governance is live-confirmed, pricing-quality recovery remains pending evidence acquisition.
