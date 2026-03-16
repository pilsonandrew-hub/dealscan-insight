# DealerScope Phase 2 Hardening Roadmap

This is the Phase 2 hardening plan after the March 15-16 ingest recovery, red-team audit, and closeout.

The immediate incident fixes are in place. That is not the same thing as a hardened system.

The repo evidence says the current state is:

- The live closeout is green for `ds-govdeals` and `ds-publicsurplus`, not for the full actor inventory in [apify/deployment.json](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/apify/deployment.json).
- Pager tooling exists, but the final closeout kept it in dry-run because a live Telegram send from the actual overnight runner was not intentionally proven in [docs/runbooks/ingest-final-closeout-2026-03-16.md](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/docs/runbooks/ingest-final-closeout-2026-03-16.md).
- Reconciliation depends on `webhook_log` and `ingest_delivery_log`, while the ingest route still treats several write failures to those audit surfaces as non-fatal in [webapp/routers/ingest.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/ingest.py).
- The rate limiter fails open when Redis is unavailable and has no ingest-specific control in [webapp/middleware/rate_limit.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/middleware/rate_limit.py).
- User-facing routers still initialize broad Supabase clients in [webapp/routers/rover.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/rover.py) and [webapp/routers/outcomes.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/outcomes.py).
- Pricing evidence still leans on proxy and local cache behavior in [backend/ingest/manheim_market.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/manheim_market.py) and [backend/ingest/retail_comps.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/retail_comps.py).

## Sequencing Rule

P0 and P1 are blocking.

P2 and P3 do not begin until the P0 and P1 exit artifacts exist and are attached to the hardening ledger. No exceptions, no “we basically did it”.

Required P0 exit artifacts:

- A live stale-secret rejection proof with exact timestamp, request context, and result.
- A live current-secret replay proof showing `ignored_replay` with no duplicate landing.
- A pager mode decision record backed by evidence from the actual overnight runner.
- A durable audit-surface test result showing how `webhook_log` and `ingest_delivery_log` behave during write failures.

Required P1 exit artifacts:

- An actor inventory with every scheduled actor classified as `enabled`, `disabled`, or `experimental`.
- A recent-health report covering every `enabled` actor, not only the two trusted ones.
- A regression pack proving replay, duplicate recovery, all-skipped runs, and audit-write failures.
- A handoff bundle format that captures deploy SHA, reconciliation output, SQL evidence, and pager evidence for a run window.

## P0: Close The Proven Control Failures

### P0.1 Eliminate Webhook Secret Truth Drift

- Why it matters: the red-team audit already found that live secret truth can drift from operator intent because runtime config can differ from what the runbook says. The closeout and overnight roadmap both show how easy it was for stale secret acceptance to survive until explicitly challenged.
- Exact deliverable: add a repo-owned webhook boundary proof flow that records active-secret fingerprint, previous-secret posture, deploy SHA, payload hash, and red-team results after each rotation or env change. The local artifact path is `runtime-artifacts/webhook-secret-proof.json`, produced by `scripts/capture_webhook_secret_proof.py` and verified by `scripts/run_ingest_rollout_preflight.py`. Preflight must fail when the current runtime posture is not backed by a matching artifact.
- Proof of done: one recorded live run showing old secret rejected with `401`, current secret accepted, replay suppressed as `ignored_replay`, `APIFY_WEBHOOK_SECRET_PREVIOUS` absent, and startup logs showing the expected secret posture after deploy.
- Dependencies: Railway env access, deploy access, startup log access, [scripts/run_ingest_rollout_preflight.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/run_ingest_rollout_preflight.py), [backend/main.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/main.py), [webapp/routers/ingest.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/ingest.py).
- Risk if skipped: the system will claim a clean rotation while production is still trusting the wrong secret.
- Owner suggestion: Platform/Ops with Backend support.

### P0.2 Make Audit Surfaces Durable, Not Best-Effort

