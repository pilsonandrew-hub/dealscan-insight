# DealerScope Workflow Authority Register

Date: 2026-05-26
Owner: Ja'various
Status: Control-tower workflow register / not CI proof by itself
Purpose: classify DealerScope workflow files so workflows cannot imply fake production proof or stale authority.

---

## Classification system

| Class | Meaning | Operator rule |
|---|---|---|
| **required-gate** | Must pass before a claim can be called shipped/green. | Treat failure as blocker for that scope. |
| **supporting-gate** | Useful validation, but not the sole proof of product truth. | Cite with scope. Do not overstate. |
| **advisory** | Produces information or review signal only. | Never use alone as pass/fail proof. |
| **legacy/historical** | Kept for archive or old branch context. | Do not use for current claims. |
| **theater-risk** | Looks authoritative but can pass while product truth is unproven. | Either harden, relabel, or remove. |

---

## Current workflow inventory

Live filesystem check on 2026-05-26 found only these workflow files in the inspected workspace paths:

| Workflow | Path | Current class | Authority boundary | Notes |
|---|---|---|---|---|
| ACE CI | `.github/workflows/ace-ci.yml` | required-gate for root ACE changes only | Runs Python 3.14 ACE unittest discovery under `ace/tests`; reports coverage informationally. | This is not DealerScope product proof. It proves ACE test health for root `ace/**` changes. |
| ACE CI mirror/copy | `projects/dealerscope/.github/workflows/ace-ci.yml` | required-gate for DealerScope repo ACE changes only | Same ACE Python test workflow within `projects/dealerscope`. | Do not cite as pricing/ingest/alert/product proof. |

No current root-level DealerScope product workflow was found in `.github/workflows` during this pass besides ACE CI. If GitHub remote contains additional workflows not present locally, remote truth must be inspected before any global CI claim.

---

## What current ACE CI proves

ACE CI can support claims like:

- ACE CLI/code tests passed for the changed `ace/**` scope.
- The ACE Python test suite imports and runs on GitHub Actions Python 3.14.
- Launchd-related ACE tests have zsh available in CI.

ACE CI does **not** prove:

- DealerScope scoring is correct.
- Auction ingest is live.
- Telegram hot-deal alerts are delivered.
- Supabase schema matches production expectations.
- Frontend product flows work.
- Apify actors are healthy.
- Railway/Vercel deployment is green.
- Pricing/MMR/MarketCheck truth is current.

---

## Required product workflow gaps

These are not necessarily missing files to build immediately. They are workflow authority gaps: product claims should not be made unless equivalent proof exists somewhere else.

| Product claim | Required proof before claim | Current register status |
|---|---|---|
| Ingest is healthy | webhook security tests, scoring tests, source normalization tests, live/read-only ingest aggregate inspection, recent webhook evidence | gap unless proven by separate run/artifact |
| Alerts are trustworthy | alert-gating tests, delivery-log verification, live Telegram/send receipt or alert_log proof | gap unless proven by separate run/artifact |
| Pricing/scoring is safe for money decisions | deterministic tests for 88% MMR ceiling, margin floor, rust-state/newer-vehicle exception, source/fallback price provenance | gap unless proven by separate run/artifact |
| Frontend operator workflow works | build/test plus browser smoke for Dashboard/Crosshair/Rover/Sniper/Analytics critical paths | gap unless proven by separate run/artifact |
| Apify actors are healthy | actor run status/dataset inspection/webhook verification | gap unless proven by separate run/artifact |
| Deployment is live | GitHub check + Railway/Vercel/current endpoint smoke | gap unless proven by separate run/artifact |
| Analytics truth is current | live schema-aware analytics route checks and outcome/execution consistency proof | gap unless proven by separate run/artifact |

---

## Workflow cleanup rule

Do not delete or rewrite workflows just because they are sparse.

Only modify a workflow if one of these is true:

1. It implies false authority.
2. It fails despite the underlying product being healthy.
3. It passes while allowing a real product-truth failure through.
4. It references stale runtimes, paths, secrets, branches, or product claims.
5. It blocks useful work due to obsolete assumptions.

Otherwise, classify it and leave it alone.

---

## Next recommended workflow action

Before editing any workflow, inspect remote GitHub Actions history for the active repo and map each recent run to one of:

- source/product gate
- deployment gate
- advisory review
- obsolete/historical
- failing for real reason
- failing for obsolete reason

Do not equate local workflow inventory with global GitHub truth until remote runs are checked.
