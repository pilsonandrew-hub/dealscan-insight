# Ingestion Observability Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DealerScope source-run and parse-event health first-class database truth instead of reconstructing incidents from Telegram and workflow logs.

**Architecture:** Add three schema-backed observability surfaces: `scrape_runs` for one row per Apify/source run, `parse_events` for item-level parse/save/skip facts, and `source_health_daily` as an aggregate view over `scrape_runs`. Feed them from the existing webhook ingest lifecycle, then expose them in preflight and live-inspection proof.

**Tech Stack:** FastAPI ingest router, Supabase/Postgres migrations, existing Python pytest suite, GitHub Actions deployment/proof workflows.

---

### Task 1: Schema Contract

**Files:**
- Create: `supabase/migrations/20260613_ingestion_observability.sql`
- Modify: `scripts/run_ingest_rollout_preflight.py`
- Test: `tests/test_ingest_rollout_preflight.py`

- [ ] Write a failing preflight test requiring `scrape_runs`, `parse_events`, and `source_health_daily`.
- [ ] Add the migration with table/view definitions, indexes, RLS service-role policies, and PostgREST schema reload notify.
- [ ] Update preflight required-column checks.
- [ ] Run the preflight tests to prove the contract.

### Task 2: Ingest Writes

**Files:**
- Modify: `webapp/routers/ingest.py`
- Test: existing ingest tests plus a focused new test if needed

- [ ] Write a failing test proving a run summary writes to `scrape_runs`.
- [ ] Write a failing test proving parse/skip/save events write to `parse_events`.
- [ ] Implement minimal helper functions using the existing `supabase_client` and direct Postgres fallback pattern where appropriate.
- [ ] Wire run start, run completion, fetch/dataset failures, source-quality-proof skips, normalization failures, and db-save outcomes.
- [ ] Run focused ingest tests.

### Task 3: Proof Surface

**Files:**
- Modify: `scripts/supabase_live_inspection.py`
- Test: `tests/test_supabase_live_inspection.py`

- [ ] Write a failing test proving run-id live inspection includes sanitized `scrape_runs`, `parse_events`, and `source_health_daily` aggregates.
- [ ] Add read-only aggregate summaries without raw payloads, URLs, VINs, or secrets.
- [ ] Run live-inspection tests.

### Task 4: End-to-End Verification

**Files:**
- All files above

- [ ] Run `git diff --check`.
- [ ] Run focused tests for ingest, preflight, reconciliation, and live inspection.
- [ ] Run full local suite.
- [ ] Commit, open PR, wait for CI/Cursor/Bugbot/Vercel.
- [ ] Apply migration before/with merge as appropriate.
- [ ] Merge only after checks pass.
- [ ] Verify Railway deploy, `/healthz`, live schema proof, and a fresh actor run with observed `scrape_runs` and `parse_events` rows.