- Why it matters: reconciliation only works if `webhook_log` and the `db_save` rows in `ingest_delivery_log` are trustworthy. The old route logged several failures to those surfaces as warnings and kept moving. That recreated the same blind spot the red-team audit just exposed.
- Exact deliverable: critical audit paths must use durable direct-Postgres fallback or fail the request loudly. Cover `insert_webhook_log`, `update_webhook_log`, replay lookup, and every `db_save` delivery ledger write. When fallback is used, surface it explicitly in the response and durable audit row.
- Proof of done: automated tests that force Supabase audit-write failures and prove one of two outcomes only: audit rows still land through direct-Postgres fallback with explicit `audit_status=fallback`, or the request exits with `503 Critical ingest audit write failed`. No silent continuation.
- Dependencies: direct PG fallback decisions, schema stability for `webhook_log` and `ingest_delivery_log`, test harness for [webapp/routers/ingest.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/ingest.py).
- Risk if skipped: the next ingest outage will again produce missing evidence, and operators will waste time arguing about whether the app, Apify, or the database dropped the run.
- Owner suggestion: Backend.

### P0.3 Prove Live Paging From The Real Runner Or Keep It Dead

- Why it matters: the repo has a scheduled pager in [/.github/workflows/ingest-health-pager.yml](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.github/workflows/ingest-health-pager.yml), but the final closeout explicitly refused to claim live paging was proven. Dry-run is not an on-call system.
- Exact deliverable: execute one controlled live Telegram page from the exact runner that will own overnight paging, capture the GitHub Actions run URL and Telegram acknowledgment, then record the on-call destination and ownership. If that proof is not produced, hard-code the mode as observational and stop pretending it is operational paging.
- Proof of done: GitHub Actions run URL, `ok=true` plus `message_id` evidence from the wrapper path in [scripts/page_recent_ingest_health.sh](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/page_recent_ingest_health.sh), named responder, exact pager mode decision in the ledger.
- Dependencies: GitHub secrets/vars, Telegram destination confirmation, on-call owner.
- Risk if skipped: the first real overnight failure will reveal that the pager was theater.
- Owner suggestion: Ops / primary on-call.

### P0.4 Put A Real Abuse Boundary On `/api/ingest/apify`

- Why it matters: the ingest route is protected by a shared secret, but the middleware fails open when Redis is down and the route is not treated as a special boundary. The current IP extraction logic also trusts the last `X-Forwarded-For` hop, which is the wrong side of the chain for most proxy setups.
- Exact deliverable: add route-specific protection for `/api/ingest/apify` with a safe fallback when Redis is unavailable, correct forwarded-IP parsing, and edge or ingress restrictions where available. Log auth failures and rate-limit hits as first-class ingest security events.
- Proof of done: tests showing Redis-down behavior, spoofed header handling, and replay floods on `/api/ingest/apify`; live config evidence that the route has tighter controls than generic app traffic.
- Dependencies: [webapp/middleware/rate_limit.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/middleware/rate_limit.py), edge config, deploy access.
- Risk if skipped: noise, replay floods, or header spoofing can degrade the ingest boundary and bury the real signal during an incident.
- Owner suggestion: Platform/Ops with Backend implementation.

## P1: Expand From Incident Repair To Operable System

### P1.1 Stop Treating Two Actors As The Whole Platform

- Why it matters: the preflight, rollout docs, and closeout evidence are narrowly centered on `ds-govdeals` and `ds-publicsurplus`, while [apify/deployment.json](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/apify/deployment.json) contains additional scheduled actors. That is partial coverage, not platform coverage.
- Exact deliverable: create an actor inventory in repo with explicit status for every actor in deployment manifest: `enabled`, `disabled`, or `experimental`. Update health, preflight, pager, and reconciliation defaults to cover every `enabled` actor.
- Proof of done: preflight and recent-health output includes every `enabled` actor by default; runbooks stop hardcoding the two-source shortcut except where intentionally labeled as trusted-sample verification.
- Dependencies: owner decision on which actors are actually in production, [scripts/reconcile_apify_ingest_runs.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/reconcile_apify_ingest_runs.py), [scripts/run_ingest_rollout_preflight.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/run_ingest_rollout_preflight.py), [docs/live_small_set_verification.md](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/docs/live_small_set_verification.md).
- Risk if skipped: failures on “other” actors will stay invisible until bad data or missing inventory leaks into downstream behavior.
- Owner suggestion: Ops with Product/Backend sign-off.

### P1.2 Convert The Red-Team Lessons Into Regression Tests

