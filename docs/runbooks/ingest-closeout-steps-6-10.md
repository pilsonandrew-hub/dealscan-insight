# Ingest Closeout Checklist — Steps 6-10

Use this only after Step 5 baseline live validation is green on the currently deployed build.

This checklist is intentionally strict. If any gate fails, stop the sequence, record the failure, and return to reconciliation before touching pager mode or declaring closeout.

## Sequence Control

Required order:

1. Step 6: remove `APIFY_WEBHOOK_SECRET_PREVIOUS`
2. Step 7: prove post-rotation behavior and replay-window posture
3. Step 8: decide pager mode from observed evidence, not preference
4. Step 9: clear ACP/Codex tooling flakes that would corrupt handoff or operator context
5. Step 10: write the ledger and final summary

Do not run Step 8 before Step 7 passes.
Do not run Step 10 while Step 9 still has a known flake.

## Step 6: Webhook Rotation Closeout

Objective:
- Return webhook auth to a single accepted secret after the overlap window has proven unnecessary.

Checks:
- Production env currently still has both `APIFY_WEBHOOK_SECRET` and `APIFY_WEBHOOK_SECRET_PREVIOUS`.
- Since Step 5 went green, no fresh backend warnings indicate acceptance via `APIFY_WEBHOOK_SECRET_PREVIOUS`.
- At least one normal webhook delivery has landed after the Apify-side header rotation and before removing the fallback secret.

Pass criteria:
- `APIFY_WEBHOOK_SECRET_PREVIOUS` is unset in the live backend env.
- Backend has been restarted or redeployed so the unset value is active.
- Operator has a timestamped note of the exact removal time.

Fail criteria:
- Any acceptance warning via `APIFY_WEBHOOK_SECRET_PREVIOUS` appears in the confidence window.
- No post-rotation webhook has landed yet, so there is still no evidence that the new secret alone is carrying traffic.
- The env was edited but the process was not restarted, leaving auth state ambiguous.

## Step 7: Post-Rotation Verification And Replay-Window Check

Objective:
- Prove the system still accepts legitimate webhook traffic after fallback removal and verify that replay suppression is behaving as designed rather than hiding failures.

Checks:
- Run `python3 scripts/run_ingest_rollout_preflight.py --env-file .env.live --actors ds-govdeals ds-publicsurplus`.
- Run `python3 scripts/check_recent_ingest_runs.py --env-file .env.live --actors ds-govdeals ds-publicsurplus`.
- Review `webhook_log` for the first post-closeout runs and confirm `processing_status` is `processed` or intentionally `ignored_replay`, not auth failure or degradation.
- Confirm the current value of `APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS` matches operator expectations.
- For any `ignored_replay` rows seen after Step 6, confirm there is already a successful processed delivery for that same `run_id` inside the replay window so suppression is explainable.

Pass criteria:
- Preflight is green.
- Recent ingest health check exits `0`.
- Post-rotation runs show normal processed flow with no evidence of stale-secret acceptance.
- Any replay suppression observed is explainable from prior successful delivery history and is not masking a missing save ledger.

Fail criteria:
- Preflight or recent health gate fails.
- Any post-rotation webhook is missing, degraded, errored, or missing save ledger.
- `ignored_replay` appears without an earlier successful delivery that explains it.
- Operator cannot state the active replay-window value and why it is safe for tonight.

## Step 8: Pager Mode Decision

Objective:
- Decide whether the ingest pager should remain dry-run or switch to live Telegram based on proven signal quality.

Operator default:
- Stay in dry-run unless every live gate below is positively proven tonight. Missing proof is a "no", not a "maybe".

Checks:
- Step 7 is fully green.
- `INGEST_HEALTH_NOTIFY_ENABLED=true` is set wherever the pager wrapper runs.
- If considering live mode, `INGEST_HEALTH_NOTIFY_DRY_RUN=false`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` are all present in the runner environment.
- Run `scripts/page_recent_ingest_health.sh --env-file .env.live --actors ds-govdeals ds-publicsurplus` once in the chosen mode and record the result.

Live enable gate for tonight:
- The exact runner that will own overnight paging has already executed the wrapper successfully in dry-run.
- The Telegram chat id has been verified as the intended on-call destination, not just copied from a prior setup.
- One intentional live page has been sent from that same runner context and acknowledged by the human who will respond tonight.
- The operator has a timestamped note of who is on point and what constitutes a page-worthy follow-up.
- No repo-side or runner-side ambiguity remains about whether pages would come from local shell execution or the scheduled GitHub path.

Pass criteria for dry-run:
- Wrapper executes cleanly.
- Dry-run output is captured and reviewed.
- Team explicitly records that tonight remains observational only.

Pass criteria for live:
- Step 7 is green.
- Telegram destination is confirmed correct.
- A controlled failure or known-safe validation proves a page can be delivered and understood by the recipient.
- Team records who is on point for live pages tonight.
- Proof came from the same execution context that will send real pages overnight.

Fail criteria:
- Live mode is enabled before proving the health signal is clean.
- Telegram credentials are present but destination ownership is unconfirmed.
- The only evidence for live readiness is that env vars exist.
- Live-page proof came from a different shell, host, or runner than the one intended to page overnight.
- No single operator is accountable for acting on a live page tonight.

Minimum missing proof before flipping to live:
- If Step 7 is green but no acknowledged live Telegram test has been produced from the actual overnight runner, keep dry-run and treat the notification path as unproven.

## Step 9: ACP/Codex Tooling Flake Cleanup

Objective:
- Remove known repo-side tooling issues that would produce false operator context, bad handoff state, or misleading automation output during closeout.

Checks:
- `node scripts/validate-codex-sync.js` runs successfully in this repo.
- Any generated validation artifacts are recognized as local working files, not mistaken for source-of-truth runbook evidence.
- If ACP is being used for persistent session context, the active handoff notes point to the current closeout checklist and not stale rollout assumptions.

Pass criteria:
- Codex validation command exits successfully and produces a readable report.
- No known local tooling crash remains open for tonight's handoff.

Fail criteria:
- Documented validation commands still crash when run as written.
- Operators are relying on stale ACP/Codex notes that predate Step 6 removal or Step 7 verification.

## Step 10: Final Closeout / Ledger / Summary

Objective:
- Leave a defensible record of what changed, what was proven, what was deferred, and what still needs watching.

Required ledger entries:
- exact timestamps for Step 5 green validation, Step 6 fallback-secret removal, and Step 7 verification
- whether pager mode ended the night in dry-run or live
- active `APIFY_WEBHOOK_REPLAY_WINDOW_SECONDS` value
- any runs replayed or intentionally left unreplayed
- any unresolved risk accepted for overnight monitoring

Pass criteria:
- Ledger is timestamped, specific, and names any remaining watchpoints.
- Summary distinguishes proven facts from assumptions.
- Deferred items are explicit, with an owner and next check time.

Fail criteria:
- Closeout says "all good" without timestamps, run ids, or explicit residual risk.
- Pager mode, replay posture, or secret-rotation state is left implicit.

## Tonight Vs Later

Do tonight:
- Step 6 removal only after observed confidence, then Step 7 verification immediately after
- Step 8 pager decision for tonight's operating mode
- Step 9 fix or document any tooling crash that would pollute the handoff
- Step 10 ledger before operators leave the window

Can wait until daylight only if tonight stays dry-run and Step 7 is green:
- broader pager hardening beyond a single validated live route
- non-blocking ACP hygiene that does not affect tonight's notes or operator context
- cosmetic doc cleanup outside the checklist and active runbooks
