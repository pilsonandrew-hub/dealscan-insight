# DealerScope Ingest Final Closeout — 2026-03-16

## Scope
Final closeout for the March 15–16 ingest recovery and hardening run.

## Final live truth
- **Latest live Railway commit:** `9898a88` — `fix: account for pre-save skip outcomes`
- **Live service:** `dealscan-insight`
- **Health state at closeout:** recent-ingest reconciliation returns **Issue summary: none** for `ds-govdeals` + `ds-publicsurplus`

## What was fixed across the run
- Dataset-id recovery from Apify actor runs
- Direct Postgres fallback for ingest saves
- Relative auction-end normalization
- Observability and replay accounting hardening
- Stable hashed listing identity and replay hardening
- Ingest delivery ledger (`ingest_delivery_log`)
- Canonical duplicate update deferral until save success
- Reconciliation tooling and recent-ingest health wrapper
- Pager wrapper and scheduled health-check path (kept dry-run)
- Broadened direct-PG fallback coverage for generic Supabase write failures
- Webhook replay hardening (`ignored_replay`, stale-payload option)
- Canonical dedupe race recovery
- Webhook secret rotation flow hardening
- Rollout preflight
- Apify SSL fallback for reconciliation tooling
- Removal of hardcoded Telegram chat fallback
- Guardrail tightening after overnight audit
- Pre-save skip ledgering and reconciliation classification for fully skipped runs

## What was proven live
### 1. Latest hardened stack deployed
- Latest code was pushed and Railway deploys were observed successful through `9898a88`.

### 2. Rollout preflight reached green
- Environment validation, schema checks, and recent-ingest health all passed after the blocker fixes.

### 3. Webhook secret rotation boundary
- Old secret was rejected (`401`) after service-scoped secret correction.
- Current secret was accepted.
- Replay suppression with the current secret produced `ignored_replay` without duplicate landing.
- `APIFY_WEBHOOK_SECRET_PREVIOUS` was removed after confidence.

### 4. Recent-ingest health wrapper
- Dry-run health wrapper was executed against live-style inputs.
- Final recent-ingest output showed `Issue summary - none`.

### 5. Historical missed-run recovery
- PublicSurplus run `oreuK2UsGFqAoiODd` was a genuine missed ingest (Apify succeeded, no webhook/ledger/opportunity evidence).
- Manual replay recovered it and produced expected duplicate-existing save outcomes.

### 6. Historical GovDeals false-positive resolution
- GovDeals run `FRQha6WgxOXIyPyRo` originally showed processed webhook with no delivery/opportunity evidence.
- Root cause: fully skipped pre-save outcomes were not being ledgered, so reconciliation misclassified the run as a save-path failure.
- Fix `9898a88` added pre-save skip ledgering and updated reconciliation to treat fully-accounted all-skipped runs correctly.
- Replaying that historical run under the new code produced skip ledger rows and cleared the health report.

## Pager mode decision
- **Decision:** keep ingest health paging in **dry-run** mode for now.
- **Reason:** dry-run path is proven; a fully acknowledged live Telegram pager send to the intended destination was not intentionally executed and verified during this closeout.
- **Current truth:** pager tooling exists and is healthier than before, but live paging was not claimed as proven.

## Remaining non-blocking items
1. **ACP/Codex tooling flake**
   - ACP session return path was unreliable during the run.
   - Local Codex CLI was used as the reliable workaround.
   - This is not a DealerScope ingest blocker, but it remains an assistant-tooling issue.

2. **Pager live enablement**
   - Dry-run is the current safe mode.
   - Live mode still requires an intentional end-to-end Telegram proof and explicit operator decision.

## Red-team notes
- Stale-secret rejection was proven by intentional `401` responses after rotation.
- Replay suppression was proven with a current-secret duplicate submission that produced `ignored_replay` and no duplicate landing.
- Overnight red-team audit found real issues that were fixed, including:
  - hardcoded Telegram chat fallback
  - missing pre-save skip ledgering
  - reconciliation blind spots for fully skipped runs

## Final assessment
DealerScope ingest is now materially hardened and operationally trustworthy for the validated live paths.

This closeout does **not** claim perfection.
It does claim that the critical ingest/replay/ledger/rotation path was repaired, re-verified live, red-teamed, and brought to a clean recent-health state.

## Final commit landmarks
- `a6dd6ef` — tighten ingest guardrails after overnight audit
- `9898a88` — account for pre-save skip outcomes

## Closeout status
- **Core live DB access blocker:** resolved
- **Real live verification:** completed
- **Recent ingest health:** green
- **Pager mode:** dry-run retained
- **Final closeout:** complete, subject to future monitoring
