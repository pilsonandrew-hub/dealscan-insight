# Ingest Deploy-State Snapshot — 2026-03-15

Snapshot taken: 2026-03-15 late evening PT

## Summary

Local repo hardening work is **ahead of both `origin/main` and the live Railway service**.

- **Local `HEAD`:** `5bb3690` — `feat: add ingest rollout preflight`
- **`origin/main`:** `6926f5b` — `fix: defer canonical duplicate updates until save succeeds`
- **Live Railway deploy:** `6926f5b` — deployed at `2026-03-15T19:05:03.943Z`

This means the latest seven hardening commits are currently **repo-only** and **not yet live**.

## Repo / Deploy Drift

### Local commits not yet on `origin/main`
1. `5bb3690` — `feat: add ingest rollout preflight`
2. `d171aaa` — `fix: harden webhook secret rotation flow`
3. `d19ec6d` — `fix: recover canonical dedupe races`
4. `cc1af9e` — `fix: harden apify webhook replay handling`
5. `42b0294` — `fix: broaden direct pg fallback coverage`
6. `fe7b55c` — `feat: add ingest health pager wrapper`
7. `a6a3ff7` — `feat: add ingest reconciliation tooling`

### Current live Railway deploy
- **Service:** `dealscan-insight`
- **Deployment ID:** `1101c556-e7af-4c54-bc82-0643a2e4039c`
- **Status:** `SUCCESS`
- **Created:** `2026-03-15T19:05:03.943Z`
- **Commit hash:** `6926f5b2e2c00c2b86f458a8ba48d2cb4653c44b`
- **Commit message:** `fix: defer canonical duplicate updates until save succeeds`

## What is definitely live
Everything through and including:
- `6926f5b` — canonical duplicate updates deferred until save success
- `84316ad` — ingest delivery ledger for replay recovery
- `73eb3c2` — timezone import for timestamp normalization
- `674f597` — ingest identity / replay semantics hardening
- `d2b3e72` — replay and save accounting hardening
- `d4b7ee3` — ingest observability improvements
- `292174f` — relative auction-end normalization
- `3f0de77` — direct DB fallback for ingest saves
- `3c2ac1a` — dataset-id recovery from actor runs

## What is NOT live yet
These are implemented locally but not yet reflected in the live Railway deploy:
- reconciliation tooling
- ingest health pager wrapper / scheduled GitHub workflow
- broadened direct-PG fallback coverage for generic Supabase write failures
- webhook replay hardening (`ignored_replay`, optional staleness checks)
- canonical dedupe race recovery (`saved_*_duplicate` statuses)
- dual-secret webhook rotation support and env validation hardening
- rollout preflight and tonight rollout runbook

## Operational meaning
Do **not** assume the current live service includes the newest hardening beyond `6926f5b`.

Before claiming the system reflects today’s full hardening sprint, we still need:
1. push / publish the seven local commits
2. deploy latest `main`
3. rerun rollout preflight
4. perform baseline live validation on the deployed build

## Immediate next step
Use this snapshot as the control artifact, then move to:
1. fix hard production blockers (`SECRET_KEY`, webhook secret posture, preflight health gate robustness)
2. deploy the latest hardened stack
3. rerun preflight and live validation
