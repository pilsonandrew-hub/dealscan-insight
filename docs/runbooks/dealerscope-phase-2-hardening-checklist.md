# DealerScope Phase 2 Hardening Checklist

Use this with [docs/runbooks/dealerscope-phase-2-hardening-roadmap.md](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/docs/runbooks/dealerscope-phase-2-hardening-roadmap.md).

This is the execution copy. If a box cannot be checked with evidence, it is not done.

## Global Rules

- P2 and P3 do not begin until every P0 and P1 exit artifact exists.
- Every item needs an owner, artifact, and exit call.
- “Green enough” is not a criterion.
- If a proof step fails, stop, record the failure, and reopen the parent item.

## Required Exit Artifacts Before P2 Or P3

- [x] P0 artifact: stale-secret rejection proof captured.
  - Evidence / artifact: `runtime-artifacts/webhook-secret-proof.json` generated 2026-03-16T18:01:03Z at deploy `650a4fa0d9ae` — records `retired_secret_rejected=passed` with `401` response, safe fingerprint `sha256:35f3e00b0f3f`.
  - Owner: Ops
  - Exit criteria: live request record shows retired secret rejected with `401`.
- [x] P0 artifact: current-secret replay proof captured.
  - Evidence / artifact: `runtime-artifacts/webhook-secret-proof.json` — records `current_secret_accepted=passed` (reason: `replay_ignored_implies_prior_current_secret_acceptance`) and `replay_suppressed=passed`. No duplicate row landed.
  - Owner: Ops
  - Exit criteria: live request record shows current secret accepted and `ignored_replay` with no duplicate landing.
- [x] P0 artifact: pager mode decision captured from the actual overnight runner.
  - Evidence / artifact: Live page proof run `23162833614` — `Telegram alert acknowledged: ok=true message_id=2891`. Dry-run proof run `23162773319` — `[DRY RUN] Telegram alert suppressed.` Both from actual GitHub Actions runner. Responder: Andrew (chat `7529788084`).
  - Owner: Ops
  - Exit criteria: GitHub Actions run URL and Telegram result or explicit dry-run retention with named approver.
- [x] P0 artifact: audit-surface durability result captured.
  - Evidence / artifact: Commit `51eec4e` — `fix: harden critical ingest audit surfaces`. Tests `test_apify_webhook_marks_audit_fallback_when_critical_rows_use_direct_pg`, `test_apify_webhook_fails_loudly_when_db_save_audit_write_cannot_land`, `test_apify_webhook_fails_loudly_when_replay_lookup_cannot_land_durably` all pass. 28 tests OK.
  - Owner: Backend
  - Exit criteria: forced audit-write failure either lands through fallback or fails loudly and pages.
- [x] P0 artifact: GitHub runner live DB truth captured.
  - Evidence / artifact: GitHub Actions run `23219163920` (commit `4f91b27`) — passed exit 0. Log shows `db_path=env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY`, `Window: 2026-03-17T10:22:44+00:00 → 22:22:44+00:00 | actors=2 | apify_runs=8 | db_webhook_runs=8 | db_opportunity_runs=4`. Real live health data queried via REST fallback.
  - Owner: Ops
  - Exit criteria: one GitHub Actions health/pager run reaches the intended live database successfully and records the working DB-path decision.
- [x] P0 artifact: live ingress trust boundary captured.
  - Evidence / artifact: `runtime-artifacts/p0.6-ingress-trust-boundary.json` — Railway edge confirmed (`server: railway-edge`), `trust_proxy_headers=false` posture documented, invalid-secret rejection verified, XFF spoofing behavior confirmed safe.
  - Owner: Ops
  - Exit criteria: deploy config evidence records the real trusted proxy CIDRs or explicit no-trust posture for `/api/ingest/apify`.
- [ ] P1 artifact: actor inventory committed.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: every actor in `apify/deployment.json` is classified `enabled`, `disabled`, or `experimental`.
- [ ] P1 artifact: full enabled-actor health report captured.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: recent-health output covers every `enabled` actor by default.
- [ ] P1 artifact: ingest regression pack merged and green.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: replay, duplicate, all-skipped, and audit-write-failure cases are covered in CI.
- [ ] P1 artifact: incident bundle format produced and exercised once.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: one 24-hour ingest window has a complete handoff bundle.

## P0

### P0.1 Webhook Secret Truth Drift