- Why it matters: today’s hardening knowledge is mostly in prose and operator memory. The repo needs to prove the four failure classes that matter most: missing webhook, replay suppression, duplicate recovery, and fully skipped run classification.
- Exact deliverable: add a regression pack with fixture payloads and integration tests for `/api/ingest/apify`, plus deterministic checks for [scripts/reconcile_apify_ingest_runs.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/reconcile_apify_ingest_runs.py). Cover `ignored_replay`, stale payload rejection, `duplicate_existing`, direct-PG fallback, and pre-save skip ledgering.
- Proof of done: CI job green on the regression suite; intentional breakage to any of those code paths causes a test failure.
- Dependencies: representative webhook fixtures, local DB test harness, CI runtime.
- Risk if skipped: the same class of outage comes back on the next cleanup or refactor.
- Owner suggestion: Backend.

### P1.3 Standardize The Incident Evidence Bundle

- Why it matters: closeout quality improved because the operator assembled facts across docs, scripts, SQL, and logs. That should be a deliverable, not a heroic act.
- Exact deliverable: produce a machine-readable and human-readable incident bundle format for any ingest window. Minimum contents: deploy SHA, actor set, reconciliation output, live schema check result, recent-health result, pager run context, SQL evidence for suspect runs, replay actions taken, and unresolved risk.
- Proof of done: one full bundle generated for a recent 24-hour window and used as the sole source for a handoff review.
- Dependencies: reconciliation tooling, live verification scripts, pager wrapper, runbook updates.
- Risk if skipped: every handoff will still depend on whoever remembers the last incident best.
- Owner suggestion: Ops.

### P1.4 Tighten Alert Eligibility To Proven Pricing Evidence

- Why it matters: [backend/ingest/alert_gating.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/alert_gating.py) still allows proxy pricing maturity for alerts, while [backend/ingest/manheim_market.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/manheim_market.py) can run in proxy-fallback-only mode. Saved rows and alert-worthy rows are not the same thing.
- Exact deliverable: separate “can save” from “can notify”. Alerts should require stricter provenance, freshness, and confidence than ingest persistence. Small-set live verification should report how many recent alert candidates were blocked for weak pricing evidence.
- Proof of done: test cases where proxy-only vehicles save successfully but cannot trigger Telegram alerts; live verification shows pricing maturity mix and blocked-alert counts.
- Dependencies: scoring owner decisions, [docs/live_small_set_verification.md](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/docs/live_small_set_verification.md), alert tests.
- Risk if skipped: operators will keep seeing high-confidence alert behavior built on low-confidence pricing inputs.
- Owner suggestion: Data/Scoring with Backend.

## P2: Reduce Systemic Trust And Consistency Debt

### P2.1 Remove Service-Role Blast Radius From User-Facing Routers

- Why it matters: [webapp/routers/rover.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/rover.py) and [webapp/routers/outcomes.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/outcomes.py) initialize broad Supabase clients and then rely on route code to enforce isolation. That is workable until it is not.
- Exact deliverable: move user-facing access to least-privilege paths backed by RLS-safe policies or dedicated backend methods. Reserve service-role usage for trusted ingest and maintenance jobs only.
- Proof of done: those routers no longer boot with service-role credentials, and auth tests prove one user cannot read or mutate another user’s data through application bugs.
- Dependencies: Supabase policy work, auth test coverage, app refactor.
- Risk if skipped: a small auth regression becomes a full data exposure or write-abuse incident.
- Owner suggestion: Backend/App.

### P2.2 Replace Local Cache Behavior With Shared Production State

- Why it matters: [backend/ingest/retail_comps.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/retail_comps.py) uses local file cache plus per-process memory. That is not stable across instances. The rate limiter and Rover affinity paths also depend on Redis availability in ways that degrade open.
- Exact deliverable: move production caching to shared infrastructure with TTL, stale-state visibility, and a documented failure mode. Production behavior cannot depend on a local `.cache` file or per-process memory for pricing truth.
- Proof of done: multi-instance staging test shows consistent cache reads and invalidation behavior; stale cache metrics are visible.
- Dependencies: Redis or DB design, app config, staging environment.
- Risk if skipped: different instances will produce different pricing evidence and inconsistent behavior under load or deploy churn.
- Owner suggestion: Platform with Backend/Data support.

### P2.3 Make Market-Data Provenance And Freshness First-Class

