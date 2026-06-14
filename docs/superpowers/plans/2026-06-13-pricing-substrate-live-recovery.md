# Pricing Substrate Live Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the live degraded pricing-quality signal into a governed recovery loop that groups clean active pricing gaps, previews safe market-price refreshes from trusted completed-sale evidence, and proves the result without weakening scoring gates.

**Architecture:** Extend the existing REST-first pricing coverage proof instead of creating a new authority surface. Add pure grouping/classification helpers, add a confirmation-gated promotion script for `competitor_sales`/`dealer_sales` evidence into `market_prices`, and update workflow proof to default to aggregate read-only output.

**Tech Stack:** Python scripts, pytest, GitHub Actions YAML, Supabase REST/Postgres helpers, existing `market_prices`, `dealer_sales`, `competitor_sales`, `ingest_delivery_log`, `sonar_listings`, and `opportunities` tables.

---

## File Map

- Modify `scripts/report_pricing_coverage_gaps.py`: add grouped recovery records, recommended actions, competitor-sales evidence matching, and aggregate formatting.
- Modify `tests/test_pricing_coverage_gap_report.py`: add RED/GREEN tests for grouped recovery status and sanitization.
- Create `scripts/refresh_market_prices_from_completed_sales.py`: dry-run/apply promotion from trusted completed-sale evidence into `market_prices`.
- Create `tests/test_refresh_market_prices_from_completed_sales.py`: promotion validation, preview rows, apply confirmation, and rejection tests.
- Modify `.github/workflows/pricing-coverage-gap-proof.yml`: add grouped output mode and keep read-only default.
- Create `.github/workflows/pricing-substrate-recovery.yml`: manual read-only recovery proof plus explicit confirmation-gated apply.
- Modify `tests/workflows/test_pricing_coverage_gap_proof_workflow.py`: grouped output assertions.
- Create `tests/workflows/test_pricing_substrate_recovery_workflow.py`: confirmation and sanitization workflow assertions.
- Keep `backend/ingest/score.py` and alert gating untouched.

## Task 1: Grouped Pricing Recovery Proof

**Files:**
- Modify `tests/test_pricing_coverage_gap_report.py`
- Modify `scripts/report_pricing_coverage_gaps.py`

- [ ] **Step 1: Add RED tests for grouped recovery classification**

Append tests that prove raw candidate rows become aggregate recovery groups and do not expose private row fields:

```python
def test_group_recovery_rows_blocks_when_no_evidence():
    rows = [
        {
            "candidate_origin": "delivery_pricing_skip",
            "year": 2020,
            "make": "ford",
            "model": "escape",
            "state": "sc",
            "source": "proxibid",
            "auction_active": True,
            "usable_market_prices_matches": 0,
            "market_prices_matches": 0,
            "usable_dealer_sales_matches": 0,
            "dealer_sales_matches": 0,
            "usable_opportunity_history": 0,
            "market_comp_opportunity_history": 0,
            "title": "private title",
            "vin": "1FMCU0F60LUB43858",
            "listing_url": "https://example.test/private",
        }
    ]

    groups = report_pricing_coverage_gaps.group_recovery_rows(rows)

    assert groups == [
        {
            "key": {
                "year": 2020,
                "make": "ford",
                "model": "escape",
                "state": "sc",
            },
            "candidate_count": 1,
            "source_counts": {"proxibid": 1},
            "status": "blocked_no_internal_comp_evidence",
            "recommended_action": "request_completed_sales_evidence",
            "evidence_counts": {
                "usable_market_prices": 0,
                "market_prices": 0,
                "usable_dealer_sales": 0,
                "dealer_sales": 0,
                "usable_internal_history": 0,
                "internal_history": 0,
                "usable_competitor_sales": 0,
                "competitor_sales": 0,
            },
        }
    ]
    assert "private title" not in report_pricing_coverage_gaps.format_recovery_group(groups[0])
    assert "1FMCU0F60LUB43858" not in report_pricing_coverage_gaps.format_recovery_group(groups[0])
    assert "https://example.test/private" not in report_pricing_coverage_gaps.format_recovery_group(groups[0])


def test_group_recovery_rows_preserves_insufficient_history_threshold():
    rows = [
        {
            "year": 2016,
            "make": "ford",
            "model": "f-150",
            "state": "ga",
            "source": "allsurplus",
            "usable_market_prices_matches": 0,
            "market_prices_matches": 0,
            "usable_dealer_sales_matches": 0,
            "dealer_sales_matches": 0,
            "usable_opportunity_history": 2,
            "market_comp_opportunity_history": 2,
        }
    ]

    groups = report_pricing_coverage_gaps.group_recovery_rows(rows)

    assert groups[0]["status"] == "insufficient_internal_history"
    assert groups[0]["recommended_action"] == "wait_for_more_internal_history"
```

