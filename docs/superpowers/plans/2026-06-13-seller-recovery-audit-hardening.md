# Seller Recovery Audit Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the internal seller recovery audit endpoint into a deterministic operator-grade JSON contract with ranked candidates, evidence, rollups, source-health summary, and explicit truth boundaries.

**Architecture:** Extend the existing read-only `/api/internal/seller-recovery-audit` builder rather than adding a new product surface. Keep scoring pure and deterministic inside `webapp/routers/internal.py`, mirror the proof contract in `scripts/supabase_live_inspection.py`, and prove both paths with focused contract tests before any PR.

**Tech Stack:** Python, FastAPI route builder, Supabase read-only query helpers, pytest, GitHub Actions, Railway health check.

---

## File Map

- Modify `tests/test_internal_pipeline_truth.py`: endpoint contract, scoring, rollup, degradation, and sanitization tests.
- Modify `webapp/routers/internal.py`: pure scoring helpers, candidate evidence, rollups, source-health summary, truth-boundary contract.
- Modify `tests/test_supabase_live_inspection.py`: read-only proof contract tests mirroring the endpoint hardening sections.
- Modify `scripts/supabase_live_inspection.py`: live proof scoring helpers, rollups, source-health summary, and truth boundaries.
- Do not add migrations or persistence tables in this pass.
- Do not add UI, report generation, public routes, or seller/investor copy.

## Scoring Contract

Use this deterministic scoring model in both endpoint and live-inspection proof:

```python
RECOVERY_REASON_WEIGHTS = {
    "missing_vin": 4.0,
    "missing_mileage": 4.0,
    "missing_auction_end": 4.0,
    "condition_unverified": 5.0,
    "proxy_pricing": 5.0,
    "missing_photos_flag": 4.0,
    "zero_photo_count": 4.0,
    "low_photo_count": 2.0,
}

def _recovery_tier(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"
```

Component weights must sum to at most 100:

- `value_gap`: max 40, from gross margin and bid headroom.
- `listing_quality`: max 30, from recovery reasons.
- `evidence_strength`: max 20, from governed pricing/photo/bidder/score evidence.
- `source_health`: max 10, from source-health row presence plus failed/skipped/parse-event observability.

The score is a prioritization score, not a revenue promise.

## Task 1: Endpoint Contract Tests

**Files:**
- Modify: `tests/test_internal_pipeline_truth.py`
- Test command: `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q`

- [ ] **Step 1: Add failing test for ranked candidate scoring and sanitization**

Add this test after `test_seller_recovery_audit_returns_sanitized_evidence_backed_candidates`:

```python
def test_seller_recovery_audit_ranks_candidates_with_bounded_scores(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "source_health_daily": [
            {"source_name": "govdeals", "total_runs": 3, "processed_runs": 2, "failed_runs": 1, "saved_count": 4, "skipped_count": 8, "parse_event_count": 12},
            {"source_name": "hibid", "total_runs": 1, "processed_runs": 1, "failed_runs": 0, "saved_count": 1, "skipped_count": 0, "parse_event_count": 1},
        ],
        "ingest_delivery_log": [
            {"status": "skipped_margin", "error_message": "margin_below_floor", "created_at": "2026-06-13T01:00:00Z"},
            {"status": "skipped_gate", "error_message": "condition_unverified", "created_at": "2026-06-13T01:01:00Z"},
        ],
        "parse_events": [
            {"source_name": "govdeals", "event_type": "db_save", "status": "skipped_margin", "reason": "margin_below_floor"},
            {"source_name": "govdeals", "event_type": "db_save", "status": "saved", "reason": None},
        ],
        "opportunities": [
            {
                "id": "candidate-high", "is_active": True, "source_site": "govdeals", "year": 2023,
                "make": "Ford", "model": "F-150", "dos_score": 86, "gross_margin": 21000,
                "bid_headroom": 17000, "pricing_maturity": "market_comp", "vin": None,
                "mileage": None, "condition_grade": "Unknown", "auction_end_date": None,
                "risk_flags": ["missing_photos"], "photo_count": 0, "bidder_count": None,
                "listing_url": "https://private.example/high", "raw_data": {"vin": "SECRETVINHIGH"},
            },
            {
                "id": "candidate-medium", "is_active": True, "source_site": "hibid", "year": 2024,
                "make": "Toyota", "model": "Tacoma", "dos_score": 81, "gross_margin": 4200,
                "bid_headroom": 900, "pricing_maturity": "proxy", "vin": "5TSECRET",
                "mileage": 19000, "condition_grade": "Good", "auction_end_date": "2026-06-20T00:00:00Z",
                "risk_flags": [], "photo_count": 2, "bidder_count": None,
            },
        ],
        "sonar_listings": [{"source_site": "hibid", "source": "hibid", "bidder_count": 12}],
    }))

    result = internal.build_seller_recovery_audit()
    candidates = result["value_leak_candidates"]

    assert [candidate["id"] for candidate in candidates] == ["candidate-high", "candidate-medium"]
    assert candidates[0]["recovery_score"] > candidates[1]["recovery_score"]
    assert candidates[0]["recovery_tier"] == "high"
    assert candidates[1]["recovery_tier"] in {"medium", "low"}
    for candidate in candidates:
        assert 0 <= candidate["recovery_score"] <= 100
        assert set(candidate["score_components"]) == {"value_gap", "listing_quality", "evidence_strength", "source_health"}
        assert round(sum(candidate["score_components"].values()), 2) == candidate["recovery_score"]
        assert "evidence" in candidate
        assert "truth_boundary" in candidate
    serialized = str(result)
    assert "SECRETVINHIGH" not in serialized
    assert "https://private.example/high" not in serialized
```

