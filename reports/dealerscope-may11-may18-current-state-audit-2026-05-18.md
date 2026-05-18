# DealerScope Current-State Audit — 2026-05-18

Scope: evidence from 2026-05-11 through 2026-05-18. Historical narrative sections are a baseline; the verification block below is the current HEAD truth.

## Current Verification Block

- Verified at: 2026-05-18T21:19:42Z+ (GitHub check-run evidence observed after completion)
- Verified HEAD: `8378125937c70e46c78523d7410a9fe6abaec6d4`
- Verification scope: current `origin/main`/local `main` check-runs for HEAD `8378125`
- Current check-run proof:
  - Codespaces Prebuild / `prebuild`: `completed / success`, run `26060265089`, completed `2026-05-18T21:19:42Z`
  - Google Cloud Build `rmgpgab-dealscan-insight-europe-west1-pilsonandrew-hub-dealsmyx`: `completed / success`, build `e34cb628-7563-474f-93f1-3f0c156a2971`
  - Cursor Review: `completed / success`, run `26060265866`
  - Saved Searches Check: `completed / success`, run `26061747624`
  - Watchdog Hunter: `completed / success`, run `26061799029`
- Current unresolved items after this verification:
  - Legacy CSV/local scraper path is now fail-closed unless explicitly enabled for local diagnostics.
  - Historical ingest artifact clutter is now explicitly scoped in reconciliation output; continue monitoring current landing issues separately.
  - Apify local skill token scope is closed as optional local tooling; GitHub Actions remains source-of-record.
  - Stale GitHub noise policy is explicit: current HEAD/protected/production-impacting evidence only.
  - Hermes Layer 0 remains design-only and is not implemented.

## Verdict

Current repo-controlled DealerScope state is **green on the current HEAD verification block**.

All code-actionable failures found during the May 11–18 cleanup window have been remediated or explicitly moved into a non-code blocker category. Current HEAD check-runs verified after the latest audit-status commit:

- `watchdog-hunter` — success
- `cursor-review` — success
- Deploy GOLD Validation Reports — success (`security-precheck`, `validate`, `enforce-slos`, `deploy`; `notification` skipped)
- Google Cloud Build `rmgpgab-dealscan-insight-europe-west1-pilsonandrew-hub-dealsmyx` — success
- `prebuild` / Codespaces Prebuild — **completed success** as run `26060265089`

## Major Work Completed

### 1. Ingest truth and webhook reliability

Completed:
- Added read-only Supabase live inspection workflow.
- Added read-only Apify-to-Supabase per-run reconciliation workflow.
- Exposed the real gap: actor health was not enough; webhook/DB landing evidence was missing for many runs.
- Fixed `/api/ingest/apify` so unreachable direct Postgres claim path falls back to Supabase REST durable path instead of returning HTTP 500.
- Corrected reconciliation wording/classification for `direct_pg_claim_rest_fallback`.
- Added/updated Apify deployment metadata, including HiBid-v2 webhook ID.
- Set explicit Railway Supabase DB URLs to prevent production from deriving the unreachable direct IPv6 Supabase host.
- Proved a fresh GovDeals run after remediation: run `c9xJjrsXt37DfOIzE` landed cleanly with webhook evidence, delivery ledger evidence, Notion sync, and Sonar mirror evidence.

Status: **live-improved and current proof green**.

Residual truth:
- Older `db_only_run` / `direct_pg_claim_rest_fallback` rows remain as historical pre-fix artifacts.
- Continue using reconciliation as the authority for ingest truth, not actor-health alone.

### 2. Ingest modularization and observability

Completed a large no-behavior-change extraction from `webapp/routers/ingest.py` into focused `backend/ingest/*` helpers, including:
- source/site identity helpers
- canonical identity and duplicate recovery
- time/listing/vehicle identity helpers
- opportunity row builder
- gate checks
- fallback score helper
- alert validation and Telegram formatting helpers
- webhook security, replay, metadata, timing, and client-IP helpers
- audit state and critical audit sentinel helpers
- direct Postgres helpers
- VIN dedup helpers
- Sonar listing builder
- delivery log helpers
- env/config helpers

Validation reported during the work:
- targeted webhook/reconcile tests passed
- full pytest passed
- build passed
- Cursor review passed on final HEAD

Status: **closed for current scope**.

### 3. CI/GitHub Actions cleanup

Completed:
- Scoped pytest collection to avoid legacy script collection failures.
- Updated workflows toward Node 24 / `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`.
- Fixed GOLD security precheck false positives and noisy exclusions.
- Fixed GOLD validation status parsing.
- Fixed local/Mac portability in `scripts/run-validation-suite.sh`.
- Fixed npm dependency vulnerabilities; `npm audit --audit-level=moderate` reports no vulnerabilities.
- Removed GitHub Pages dependency from validation workflows and replaced dashboard publishing with artifact upload.
- Removed accidental nested workflow file `.github/workflows/.github/workflows/deploy-gold.yml`.
- Made `scripts/enforce_slos.sh` executable.

Current status: **green**.

### 4. Google Cloud Build / Cloud Run deploy failures

Completed:
- Fixed Docker build package failure by removing unsafe `apt-get upgrade` behavior from `Dockerfile`.
- Added `.dockerignore` to keep build context clean and avoid shipping secrets/local artifacts.
- Added safe startup fallback for missing `SECRET_KEY` import crash in Cloud Run-style environments, with tests.
- Verified Google Cloud Build check is now green at current HEAD.

Status: **closed for current HEAD**.

### 5. Codespaces Prebuild failures