- [ ] **Step 2: Run RED test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_coverage_gap_report.py -q
```

Expected: fail because `group_recovery_rows` and `format_recovery_group` do not exist.

- [ ] **Step 3: Implement grouped proof helpers**

In `scripts/report_pricing_coverage_gaps.py`, add pure helpers:

```python
def recommended_action_for_status(status: str) -> str:
    return {
        "covered_by_market_prices": "none",
        "covered_by_dealer_sales": "refresh_market_prices_from_dealer_sales",
        "covered_by_competitor_sales": "refresh_market_prices_from_competitor_sales",
        "seedable_from_internal_history": "refresh_market_prices_from_dealer_sales",
        "insufficient_internal_history": "wait_for_more_internal_history",
        "insufficient_competitor_sales": "request_completed_sales_evidence",
        "blocked_no_internal_comp_evidence": "request_completed_sales_evidence",
        "dirty_source_row": "ignore_dirty_source_row",
        "expired_pricing_gap": "ignore_expired_listing",
    }.get(status, "request_completed_sales_evidence")
```

Add `group_recovery_rows(rows: list[dict]) -> list[dict]` that groups by `year/make/model/state`, sums evidence counts, aggregates `source_counts`, chooses the strongest status in this order:

1. `covered_by_market_prices`
2. `covered_by_dealer_sales`
3. `covered_by_competitor_sales`
4. `seedable_from_internal_history`
5. `insufficient_internal_history`
6. `insufficient_competitor_sales`
7. `blocked_no_internal_comp_evidence`

Add `format_recovery_group(group: dict) -> str` that prints only aggregate fields.

- [ ] **Step 4: Run GREEN test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_coverage_gap_report.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add scripts/report_pricing_coverage_gaps.py tests/test_pricing_coverage_gap_report.py
git commit -m "feat: group pricing substrate recovery gaps"
```

## Task 2: Completed-Sales Market-Price Refresh Preview

**Files:**
- Create `tests/test_refresh_market_prices_from_completed_sales.py`
- Create `scripts/refresh_market_prices_from_completed_sales.py`

- [ ] **Step 1: Add RED tests for preview and rejection**

Create tests proving the script can build a preview row from completed-sale evidence and rejects weak evidence:

```python
from datetime import datetime, timezone

from scripts import refresh_market_prices_from_completed_sales as refresh


def test_preview_market_price_from_competitor_sales_group():
    rows = [
        {"year": 2020, "make": "Ford", "model": "Escape", "state": "SC", "sale_price": price, "auction_end_date": "2026-05-01T00:00:00+00:00", "source": "proxibid"}
        for price in (17000, 18000, 19000, 20000, 21000)
    ]

    preview = refresh.build_market_price_preview(
        rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    )

    assert preview["year"] == 2020
    assert preview["make"] == "ford"
    assert preview["model"] == "escape"
    assert preview["state"] == "sc"
    assert preview["avg_price"] == 19000.0
    assert preview["low_price"] == 17000.0
    assert preview["high_price"] == 21000.0
    assert preview["sample_size"] == 5
    assert preview["source"] == "competitor_sales"
    assert preview["source_run_id"] == "pricing-recovery-test"
    assert "proxy" not in preview["confidence_notes"].lower()


def test_preview_rejects_sparse_or_zero_completed_sales():
    rows = [
        {"year": 2020, "make": "Ford", "model": "Escape", "state": "SC", "sale_price": 0, "auction_end_date": "2026-05-01T00:00:00+00:00", "source": "proxibid"}
    ]

    assert refresh.build_market_price_preview(
        rows,
        source="competitor_sales",
        source_run_id="pricing-recovery-test",
        now=datetime(2026, 6, 14, tzinfo=timezone.utc),
        ttl_days=14,
        min_sample_size=5,
    ) is None
```

- [ ] **Step 2: Run RED test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_refresh_market_prices_from_completed_sales.py -q
```

Expected: fail because the module does not exist.

- [ ] **Step 3: Implement preview-only script**

Create `scripts/refresh_market_prices_from_completed_sales.py` with:

- `build_market_price_preview(rows, source, source_run_id, now, ttl_days, min_sample_size)`
- `_safe_price`, `_parse_datetime`, `_normalize_text`
- `main()` with dry-run default
- no database writes yet

The preview must use only completed sale prices and dates. Do not use current bid, proxy MMR, title, listing URL, or raw payload.

- [ ] **Step 4: Run GREEN test**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_refresh_market_prices_from_completed_sales.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add scripts/refresh_market_prices_from_completed_sales.py tests/test_refresh_market_prices_from_completed_sales.py
git commit -m "feat: preview market price recovery rows"
```

## Task 3: Confirmation-Gated Apply And Workflow Proof

**Files:**
- Modify `tests/test_refresh_market_prices_from_completed_sales.py`
- Modify `scripts/refresh_market_prices_from_completed_sales.py`
- Create `.github/workflows/pricing-substrate-recovery.yml`
- Create `tests/workflows/test_pricing_substrate_recovery_workflow.py`
- Modify `.github/workflows/pricing-coverage-gap-proof.yml`
- Modify `tests/workflows/test_pricing_coverage_gap_proof_workflow.py`

- [ ] **Step 1: Add RED tests for apply confirmation**

Add tests:

```python
def test_apply_requires_confirmation():
    assert refresh.confirm_apply(apply=True, confirmation="") is False
    assert refresh.confirm_apply(apply=True, confirmation="REFRESH_MARKET_PRICES_FROM_COMPLETED_SALES") is True
    assert refresh.confirm_apply(apply=False, confirmation="") is True
```

Create workflow tests asserting:

```python
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "pricing-substrate-recovery.yml"


def test_pricing_substrate_recovery_workflow_is_manual_and_confirmation_gated():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "pull_request:" not in text
    assert "apply:" in text
    assert "confirmation:" in text
    assert "REFRESH_MARKET_PRICES_FROM_COMPLETED_SALES" in text
    assert "scripts/refresh_market_prices_from_completed_sales.py" in text
    assert "set -x" not in text.lower()
```

- [ ] **Step 2: Run RED tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_refresh_market_prices_from_completed_sales.py tests/workflows/test_pricing_substrate_recovery_workflow.py -q
```

Expected: fail because apply helper and workflow are missing.

- [ ] **Step 3: Implement apply confirmation and workflow**

Add:

- `confirm_apply(apply: bool, confirmation: str) -> bool`
- `insert_market_price_rows_via_rest(...)` or direct DB insert following existing `prepare_external_market_comp_seed.py` style
- CLI args `--apply`, `--confirmation`, `--ttl-days`, `--min-sample-size`, `--source-run-id`, `--via-rest`

Create `.github/workflows/pricing-substrate-recovery.yml`:

- manual `workflow_dispatch` only
- defaults `apply=false`
- requires `confirmation=REFRESH_MARKET_PRICES_FROM_COMPLETED_SALES` when apply is true
- uses `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
- prints aggregate preview output
- never enables shell tracing