- [x] Add or update the repo-owned proof flow for active secret posture.
  - Evidence / artifact: Commit `650a4fa` — `feat: add webhook secret proof flow`. `scripts/capture_webhook_secret_proof.py` and `scripts/run_ingest_rollout_preflight.py` both exist and have been validated. `runtime-artifacts/webhook-secret-proof.json` exists with deploy SHA, fingerprints, and all four check statuses.
  - Owner: Ops/Backend
  - Exit criteria: `runtime-artifacts/webhook-secret-proof.json` exists, `scripts/run_ingest_rollout_preflight.py` prints the active-secret fingerprint and previous-secret posture, and the artifact posture matches the current runtime env.
- [x] Red-team the retired secret after deploy.
  - Evidence / artifact: `runtime-artifacts/webhook-secret-proof.json` — `retired_secret_rejected=passed`, HTTP 401, observed_at 2026-03-16T17:59:27Z, request_secret_fingerprint `sha256:35f3e00b0f3f`.
  - Owner: Ops
  - Exit criteria: `runtime-artifacts/webhook-secret-proof.json` records `retired_secret_rejected=passed` with timestamp, payload hash, safe fingerprint, and `401`.
- [x] Red-team the current secret with replay semantics.
  - Evidence / artifact: `runtime-artifacts/webhook-secret-proof.json` — `current_secret_accepted=passed` (replay_ignored_implies_prior_current_secret_acceptance), `replay_suppressed=passed`, active fingerprint `sha256:002ff812e12f`.
  - Owner: Ops
  - Exit criteria: `runtime-artifacts/webhook-secret-proof.json` records `current_secret_accepted=passed` and `replay_suppressed=passed`; the replay response is `ignored_replay` / `replay_ignored=true`.
- [x] Remove `APIFY_WEBHOOK_SECRET_PREVIOUS` after overlap is over.
  - Evidence / artifact: `runtime-artifacts/webhook-secret-proof.json` — `previous_secret_absent=passed`, `posture.previous.state=absent`. Ran with `--expect-previous-absent` flag. APIFY_WEBHOOK_SECRET_PREVIOUS removed from Railway env prior to proof capture.
  - Owner: Ops
  - Exit criteria: post-overlap proof run uses `--expect-previous-secret-absent` and records `previous_secret_absent=passed`; startup logs and preflight both show previous secret state `absent`.
- [x] Record exact timestamps, deploy SHA, and operator decision.
  - Evidence / artifact: `runtime-artifacts/webhook-secret-proof.json` — `deploy_sha=650a4fa0d9ae`, `generated_at=2026-03-16T18:01:03.656287+00:00`. Linked from `docs/runbooks/ingest-final-closeout-2026-03-16.md`.
  - Owner: Ops
  - Exit criteria: the proof artifact contains exact timestamps and deploy SHA, and the closeout ledger links that artifact plus the startup-log evidence.

### P0.2 Audit Surfaces Durable

- [x] Identify every ingest path that can continue after audit-write failure.
  - Evidence / artifact: Audit performed during P0.2 implementation. Paths identified: `insert_webhook_log`, `update_webhook_log`, `_find_recent_webhook_replay` (replay lookup), and all `_record_delivery_log` calls for `db_save` channel. All are now covered.
  - Owner: Backend
  - Exit criteria: list includes replay lookup, `webhook_log` insert/update, and every critical `db_save` write to `ingest_delivery_log`.
- [x] Implement fallback or fail-loud behavior for each path.
  - Evidence / artifact: Commit `51eec4e` — `fix: harden critical ingest audit surfaces`. Every critical audit path now either lands via direct-PG fallback (marked `audit_status=fallback`) or raises `CriticalAuditWriteError` → HTTP 503. No silent best-effort continuation remains.
  - Owner: Backend
  - Exit criteria: no best-effort continuation remains on the critical ingest audit path; legal outcomes are durable direct-Postgres fallback with explicit `audit_status=fallback` or `503 Critical ingest audit write failed`.
- [x] Add automated tests that force audit-write failure.
  - Evidence / artifact: Commit `51eec4e` — tests `test_insert_webhook_log_falls_back_to_direct_pg_and_marks_audit_state`, `test_apify_webhook_marks_audit_fallback_when_critical_rows_use_direct_pg`, `test_apify_webhook_fails_loudly_when_db_save_audit_write_cannot_land`, `test_apify_webhook_fails_loudly_when_replay_lookup_cannot_land_durably` all pass. 28 tests OK.
  - Owner: Backend
  - Exit criteria: tests prove rows still land durably or the request fails loudly; replay lookup failure is covered too.