- [ ] **Step 2: Add failing test for rollups and truth boundaries**

Add this test after the scoring test:

```python
def test_seller_recovery_audit_returns_rollups_and_truth_boundaries(monkeypatch):
    monkeypatch.setattr(internal, "supabase_client", _Supabase({
        "source_health_daily": [
            {"source_name": "allsurplus", "total_runs": 2, "processed_runs": 1, "failed_runs": 1, "saved_count": 3, "skipped_count": 9, "parse_event_count": 11},
        ],
        "ingest_delivery_log": [
            {"status": "skipped_margin", "error_message": "margin_below_floor"},
            {"status": "skipped_margin", "error_message": "margin_below_floor"},
        ],
        "parse_events": [{"source_name": "allsurplus", "event_type": "db_save", "status": "skipped_margin", "reason": "margin_below_floor"}],
        "opportunities": [
            {"id": "c1", "is_active": True, "source_site": "allsurplus", "gross_margin": 9000, "bid_headroom": 7000, "dos_score": 84, "pricing_maturity": "market_comp", "vin": None, "mileage": None, "condition_grade": "Unknown", "risk_flags": ["missing_photos"], "photo_count": 0},
            {"id": "c2", "is_active": True, "source_site": "allsurplus", "gross_margin": 6000, "bid_headroom": 3000, "dos_score": 82, "pricing_maturity": "market_comp", "vin": "known", "mileage": 24000, "condition_grade": "Good", "risk_flags": [], "photo_count": 1},
        ],
        "sonar_listings": [],
    }))

    result = internal.build_seller_recovery_audit()

    assert result["recovery_rollups"]["reason_counts"]["missing_photos_flag"] == 1
    assert result["recovery_rollups"]["reason_counts"]["low_photo_count"] == 1
    assert result["recovery_rollups"]["source_counts"] == {"allsurplus": 2}
    assert result["recovery_rollups"]["top_sources_by_score"][0]["source_site"] == "allsurplus"
    assert result["source_health_summary"]["observed_source_count"] == 1
    assert result["source_health_summary"]["sources_with_failed_runs"] == 1
    assert result["source_health_summary"]["total_failed_runs"] == 1
    assert result["truth_boundaries"]["candidate_ranking"].startswith("Internal deterministic prioritization")
    assert "seller intent" in result["truth_boundaries"]["source_health"]
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: failures mention missing `recovery_score`, `recovery_rollups`, `source_health_summary`, or `truth_boundaries`.

## Task 2: Endpoint Scoring Helpers

**Files:**
- Modify: `webapp/routers/internal.py`
- Test command: `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q`

- [ ] **Step 1: Add pure helpers near `_candidate_recovery_reasons`**

Insert this code before `_seller_recovery_candidates`:

```python
RECOVERY_REASON_WEIGHTS = {
    "missing_vin": 4.0,
    "missing_mileage": 4.0,
    "missing_auction_end": 4.0,
    "condition_unverified": 5.0,
    "proxy_pricing": 5.0,
    "missing_photos_flag": 4.0,
    "zero_photo_count": 4.0,
    "low_photo_count": 2.0,
}


