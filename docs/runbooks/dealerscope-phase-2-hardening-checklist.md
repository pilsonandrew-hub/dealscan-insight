# DealerScope Phase 2 Hardening Checklist

Use this with [docs/runbooks/dealerscope-phase-2-hardening-roadmap.md](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/docs/runbooks/dealerscope-phase-2-hardening-roadmap.md).

This is the execution copy. If a box cannot be checked with evidence, it is not done.

## Global Rules

- P2 and P3 do not begin until every P0 and P1 exit artifact exists.
- Every item needs an owner, artifact, and exit call.
- “Green enough” is not a criterion.
- If a proof step fails, stop, record the failure, and reopen the parent item.

## Required Exit Artifacts Before P2 Or P3

- [ ] P0 artifact: stale-secret rejection proof captured.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: live request record shows retired secret rejected with `401`.
- [ ] P0 artifact: current-secret replay proof captured.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: live request record shows current secret accepted and `ignored_replay` with no duplicate landing.
- [ ] P0 artifact: pager mode decision captured from the actual overnight runner.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: GitHub Actions run URL and Telegram result or explicit dry-run retention with named approver.
- [ ] P0 artifact: audit-surface durability result captured.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: forced audit-write failure either lands through fallback or fails loudly and pages.
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

- [ ] Add or update the repo-owned proof flow for active secret posture.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: `runtime-artifacts/webhook-secret-proof.json` exists, `scripts/run_ingest_rollout_preflight.py` prints the active-secret fingerprint and previous-secret posture, and the artifact posture matches the current runtime env.
- [ ] Red-team the retired secret after deploy.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: `runtime-artifacts/webhook-secret-proof.json` records `retired_secret_rejected=passed` with timestamp, payload hash, safe fingerprint, and `401`.
- [ ] Red-team the current secret with replay semantics.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: `runtime-artifacts/webhook-secret-proof.json` records `current_secret_accepted=passed` and `replay_suppressed=passed`; the replay response is `ignored_replay` / `replay_ignored=true`.
- [ ] Remove `APIFY_WEBHOOK_SECRET_PREVIOUS` after overlap is over.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: post-overlap proof run uses `--expect-previous-secret-absent` and records `previous_secret_absent=passed`; startup logs and preflight both show previous secret state `absent`.
- [ ] Record exact timestamps, deploy SHA, and operator decision.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: the proof artifact contains exact timestamps and deploy SHA, and the closeout ledger links that artifact plus the startup-log evidence.

### P0.2 Audit Surfaces Durable

- [ ] Identify every ingest path that can continue after audit-write failure.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: list includes replay lookup, `webhook_log` insert/update, and every critical `db_save` write to `ingest_delivery_log`.
- [ ] Implement fallback or fail-loud behavior for each path.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: no best-effort continuation remains on the critical ingest audit path; legal outcomes are durable direct-Postgres fallback with explicit `audit_status=fallback` or `503 Critical ingest audit write failed`.
- [ ] Add automated tests that force audit-write failure.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: tests prove rows still land durably or the request fails loudly; replay lookup failure is covered too.
- [ ] Update reconciliation docs to describe the hardened audit behavior.
  - Evidence / artifact:
  - Owner:
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

- [ ] Review current `/api/ingest/apify` protection posture.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: current auth, replay, and rate-limit behavior documented.
- [ ] Add route-specific rate limiting or edge restriction for `/api/ingest/apify`.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: ingest route has stricter protection than generic API traffic.
- [ ] Fix forwarded-IP parsing and verify behavior under proxy headers.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: spoofed `X-Forwarded-For` chain cannot bypass the intended client-IP logic.
- [ ] Test Redis-down behavior for rate limiting.
  - Evidence / artifact:
  - Owner:
  - Exit criteria: Redis outage does not silently erase the ingest route’s abuse boundary.

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