- Why it matters: the current market-data layer can fall back quietly. That keeps ingest alive, but it also makes it too easy for “green ingest” to hide weakening score quality.
- Exact deliverable: require provenance and freshness fields to flow through scoring, persistence, verification, and alerting. Add explicit degraded states for “live market data absent, proxy fallback active” and “retail comps stale or sparse”.
- Proof of done: verification output and health bundles show source status, freshness age, and fallback share over the last window; one degraded-market-data test proves the system reports the condition instead of silently absorbing it.
- Dependencies: schema and reporting updates, scoring changes, verification updates.
- Risk if skipped: pricing quality erosion will remain invisible until operators notice bad calls manually.
- Owner suggestion: Data/Scoring.

## P3: Turn Hardening Into A Release Discipline

### P3.1 Add Chaos Drills And A Pre-Deploy Ingest Gate

- Why it matters: several serious defects were only surfaced because the live system was challenged after the fact. That has to become deliberate.
- Exact deliverable: add a release gate and recurring game-day that exercises secret rotation, replay suppression, missing webhook detection, duplicate recovery, audit-write failure, and pager path verification. The release gate should block when the regression pack fails.
- Proof of done: one completed drill with artifacts and a pipeline gate wired into the deploy flow.
- Dependencies: P0 and P1 regression work, CI plumbing, operator time.
- Risk if skipped: hardening stays anecdotal and drifts until the next incident.
- Owner suggestion: Platform with Backend and on-call participation.

### P3.2 Collapse Operator Knowledge Into A Single Control Plane

- Why it matters: today’s truth is scattered across runbooks, logs, scripts, closeout notes, and local operator context. The ACP/Codex flake called out in closeout is a symptom of that wider problem.
- Exact deliverable: create one hardening control-plane entrypoint that links current actor inventory, pager mode, last reconciliation bundle, last red-team result, and active watchpoints. Stop relying on memory and chat scrollback.
- Proof of done: a fresh operator can execute a handoff or incident review using only the control-plane entrypoint and attached artifacts.
- Dependencies: P1 incident bundle, docs consolidation, ownership.
- Risk if skipped: incident response remains person-dependent and brittle.
- Owner suggestion: Ops.

## Hidden And Adjacent Gaps Backed By Repo Evidence

These are not “nice to have” observations. They are the nearby holes most likely to reopen the same class of problems.

- Audit logging remains a live watchpoint. The hardened route now fails loudly if critical audit evidence cannot land and marks backfilled audit rows with `audit_fallbacks=...`, but operators still need to watch for `audit_backfilled` in reconciliation output from [webapp/routers/ingest.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/ingest.py) and [scripts/reconcile_apify_ingest_runs.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/reconcile_apify_ingest_runs.py).
- Actor coverage is too narrow by default. The preflight defaults to `ds-govdeals` and `ds-publicsurplus` in [scripts/run_ingest_rollout_preflight.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/scripts/run_ingest_rollout_preflight.py), while the deployment manifest contains more actors in [apify/deployment.json](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/apify/deployment.json).
- Pager proof is incomplete. The workflow exists in [/.github/workflows/ingest-health-pager.yml](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/.github/workflows/ingest-health-pager.yml), but the closeout says live paging was not intentionally proven. That is an operational gap, not a paperwork gap.
- The rate limiter fails open. If Redis cannot be reached, [webapp/middleware/rate_limit.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/middleware/rate_limit.py) simply allows traffic through. That is acceptable for a brochure site. It is not acceptable for a webhook boundary.
- User-facing auth still has too much privilege underneath it. [webapp/routers/rover.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/rover.py) and [webapp/routers/outcomes.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/webapp/routers/outcomes.py) rely on app logic to constrain broad Supabase access.
- Pricing evidence can drift without tripping ingest health. [backend/ingest/manheim_market.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/manheim_market.py) can run fallback-only, and [backend/ingest/retail_comps.py](/Users/andrewpilson/.openclaw/workspace/projects/dealerscope/backend/ingest/retail_comps.py) caches locally. The system can look operational while price quality quietly decays.

## Exit Condition For Phase 2

Phase 2 is done only when:

- The webhook boundary is proven after secret changes, not assumed.
- Audit surfaces are durable enough that reconciliation is trustworthy under failure.
- Every enabled actor is covered by recent-health and pager logic.
- Alerting only escalates rows backed by evidence strong enough to trust.
- User-facing routes no longer carry unnecessary service-role blast radius.
- Hardening regressions fail in CI before they fail overnight.

Anything short of that is still incident recovery, not hardening.