def _bounded_component(value: float, maximum: float) -> float:
    return round(max(0.0, min(float(value), maximum)), 2)


def _component_from_amount(value: Optional[float], *, cap: float, points: float) -> float:
    if value is None or value <= 0:
        return 0.0
    return _bounded_component((min(value, cap) / cap) * points, points)


def _source_key(value: Any) -> str:
    return str(value or "unknown").strip().lower()[:80] or "unknown"


def _recovery_tier(score: float) -> str:
    if score >= 75:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _source_health_by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = _source_key(row.get("source_name"))
        latest.setdefault(source, row)
    return latest


def _source_health_component(source_site: str, source_health_index: dict[str, dict[str, Any]]) -> float:
    row = source_health_index.get(_source_key(source_site))
    if not row:
        return 0.0
    score = 2.0
    if (_as_int(row.get("failed_runs")) or 0) > 0:
        score += 3.0
    if (_as_int(row.get("skipped_count")) or 0) > 0:
        score += 2.0
    if (_as_int(row.get("parse_event_count")) or 0) > 0:
        score += 2.0
    if (_as_int(row.get("saved_count")) or 0) > 0:
        score += 1.0
    return _bounded_component(score, 10.0)


def _candidate_evidence(row: dict[str, Any], *, source_bidder_available: bool) -> dict[str, Any]:
    opportunity_bidder = _bidder_count(row)
    source_mirror_bidder = bool(source_bidder_available and opportunity_bidder is None)
    return {
        "dos_score_present": _numeric_score(row) is not None,
        "gross_margin_present": _first_number(row, "gross_margin", "potential_profit", "margin") is not None,
        "bid_headroom_present": _first_number(row, "bid_headroom") is not None,
        "photo_count_present": _photo_count(row) is not None,
        "opportunity_bidder_count_present": opportunity_bidder is not None,
        "source_mirror_bidder_count_present": source_mirror_bidder,
        "bidder_depth_surface": "opportunities" if opportunity_bidder is not None else "source_mirror" if source_mirror_bidder else None,
        "pricing_maturity": str(row.get("pricing_maturity") or "unknown")[:80],
    }


def _score_candidate(row: dict[str, Any], reasons: list[str], *, source_bidder_available: bool, source_health_index: dict[str, dict[str, Any]]) -> tuple[float, dict[str, float], dict[str, Any]]:
    gross_margin = _first_number(row, "gross_margin", "potential_profit", "margin")
    bid_headroom = _first_number(row, "bid_headroom")
    value_gap = _bounded_component(
        _component_from_amount(gross_margin, cap=25000.0, points=25.0)
        + _component_from_amount(bid_headroom, cap=25000.0, points=15.0),
        40.0,
    )
    listing_quality = _bounded_component(sum(RECOVERY_REASON_WEIGHTS.get(reason, 0.0) for reason in reasons), 30.0)
    evidence = _candidate_evidence(row, source_bidder_available=source_bidder_available)
    evidence_strength = _bounded_component(
        (3.0 if evidence["dos_score_present"] else 0.0)
        + (2.0 if evidence["gross_margin_present"] else 0.0)
        + (2.0 if evidence["bid_headroom_present"] else 0.0)
        + (4.0 if evidence["photo_count_present"] else 0.0)
        + (4.0 if evidence["opportunity_bidder_count_present"] else 0.0)
        + (3.0 if evidence["source_mirror_bidder_count_present"] else 0.0)
        + (3.0 if str(row.get("pricing_maturity") or "").lower() == "market_comp" else 0.0)
        + (2.0 if str(row.get("pricing_maturity") or "").lower() != "proxy" else 0.0),
        20.0,
    )
    source_health = _source_health_component(str(row.get("source_site") or row.get("source") or "unknown"), source_health_index)
    components = {
        "value_gap": value_gap,
        "listing_quality": listing_quality,
        "evidence_strength": evidence_strength,
        "source_health": source_health,
    }
    score = round(sum(components.values()), 2)
    return score, components, evidence