Update `pricing-coverage-gap-proof.yml` with a grouped output input only if Task 1 adds a CLI flag such as `--grouped`.

- [ ] **Step 4: Run GREEN workflow and script tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_refresh_market_prices_from_completed_sales.py tests/workflows/test_pricing_substrate_recovery_workflow.py tests/workflows/test_pricing_coverage_gap_proof_workflow.py -q
```

Expected: tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add scripts/refresh_market_prices_from_completed_sales.py tests/test_refresh_market_prices_from_completed_sales.py .github/workflows/pricing-substrate-recovery.yml tests/workflows/test_pricing_substrate_recovery_workflow.py .github/workflows/pricing-coverage-gap-proof.yml tests/workflows/test_pricing_coverage_gap_proof_workflow.py
git commit -m "feat: gate pricing substrate recovery workflow"
```

## Task 4: Verification, PR, And Live Proof

**Files:**
- No planned code files unless review finds a defect.

- [ ] **Step 1: Run focused local verification**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_pricing_coverage_gap_report.py tests/test_refresh_market_prices_from_completed_sales.py tests/workflows/test_pricing_coverage_gap_proof_workflow.py tests/workflows/test_pricing_substrate_recovery_workflow.py -q
```

Expected: pass.

- [ ] **Step 2: Run adjacent local verification**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_competitor_pricing.py tests/test_competitor_pricing_scoring.py tests/test_competitor_sales_scraper_runner.py tests/test_prepare_external_market_comp_seed.py tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py -q
```

Expected: pass.

- [ ] **Step 3: Run full local suite**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest -q
```

Expected: pass.

- [ ] **Step 4: Open PR and monitor reviews**

```bash
git push -u origin fix/pricing-substrate-live-recovery
gh pr create --repo pilsonandrew-hub/dealscan-insight --title "Harden pricing substrate live recovery" --body-file /tmp/pricing-substrate-live-recovery-pr.md
```

PR body must include the exact test commands and state that scoring and alert gates were not relaxed.

- [ ] **Step 5: Address review with RED/GREEN tests**

If Cursor/Bugbot/Codex/Devin finds a valid issue:

1. Add a failing regression test.
2. Run it and capture expected failure.
3. Implement the fix.
4. Run focused, adjacent, and full verification as needed.
5. Commit and push.

- [ ] **Step 6: Merge only after clean checks**

Merge only when:

- PR checks pass.
- Cursor/Bugbot has no unresolved valid finding.
- Review comments are resolved or demonstrably stale.

- [ ] **Step 7: Live proof after merge**

Run:

```bash
gh workflow run pricing-coverage-gap-proof.yml --repo pilsonandrew-hub/dealscan-insight --ref main -f lookback_days=14 -f max_mileage=100000 -f max_age_years=10 -f limit=100
gh workflow run pricing-substrate-recovery.yml --repo pilsonandrew-hub/dealscan-insight --ref main -f apply=false -f confirmation="" -f ttl_days=14 -f min_sample_size=5
gh workflow run supabase-live-inspection.yml --repo pilsonandrew-hub/dealscan-insight --ref main
```

Expected:

- workflows succeed on current main
- pricing recovery proof prints grouped aggregate gaps
- no private listing details appear in default workflow output
- `market_data_quality` remains degraded unless real trusted evidence was applied

- [ ] **Step 8: Closeout classification**

Use exactly one status:

- `live-confirmed` if PR merged, post-merge checks pass, Railway health is OK, and fresh live proof succeeds.
- `live-improved but pending` if grouped proof works but no trusted evidence exists to refresh pricing quality.
- `locally validated only` if PR is not merged or live proof has not run.
- `hypothesis` if the evidence does not support the lane.