Completed:
- Added `.devcontainer/devcontainer.json` using stable `node:24-bookworm` instead of failing default universal image pull.
- Prior Codespaces Prebuild proof passed after the stable devcontainer fix.
- On latest verified HEAD `8378125937c70e46c78523d7410a9fe6abaec6d4`, Codespaces Prebuild run `26060265089` completed successfully.

Status: **closed for current HEAD**.

### 6. GitHub billing/spending-limit blocker

Completed:
- Identified Cursor Review, Codespaces, Watchdog, and Saved Searches failures as GitHub Actions runner-start failures due to account payment/spending-limit issues, not repo failures.
- Updated account-level budget/spending settings.
- Reran blocked checks.
- Billing/spending-limit failures stopped blocking later runner startup; current HEAD Cursor Review, GOLD Validation, Watchdog, and Google Cloud Build passed.
- Latest Codespaces Prebuild completed successfully, so billing/spending-limit failure is not a current blocker for HEAD `8378125`.

Status: **closed for billing and current Codespaces proof**.

### 7. Hermes design artifact

Completed:
- Added `reports/hermes-dealerscope-operating-spec-2026-05-18.md`.
- Hermes defined as DealerScope’s Signal, Reliability, and Acquisition Judgment Officer.
- Build order defined: truth-ledger, pipeline-truth, ingest-reconciler, alert-chain-verifier, operator-briefing, actor-health-profiler, deal-quality-auditor, Opportunity Desk, market-memory, incident-commander.

Status: **design artifact committed; implementation not started**.

## Current Open Items

### A. Final reconciliation proof follow-up / historical artifact scoping

Manual run `26059063029` was triggered as a final read-only audit proof after this review and later reported success in GitHub Actions. Continue using reconciliation as the source of truth for actor → webhook → DB landing evidence.

Historical artifact handling is now explicit in `scripts/reconcile_apify_ingest_runs.py`: `db_only_run`, `direct_pg_claim_rest_fallback`, and `audit_backfilled` are reported as `issue_scope=historical_artifact` when they are not mixed with current landing failures. Current actor → webhook → DB failures remain `issue_scope=current_landing_issue`.

Verification: `.venv-test/bin/python -m pytest tests/test_reconcile_apify_ingest_runs.py -q` → `23 passed`.

Classification: **current proof green; historical artifact clutter classified separately**.

### B. Codespaces Prebuild final proof

Current HEAD `8378125937c70e46c78523d7410a9fe6abaec6d4` has a passing Codespaces Prebuild: run `26060265089`, `completed / success`, completed `2026-05-18T21:19:42Z`.

Classification: **closed for current HEAD**.

### C. Historical stale failures still visible in GitHub mobile

GitHub mobile can show old red Xs from earlier commits. Current HEAD check-runs are the authority.

Classification: **not current blocker**.

### D. Node 20 deprecation annotations

Some GitHub-owned actions still emit Node 20 warnings despite Node 24 forcing. Current checks pass.

Classification: **non-blocking noise**.

### E. Legacy local scraper path

`backend/ingest/scrape_all.py` still writes local CSV files under `DATA_DIR`, including `no_rust_exception_list.csv` and `scraped_listings.csv`. This is not the production ingest path. Production ingest authority is Apify webhook → Railway `/api/ingest/apify` → Supabase.

The path is now explicitly marked as legacy local/offline diagnostics and fails closed unless `DEALERSCOPE_ALLOW_LEGACY_LOCAL_SCRAPER=1` is set. This prevents accidental use as a production ingest surface while preserving an intentional local diagnostic escape hatch.

Verification: `.venv-test/bin/python -m pytest tests/test_reconcile_apify_ingest_runs.py tests/test_scrape_all_legacy_guard.py -q` → `25 passed`.

Classification: **closed as production ambiguity; retained only as explicit local diagnostics**.


### F. Apify local skill token scope

Local shell inspection does not currently have `APIFY_TOKEN` or `APIFY_API_TOKEN` exported, and prior local skill-token evidence was stale/scoped incorrectly. This is not a production blocker because the repo-owned GitHub Actions workflows use repository secret `APIFY_TOKEN` for read-only actor/watchdog/reconciliation checks:

- `.github/workflows/supabase-ingest-reconciliation.yml`
- `.github/workflows/dealerscope-scraper-watchdog.yml`
- `.github/workflows/apify-health-check.yml`
- `.github/workflows/scraper-health-agent.yml`

Decision: local Apify visibility is optional operator convenience, not source-of-record. Do not rotate/update local Apify credentials unless direct OpenClaw-side Apify inspection becomes necessary. For normal DealerScope truth, use the repo workflows and their secret-backed evidence.

Classification: **closed as optional local tooling; GitHub Actions remains source-of-record**.

### G. Stale GitHub noise policy

Investigate only:

1. failures on the current HEAD,
2. protected workflow failures that block deploy/validation,
3. production-impacting failures with live evidence, or
4. failures reproduced by the source-of-record workflow/reconciliation path.

Do not chase old GitHub mobile red Xs, older branch failures, Node20 warnings from GitHub-owned action runtime annotations, or historical workflow failures unless they reproduce on current HEAD or affect production truth.

Classification: **active policy**.

## Recommended Next Step

Remaining non-Hermes truth-cleanup items are now closed or policy-classified. Next, start Hermes foundation, but only Layer -1 / Layer 0:

1. Truth ledger schema/design in repo, source-backed and append-only.
2. Pipeline-truth snapshot generator that summarizes actor run → webhook → DB landing → delivery/alert evidence.
3. Operator briefing generated from the truth ledger, not model memory.

Do **not** start economic recommendations yet. Hermes should not recommend buys until each recommendation can carry its proof chain.