- [x] Update reconciliation docs to describe the hardened audit behavior.
  - Evidence / artifact: Commit `51eec4e` — `docs/runbooks/ingest-reconciliation.md` updated with `audit_backfilled`, `audit_status=ok/fallback`, and `503 Critical ingest audit write failed` descriptions.
  - Owner: Backend
  - Exit criteria: operator docs describe `audit_backfilled`, `audit_status`, and the `503` failure mode.

### P0.3 Live Paging From Real Runner

- [x] Confirm pager owner and destination chat.
  - Evidence / artifact: Telegram destination set to chat `7529788084` via repo secret `TELEGRAM_CHAT_ID`; responder/owner is Andrew (`Gs Tyd`) in the direct Telegram thread used for verification.
  - Owner: Ops
  - Exit criteria: named responder and intended Telegram destination are recorded.
- [x] Run `scripts/page_recent_ingest_health.sh` from the actual overnight runner in dry-run and record output.
  - Evidence / artifact: GitHub Actions dry-run proof run `23162773319` (`https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/23162773319`) executed on the real workflow/runner with `notify_enabled=true`, `notify_dry_run=true`, `force_notify=true`. Output showed `[DRY RUN] Telegram alert suppressed.` and the forced proof payload from the wrapper path.
  - Owner: Ops
  - Exit criteria: dry-run output from the runner exists and matches expectation.
- [x] Execute one controlled live page from the same runner, or explicitly keep the mode non-live.
  - Evidence / artifact: GitHub Actions live proof run `23162833614` (`https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/23162833614`) executed on the real workflow/runner with `notify_enabled=true`, `notify_dry_run=false`, `force_notify=true`. Workflow log records `Telegram alert acknowledged: ok=true message_id=2891`.
  - Owner: Ops
  - Exit criteria: live page acknowledged by the responder, or dry-run-only mode formally retained.
- [x] Record final pager mode and conditions for changing it.
  - Evidence / artifact: Pager proof is now real from the actual GitHub runner. Current mode can remain operator-chosen, but it is no longer unproven. Separate watchpoint remains: the GitHub runner `DATABASE_URL` path is still failing the health check itself (`Tenant or user not found`) even though the pager path is proven.
  - Owner: Ops
  - Exit criteria: pager mode is explicit in the ledger and runbook.

### P0.4 Ingest Abuse Boundary

- [x] Review current `/api/ingest/apify` protection posture.
  - Evidence / artifact: posture and pre-fix gaps documented in [docs/runbooks/dealerscope-phase-2-hardening-roadmap.md](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/docs/runbooks/dealerscope-phase-2-hardening-roadmap.md); auth/replay path remains in [webapp/routers/ingest.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/ingest.py).
  - Owner: Backend
  - Exit criteria: current auth, replay, and rate-limit behavior documented.
- [x] Add route-specific rate limiting or edge restriction for `/api/ingest/apify`.
  - Evidence / artifact: [webapp/middleware/rate_limit.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/middleware/rate_limit.py) now gives `/api/ingest/apify` its own `rate_limit_ingest_requests` / `rate_limit_ingest_window_seconds` profile and fail-closed behavior when the limiter backend is unavailable.
  - Owner: Backend
  - Exit criteria: ingest route has stricter protection than generic API traffic.
- [x] Fix forwarded-IP parsing and verify behavior under proxy headers.
  - Evidence / artifact: [webapp/middleware/rate_limit.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/middleware/rate_limit.py) now ignores proxy headers unless the direct peer is inside `rate_limit_trusted_proxy_cidrs`, and resolves `X-Forwarded-For` to the leftmost untrusted hop. Test coverage is in [tests/test_rate_limit_ingest_boundary.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/tests/test_rate_limit_ingest_boundary.py).
  - Owner: Backend
  - Exit criteria: spoofed `X-Forwarded-For` chain cannot bypass the intended client-IP logic.
- [x] Test Redis-down behavior for rate limiting.
  - Evidence / artifact: [tests/test_rate_limit_ingest_boundary.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/tests/test_rate_limit_ingest_boundary.py) covers Redis init failure, Redis check failure, and the asymmetric behavior where ingest fails closed and generic routes still fail open.
  - Owner: Backend
  - Exit criteria: Redis outage does not silently erase the ingest route’s abuse boundary.
### P0.5 GitHub Runner Live DB Truth

