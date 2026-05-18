# DealerScope Current-State Audit — 2026-05-18

Scope: evidence from 2026-05-11 through 2026-05-18, current repo/live state at HEAD `e63282f40b1ffb3ba0f1b0b4ce1690d29e62e8a8`.

## Verdict

Current repo-controlled DealerScope state is **green except for one still-running Codespaces prebuild check**.

All code-actionable failures found during the May 11–18 cleanup window have been remediated or explicitly moved into a non-code blocker category. Current HEAD check-runs verified after the audit commit:

- `watchdog-hunter` — success
- `cursor-review` — success
- Deploy GOLD Validation Reports — success (`security-precheck`, `validate`, `enforce-slos`, `deploy`; `notification` skipped)
- Google Cloud Build `rmgpgab-dealscan-insight-europe-west1-pilsonandrew-hub-dealsmyx` — success
- `prebuild` / Codespaces Prebuild — **still in progress** as run `26059251923`

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
- On latest HEAD `e63282f40b1ffb3ba0f1b0b4ce1690d29e62e8a8`, Codespaces Prebuild run `26059251923` is still in progress and has not produced a fresh conclusion yet.

Status: **pending fresh HEAD conclusion**.

### 6. GitHub billing/spending-limit blocker

Completed:
- Identified Cursor Review, Codespaces, Watchdog, and Saved Searches failures as GitHub Actions runner-start failures due to account payment/spending-limit issues, not repo failures.
- Updated account-level budget/spending settings.
- Reran blocked checks.
- Billing/spending-limit failures stopped blocking later runner startup; current HEAD Cursor Review, GOLD Validation, Watchdog, and Google Cloud Build passed.
- Latest Codespaces Prebuild is still running, so billing is not currently proven as a blocker for that check but the final conclusion is pending.

Status: **closed for billing; Codespaces conclusion pending**.

### 7. Hermes design artifact

Completed:
- Added `reports/hermes-dealerscope-operating-spec-2026-05-18.md`.
- Hermes defined as DealerScope’s Signal, Reliability, and Acquisition Judgment Officer.
- Build order defined: truth-ledger, pipeline-truth, ingest-reconciler, alert-chain-verifier, operator-briefing, actor-health-profiler, deal-quality-auditor, Opportunity Desk, market-memory, incident-commander.

Status: **design artifact committed; implementation not started**.

## Current Open Items

### A. Final reconciliation proof follow-up

Manual run `26059063029` was triggered as a final read-only audit proof after this review and later reported success in GitHub Actions. Continue using reconciliation as the source of truth for actor → webhook → DB landing evidence.

Classification: **current proof green; keep monitoring**.

### B. Latest Codespaces Prebuild still running

Current HEAD run `26059251923` remains `in_progress` as of the last audit read. A scheduled follow-up is already configured to report pass/fail.

Classification: **pending verification**.

### C. Historical stale failures still visible in GitHub mobile

GitHub mobile can show old red Xs from earlier commits. Current HEAD check-runs are the authority.

Classification: **not current blocker**.

### D. Node 20 deprecation annotations

Some GitHub-owned actions still emit Node 20 warnings despite Node 24 forcing. Current checks pass.

Classification: **non-blocking noise**.

### E. Legacy local scraper path

`backend/ingest/scrape_all.py` and older scraper surfaces still have CSV/mock/offline remnants. Production ingest authority is Apify webhook → Railway `/api/ingest/apify` → Supabase.

Classification: **real cleanup candidate, lower priority than Hermes truth-ledger unless it misleads operators**.

## Recommended Next Step

Start Hermes foundation, but only Layer -1 / Layer 0:

1. Truth ledger schema/design in repo, source-backed and append-only.
2. Pipeline-truth snapshot generator that summarizes actor run → webhook → DB landing → delivery/alert evidence.
3. Operator briefing generated from the truth ledger, not model memory.

Do **not** start economic recommendations yet. Hermes should not recommend buys until each recommendation can carry its proof chain.
