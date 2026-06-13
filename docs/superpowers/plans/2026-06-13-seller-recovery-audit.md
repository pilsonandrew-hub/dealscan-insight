# Seller Recovery Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only internal seller recovery audit that turns live ingestion/source truth into sanitized, evidence-backed listing recovery diagnostics.

**Architecture:** Keep the implementation inside `webapp/routers/internal.py` beside existing governed truth surfaces. Add pure helper functions for section aggregation and candidate classification, then expose them through `GET /api/internal/seller-recovery-audit`. Extend `scripts/supabase_live_inspection.py` only enough to prove the live schema/aggregate surface without printing sensitive row payloads.

**Tech Stack:** FastAPI, Supabase Python client patterns already used in `webapp/routers/internal.py`, pytest, existing read-only live inspection script.

---

### Task 1: Internal Audit Builder

**Files:**
- Modify: `webapp/routers/internal.py`
- Test: `tests/test_internal_pipeline_truth.py`

- [ ] **Step 1: Write failing tests for seller recovery audit aggregation**

Add tests that monkeypatch `internal.supabase_client` with fake `source_health_daily`, `ingest_delivery_log`, `parse_events`, and `opportunities` rows. Assert that the result includes source health, listing-quality counts, value-leak candidates, and unsupported dimensions. Assert serialized output excludes `vin`, `listing_url`, `description`, and raw payload data.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: fails because `build_seller_recovery_audit` does not exist.

- [ ] **Step 3: Implement the minimal builder helpers**

Add pure helpers in `webapp/routers/internal.py`:

- `_safe_section_rows(...)`
- `_seller_recovery_reason_counts(...)`
- `_candidate_recovery_reasons(...)`
- `_seller_recovery_candidates(...)`
- `build_seller_recovery_audit()`

Keep all output aggregate or sanitized. Candidate rows may include `id`, `source_site`, `year`, `make`, `model`, `dos_score`, `gross_margin`, `bid_headroom`, `pricing_maturity`, and deterministic reasons.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

Expected: seller recovery audit tests pass with existing internal tests.

### Task 2: Internal Endpoint

**Files:**
- Modify: `webapp/routers/internal.py`
- Test: `tests/test_internal_pipeline_truth.py`

- [ ] **Step 1: Write failing endpoint/auth tests**

Add tests that missing `X-Internal-Secret` still rejects through the existing guard and that the route function returns `build_seller_recovery_audit()` when authorized.

- [ ] **Step 2: Run tests and verify RED**

Run the same internal test file. Expected: fails because `seller_recovery_audit` route function does not exist.

- [ ] **Step 3: Add route**

Add:

```python
@router.get("/seller-recovery-audit", include_in_schema=False)
def seller_recovery_audit(x_internal_secret: Optional[str] = Header(None, alias="X-Internal-Secret")) -> dict[str, Any]:
    verify_internal_secret(x_internal_secret)
    return build_seller_recovery_audit()
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py -q
```

### Task 3: Live Inspection Proof

**Files:**
- Modify: `scripts/supabase_live_inspection.py`
- Test: `tests/test_supabase_live_inspection.py`

- [ ] **Step 1: Write failing script proof tests**

Add a test that `_safe_truth_audit()` includes a `seller_recovery_audit` section with aggregate candidate counts and unsupported dimensions from fake rows. Assert no sensitive fields appear in serialized output.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q
```

Expected: fails because `_safe_truth_audit()` has no seller recovery section.

- [ ] **Step 3: Add sanitized live proof aggregation**

Reuse deterministic candidate classification logic locally in the script or add script-local helpers. Do not make the script call the HTTP endpoint; it should remain a read-only Supabase proof path.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_supabase_live_inspection.py -q
```

### Task 4: Verification, PR, Deploy, Live Proof

**Files:**
- All modified files

- [ ] **Step 1: Run focused suite**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests/test_internal_pipeline_truth.py tests/test_supabase_live_inspection.py tests/test_ingest_rollout_preflight.py -q
```

- [ ] **Step 2: Run full local suite**

```bash
/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.venv/bin/python -m pytest tests -q
```

- [ ] **Step 3: Commit and open PR**

Commit only this branch’s files and open a PR. Do not include dirty primary checkout state.

- [ ] **Step 4: Wait for CI/Cursor/Vercel**

All required checks must pass before merge.

- [ ] **Step 5: Merge, verify Railway health, and run live proof**

After deploy, run `/healthz`, the internal endpoint, and/or `scripts/supabase_live_inspection.py` against production with aggregate-only output.

- [ ] **Step 6: Close only if live proof passes**

Send Andrew a concise closeout only if production proves the surface. If the endpoint or live proof is degraded, keep the issue open and remediate.