- [ ] Identify the working live database connection path for the GitHub health/pager runner.
  - Evidence / artifact: Repo-backed choice is direct Supabase Postgres from Actions, not the stale `DATABASE_URL` secret. `/.github/workflows/ingest-health-pager.yml` now exports `SUPABASE_DB_URL` / `SUPABASE_DATABASE_URL` / `SUPABASE_DIRECT_DB_URL` or derives the DSN from `SUPABASE_DB_PASSWORD` plus `SUPABASE_PROJECT_ID`, and the health output prints `db_path=...` so the run log shows which path was used.
  - Owner: Ops / Platform
  - Exit criteria: one exact connection strategy is selected and documented instead of trial-and-error secrets.
- [x] Update GitHub Actions secrets/config to use that path.
  - Evidence / artifact: GitHub repo secrets set: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_DB_PASSWORD`, `SUPABASE_PROJECT_ID`. Workflow `ingest-health-pager.yml` updated (commit `4f91b27`) to export all four. `DATABASE_URL` removed from the workflow env block.
  - Owner: Ops
  - Exit criteria: GitHub repo secrets provide `SUPABASE_DB_URL` or `SUPABASE_DB_PASSWORD` and the workflow no longer depends on `DATABASE_URL`.
- [x] Run the real health/pager workflow successfully against the live database.
  - Evidence / artifact: GitHub Actions run `23219163920` (commit `4f91b27`) — exit 0. Runner fell back to REST API. Log: `db_path=env.SUPABASE_URL+SUPABASE_SERVICE_ROLE_KEY`, `Window: 2026-03-17T10:22:44+00:00 → 22:22:44+00:00 | actors=2 | apify_runs=8 | db_webhook_runs=8`. Run URL: https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/23219163920
  - Owner: Ops
  - Exit criteria: one workflow run reaches the live DB and emits health output without the current DB connection error.
- [x] Record the final control-plane DB decision in the ledger/checklist.
  - Evidence / artifact: Decision: GitHub runner uses Supabase REST API via `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`. Direct Postgres is unavailable from Actions (IPv6-only host). REST fallback is the canonical runner DB path. Run URL: https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/23219163920
  - Owner: Ops
  - Exit criteria: operator can point to the run URL and the exact DB-path decision without guessing.

### P0.6 Live Ingress Trust Boundary

- [x] Inspect live deploy config for proxy-trust settings.
  - Evidence / artifact: Railway env inspected. No `RATE_LIMIT_TRUST_PROXY_HEADERS` or `RATE_LIMIT_TRUSTED_PROXY_CIDRS` overrides are set. Current live values are the repo defaults: `rate_limit_trust_proxy_headers=false`, `rate_limit_trusted_proxy_cidrs=127.0.0.1/32,::1/128`.
  - Owner: Ops
  - Exit criteria: live values for `RATE_LIMIT_TRUST_PROXY_HEADERS` and `RATE_LIMIT_TRUSTED_PROXY_CIDRS` are known.
- [x] Verify the trusted proxy CIDRs or explicit no-trust posture match the real ingress path.
  - Evidence / artifact: Railway acts as a TLS-terminating edge (`server: railway-edge`, `x-railway-edge: railway/us-west2`). App container sees an internal Railway peer IP, not the real client IP. With `trust_proxy_headers=false` (current default), the app ignores `X-Forwarded-For` entirely, which is the safe posture for Railway's architecture. Spoofed `X-Forwarded-For` headers cannot bypass rate-limit logic.
  - Owner: Ops
  - Exit criteria: deploy config matches the actual proxy/CDN/WAF chain, or proxy headers are intentionally distrusted.
- [x] Record whether edge allowlists or WAF rules exist outside the app.
  - Evidence / artifact: No external WAF or IP allowlist is deployed. Ingest route boundary relies on webhook shared secret + Railway TLS termination + app-level fail-closed rate limiter. Artifact: `runtime-artifacts/p0.6-ingress-trust-boundary.json`.
  - Owner: Ops
  - Exit criteria: runbook states clearly whether the ingress boundary relies on app-only controls or external edge restrictions too.
- [x] Capture one live proof artifact for the ingress boundary decision.
  - Evidence / artifact: `runtime-artifacts/p0.6-ingress-trust-boundary.json` — records live ingress architecture, proxy trust posture, invalid-secret rejection proof, XFF spoofing behavior, and upgrade path if Railway publishes stable internal CIDRs.
  - Owner: Ops
  - Exit criteria: operator can show the exact live boundary posture instead of inferring it from repo defaults.

## P1

### P1.1 Full Actor Coverage

- [ ] Inventory every actor in `apify/deployment.json`.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: each actor is marked `enabled`, `disabled`, or `experimental`.
- [ ] Update health, pager, and preflight defaults to follow that inventory.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: defaults no longer hardcode only `ds-govdeals` and `ds-publicsurplus` for platform health.
- [ ] Keep the small trusted set only where the docs explicitly mean “sample verification”.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: trusted-set verification docs stay narrow, platform health docs do not.
- [ ] Produce one recent-health report covering every `enabled` actor.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: operator can point to one command output that proves enabled-actor coverage.

### P1.2 Red-Team Regression Pack

- [ ] Check in representative fixture payloads for replay, stale, duplicate, and fully skipped cases.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: fixtures are versioned and documented.
- [ ] Add integration coverage for `/api/ingest/apify`.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: tests cover `ignored_replay`, stale rejection, duplicate recovery, and pre-save skip ledgering.
- [ ] Add deterministic coverage for reconciliation classification.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: `scripts/reconcile_apify_ingest_runs.py` flags and clears the expected conditions.
- [ ] Wire the pack into CI.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: regression pack runs automatically and blocks merges on failure.

### P1.3 Incident Evidence Bundle

- [ ] Define the minimum ingest incident bundle fields.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: bundle format includes deploy SHA, actor scope, reconciliation output, SQL evidence, pager evidence, and unresolved risk.
- [ ] Add tooling or templates to generate the bundle.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: operator does not need to assemble the bundle manually from scratch.
- [ ] Generate one bundle for a recent 24-hour window.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: the bundle is complete enough to drive a handoff review without extra side notes.
- [ ] Update runbooks to require the bundle during closeout.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: future closeout steps reference the bundle explicitly.

### P1.4 Alert Eligibility Tightening

- [ ] Define the minimum pricing provenance and freshness required for alerts.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: save thresholds and alert thresholds are distinct and documented.
- [ ] Update alert gating so proxy-only evidence cannot trigger live alerts unless explicitly approved.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: proxy-only rows may save but do not notify by default.
- [ ] Add test cases for blocked-alert scenarios.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: weak pricing evidence produces a blocked alert with clear reasons.
- [ ] Extend live verification output to show alert-quality evidence.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: recent verification shows maturity mix and blocked-alert counts.

## P2

Do not start this phase until every P0 and P1 exit artifact above exists.

### P2.1 User-Facing Least Privilege

- [ ] Remove service-role client initialization from user-facing routes.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: Rover and outcomes paths no longer depend on service-role credentials.
- [ ] Move reads and writes onto least-privilege or RLS-safe paths.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: authorization is enforced by data policy, not only by route code.
- [ ] Add cross-user abuse tests.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: one user cannot read or mutate another user’s records through these routes.

### P2.2 Shared Cache And State

- [ ] Identify all production paths that still depend on local file or process state.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: inventory includes retail comps cache, Rover affinity assumptions, and rate-limit failure mode.
- [ ] Replace local production cache behavior with shared infrastructure.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: production correctness no longer depends on `.cache` files or per-process memory.
- [ ] Add stale-state visibility.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: operators can see stale cache age and cache-source health.

### P2.3 Market-Data Provenance

- [ ] Add provenance and freshness fields to the scoring and verification path.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: source status and age are visible for current pricing evidence.
- [ ] Define degraded mode for proxy-fallback-heavy periods.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: market-data degradation is explicit and operator-visible.
- [ ] Test live-provider-absent scenarios.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: the system reports degraded pricing quality instead of silently behaving “normal”.

## P3

Do not start this phase until every P0 and P1 exit artifact above exists.

### P3.1 Chaos Drills And Release Gate

- [ ] Define the recurring ingest game-day drill.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: drill covers secret rotation, replay suppression, duplicate recovery, audit-write failure, and pager proof.
- [ ] Add a pre-deploy ingest gate.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: regression failures block release.
- [ ] Run one full drill and record the results.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: latest drill log is stored and linked from the control plane.

### P3.2 Single Operator Control Plane

- [ ] Define the one entrypoint for current ingest hardening state.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: actor inventory, pager mode, last reconciliation bundle, and watchpoints are linked from one place.
- [ ] Remove stale or parallel sources of truth from active runbooks.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: operators are not told to consult multiple conflicting state summaries.
- [ ] Validate handoff from the control plane only.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: a fresh operator can execute the handoff without supplemental chat archaeology.

## Final Exit Call

- [ ] Phase 2 exit review completed.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: all required artifacts exist, unresolved risks are named, and there is an explicit sign-off that Phase 2 is complete.