```

- [ ] **Step 2: Change `_seller_recovery_candidates` signature and candidate object**

Replace the function header and scoring block with:

```python
def _seller_recovery_candidates(
    rows: list[dict[str, Any]],
    *,
    source_listing_rows: Optional[list[dict[str, Any]]] = None,
    source_health_rows: Optional[list[dict[str, Any]]] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    source_listing_rows = source_listing_rows or []
    source_health_index = _source_health_by_source(source_health_rows or [])
    source_bidder_available = any(_bidder_count(row) is not None for row in source_listing_rows)
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if row.get("is_active") is False:
            continue
        gross_margin = _first_number(row, "gross_margin", "potential_profit", "margin")
        bid_headroom = _first_number(row, "bid_headroom")
        if gross_margin is None and bid_headroom is None:
            continue
        reasons = _candidate_recovery_reasons(row)
        if not reasons:
            continue
        score = _numeric_score(row)
        recovery_score, score_components, evidence = _score_candidate(
            row,
            reasons,
            source_bidder_available=source_bidder_available,
            source_health_index=source_health_index,
        )
        candidates.append({
            "id": str(row.get("id") or "")[:80],
            "source_site": str(row.get("source_site") or row.get("source") or "unknown")[:80],
            "year": _as_int(row.get("year")) if row.get("year") is not None else None,
            "make": str(row.get("make") or "")[:80],
            "model": str(row.get("model") or "")[:80],
            "dos_score": round(score, 2) if score is not None else None,
            "gross_margin": round(gross_margin, 2) if gross_margin is not None else None,
            "bid_headroom": round(bid_headroom, 2) if bid_headroom is not None else None,
            "pricing_maturity": str(row.get("pricing_maturity") or "unknown")[:80],
            "recovery_reasons": reasons,
            "recovery_score": recovery_score,
            "recovery_tier": _recovery_tier(recovery_score),
            "score_components": score_components,
            "evidence": evidence,
            "truth_boundary": "Internal prioritization from governed fields only; not a recovery guarantee or seller-intent claim.",
        })
    candidates.sort(
        key=lambda item: (
            float(item["recovery_score"] or 0),
            float(item["gross_margin"] or 0),
            float(item["bid_headroom"] or 0),
            float(item["dos_score"] or 0),
        ),
        reverse=True,
    )
    return candidates[:limit]
```

- [ ] **Step 3: Update builder call**

Replace:

```python
candidates = _seller_recovery_candidates(opportunity_rows)
```

with:

```python
candidates = _seller_recovery_candidates(
    opportunity_rows,
    source_listing_rows=source_listing_rows,
    source_health_rows=source_health_rows,
)
```

- [ ] **Step 4: Run endpoint tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: scoring test passes; rollup test still fails until Task 3.

## Task 3: Endpoint Rollups and Truth Boundaries

**Files:**
- Modify: `webapp/routers/internal.py`
- Test command: `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q`

- [ ] **Step 1: Add rollup helpers near `_source_listing_quality_summary`**

```python
def _recovery_rollups(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    tier_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    source_scores: dict[str, list[float]] = defaultdict(list)
    source_reasons: dict[str, Counter[str]] = defaultdict(Counter)
    for candidate in candidates:
        source = str(candidate.get("source_site") or "unknown")[:80]
        tier_counts[str(candidate.get("recovery_tier") or "low")] += 1
        source_counts[source] += 1
        source_scores[source].append(float(candidate.get("recovery_score") or 0))
        for reason in candidate.get("recovery_reasons") or []:
            reason_counts[str(reason)] += 1
            source_reasons[source][str(reason)] += 1
    top_sources = []
    for source, scores in source_scores.items():
        top_sources.append({
            "source_site": source,
            "candidate_count": source_counts[source],
            "average_recovery_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "top_reasons": [reason for reason, _count in source_reasons[source].most_common(5)],
        })
    top_sources.sort(key=lambda item: (item["average_recovery_score"], item["candidate_count"]), reverse=True)
    return {
        "reason_counts": dict(reason_counts.most_common(20)),
        "tier_counts": {"high": tier_counts.get("high", 0), "medium": tier_counts.get("medium", 0), "low": tier_counts.get("low", 0)},
        "source_counts": dict(source_counts.most_common(20)),
        "top_sources_by_score": top_sources[:10],
    }


def _source_health_summary(source_health_rows: list[dict[str, Any]], delivery_rows: list[dict[str, Any]], parse_event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed_sources = {_source_key(row.get("source_name")) for row in source_health_rows if row.get("source_name")}
    return {
        "observed_source_count": len(observed_sources),
        "sources_with_failed_runs": sum(1 for row in source_health_rows if (_as_int(row.get("failed_runs")) or 0) > 0),
        "total_processed_runs": sum(_as_int(row.get("processed_runs")) or 0 for row in source_health_rows),
        "total_failed_runs": sum(_as_int(row.get("failed_runs")) or 0 for row in source_health_rows),
        "total_saved_count": sum(_as_int(row.get("saved_count")) or 0 for row in source_health_rows),
        "total_skipped_count": sum(_as_int(row.get("skipped_count")) or 0 for row in source_health_rows),
        "total_parse_event_count": sum(_as_int(row.get("parse_event_count")) or 0 for row in source_health_rows),
        "top_delivery_statuses": _status_counts(delivery_rows, "status"),
        "top_parse_event_statuses": _status_counts(parse_event_rows, "status"),
    }


SELLER_RECOVERY_TRUTH_BOUNDARIES = {
    "candidate_ranking": "Internal deterministic prioritization, not a recovery guarantee.",
    "bidder_depth": "Uses governed opportunity bidder_count when present; otherwise uses governed source mirror bidder_count when present.",
    "photo_quality": "Uses governed photo_count and missing_photos risk flags; does not infer photo quality from private raw payloads.",
    "source_health": "Aggregates run and parse-event observability; does not prove seller intent.",
}
```

- [ ] **Step 2: Add new sections to `build_seller_recovery_audit` return**

Add these keys after `source_listing_quality`:

```python
"source_health_summary": _source_health_summary(source_health_rows, delivery_rows, parse_event_rows),
"recovery_rollups": _recovery_rollups(candidates),
```

Add this key near `truth_boundary`:

```python
"truth_boundaries": SELLER_RECOVERY_TRUTH_BOUNDARIES,
```

- [ ] **Step 3: Run endpoint tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: all endpoint tests pass.

- [ ] **Step 4: Commit endpoint work**

```bash
git add webapp/routers/internal.py tests/test_internal_pipeline_truth.py
git commit -m "feat: harden seller recovery audit endpoint"
```

## Task 4: Live Inspection Proof Contract

**Files:**
- Modify: `tests/test_supabase_live_inspection.py`
- Modify: `scripts/supabase_live_inspection.py`
- Test command: `/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q`

- [ ] **Step 1: Add failing live-inspection assertions**

In `test_safe_truth_audit_includes_sanitized_seller_recovery_candidates`, add:

```python
    candidate = report["seller_recovery_audit"]["value_leak_candidates"][0]
    assert candidate["recovery_score"] > 0
    assert candidate["recovery_tier"] in {"high", "medium", "low"}
    assert round(sum(candidate["score_components"].values()), 2) == candidate["recovery_score"]
    assert candidate["evidence"]["photo_count_present"] is True
    assert report["seller_recovery_audit"]["recovery_rollups"]["reason_counts"]["missing_photos_flag"] == 1
    assert report["seller_recovery_audit"]["source_health_summary"]["observed_source_count"] == 1
    assert report["seller_recovery_audit"]["truth_boundaries"]["candidate_ranking"].startswith("Internal deterministic prioritization")
```

In `test_seller_recovery_audit_reports_source_mirror_bidder_depth_when_opportunities_lack_it`, add:

```python
    candidate = report["value_leak_candidates"][0]
    assert candidate["evidence"]["bidder_depth_surface"] == "source_mirror"
    assert candidate["evidence"]["source_mirror_bidder_count_present"] is True
```

- [ ] **Step 2: Run live-inspection tests and confirm failure**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q
```

Expected: failures mention missing scoring or rollup keys.

- [ ] **Step 3: Mirror endpoint helpers in `scripts/supabase_live_inspection.py`**

Add script-local versions of the helpers from Tasks 2 and 3, using existing script names `_coerce_int`, `_coerce_float`, `_first_positive_number`, `_photo_count`, and `_bidder_count` instead of endpoint-only helper names.

Use the same public output keys:

```python
"recovery_score"
"recovery_tier"
"score_components"
"evidence"
"truth_boundary"
"recovery_rollups"
"source_health_summary"
"truth_boundaries"
```

- [ ] **Step 4: Update `_seller_recovery_candidates_from_opportunities` and `_summarize_seller_recovery_audit`**

Change candidate sorting to `recovery_score` first and return the same candidate contract as the endpoint. Add summary sections:

```python
"source_health_summary": _seller_recovery_source_health_summary(source_health_rows, delivery_rows, parse_event_rows),
"recovery_rollups": _seller_recovery_rollups(candidates),
"truth_boundaries": SELLER_RECOVERY_TRUTH_BOUNDARIES,
```

- [ ] **Step 5: Run live-inspection tests**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q
```

Expected: all live-inspection tests pass.

- [ ] **Step 6: Commit live-inspection work**

```bash
git add scripts/supabase_live_inspection.py tests/test_supabase_live_inspection.py
git commit -m "test: prove seller recovery audit hardening live inspection"
```

## Task 5: Focused and Full Verification

**Files:**
- Verify all touched files.

- [ ] **Step 1: Run focused endpoint and live-proof tests**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run adjacent focused suite**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py tests/test_ingest_rollout_preflight.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run full local suite**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests -q
```

Expected: full suite passes.

- [ ] **Step 4: Inspect working tree**

```bash
git status --short
git diff --stat origin/main...HEAD
```

Expected: only seller recovery hardening files and docs are changed.

## Task 6: PR, CI, Deployment, and Live Proof

**Files:**
- No direct file edits unless review or CI finds a current defect.

- [ ] **Step 1: Push branch and open PR**

```bash
git push -u origin fix/seller-recovery-audit-hardening
gh pr create --title "Harden seller recovery audit contract" --body-file docs/superpowers/specs/2026-06-13-seller-recovery-audit-hardening-design.md
```

Expected: PR opens against `main`.

- [ ] **Step 2: Wait for PR checks**

```bash
gh pr checks --watch
```

Expected: DealerScope CI, Cursor Code Review, Vercel Deploy Gate, and relevant checks pass. If Cursor flags a current defect, address it before merge.

- [ ] **Step 3: Merge only after green checks**

```bash
gh pr merge --squash --delete-branch
```

Expected: PR merged into `main`.

- [ ] **Step 4: Verify current-main checks**

```bash
gh run list --branch main --limit 10 --json databaseId,name,status,conclusion,headSha,createdAt
```

Expected: latest main checks for the merge commit succeed.

- [ ] **Step 5: Verify Railway health**

```bash
curl -sS https://dealscan-insight-production.up.railway.app/healthz
```

Expected: `{"status":"ok"}` with a fresh timestamp.

- [ ] **Step 6: Run fresh production live inspection**

```bash
gh workflow run supabase-live-inspection.yml --ref main
gh run list --workflow "DealerScope Supabase Live Inspection" --branch main --limit 3
NEW_RUN_ID=$(gh run list --workflow "DealerScope Supabase Live Inspection" --branch main --limit 1 --json databaseId --jq '.[0].databaseId')
gh run view "$NEW_RUN_ID" --log | rg -n "seller_recovery_audit|recovery_score|recovery_rollups|source_health_summary|truth_boundaries"
```

Expected: live inspection succeeds and prints the hardened seller recovery sections without sensitive fields.

- [ ] **Step 7: Close with exact status label**

Send Andrew the final classification:

```text
Status: live-confirmed.
Evidence: PR number, merge commit, focused tests, full suite, PR checks, main checks, Railway health, fresh Supabase Live Inspection run, and the specific hardened fields proved in live logs.
```

Do not call the issue fixed before Step 6 succeeds.

## Self-Review

- Spec coverage: endpoint scoring, candidate evidence, rollups, source-health summary, truth boundaries, sanitization, live inspection, and live closeout are each mapped to tasks.
- Placeholder scan: no unresolved placeholders are present; every code step names exact files, commands, and expected outcomes.
- Type consistency: endpoint and live-inspection output keys match: `recovery_score`, `recovery_tier`, `score_components`, `evidence`, `recovery_rollups`, `source_health_summary`, and `truth_boundaries`.
