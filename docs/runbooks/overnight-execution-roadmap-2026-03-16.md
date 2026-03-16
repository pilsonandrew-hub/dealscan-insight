# Overnight Execution Roadmap — 2026-03-16

This roadmap starts from the exact unresolved state at the end of tonight.

## Operating Rules

- Do not leave the current waypoint until it is fixed, jointly judged fixed enough by me + Codex, or explicitly externally blocked.
- No silent skipping.
- No calling something verified unless it has actually been checked live.
- After each successful step, run an independent red-team audit loop.
- If a serious snag appears, consult Codex before moving on.

## Current Active Waypoint

**Fix live webhook secret truth and complete real live verification.**

### Current known blocker
The live service is still accepting the old webhook secret and rejecting the new one even after a deploy/redeploy.

Most likely cause already identified:
- Railway production has duplicate variable scopes.
- `APIFY_WEBHOOK_SECRET` exists at both the environment level and the `dealscan-insight` service level.
- The running service appears to be reading the service-scoped old value, not the environment-level new value.

This means live verification is **not complete yet**.

---

## Phase A — Clear the current blocker

### A1. Fix service-scoped webhook secret truth
Goal:
- ensure the active `dealscan-insight` service uses the new webhook secret value
- ensure no stale service-scoped override is defeating the intended env state

Checks:
- inspect Railway variable scopes
- update the service-scoped `APIFY_WEBHOOK_SECRET` to the intended new value
- confirm `APIFY_WEBHOOK_SECRET_PREVIOUS` is absent unless intentionally reintroduced
- redeploy/restart the service after the change

Pass:
- startup logs no longer warn that the active secret is short

Fail:
- startup log still shows short active secret after restart
- old secret still accepted live

### A2. Re-run red-team webhook test
Goal:
- prove the stale secret is dead and replay suppression still works

Checks:
1. POST a recent valid webhook payload with the retired secret
2. Expect `401`
3. POST the same payload with the current secret and same run_id
4. Expect `200` with replay ignored / `ignored_replay`
5. Confirm no duplicate `opportunities` or new delivery side effects were created

Pass:
- old secret rejected
- new secret accepted
- replay suppressed cleanly

Fail:
- old secret still accepted
- new secret rejected
- duplicate landing occurs

### A3. Independent red-team audit loop for webhook boundary
Goal:
- challenge the rotation result before moving on

Checks:
- inspect Railway logs for any acceptance via previous/old secret
- verify startup logs reflect the intended secret posture
- spot-check webhook_log around the test run_id

Pass:
- no evidence of old-secret acceptance after fix

---

## Phase B — Finish roadmap Step 6

### B1. Close webhook rotation properly
Only after Phase A passes.

Checks:
- `APIFY_WEBHOOK_SECRET_PREVIOUS` remains absent
- at least one normal webhook lands after the fix on the new secret
- no warnings suggest fallback acceptance

Pass:
- Step 6 complete

Then run a fresh red-team audit loop.

---

## Phase C — Finish roadmap Step 7

### C1. Post-rotation verification + replay-window check
Goal:
- prove the system behaves correctly after rotation, not just during it

Checks:
- rerun live preflight / recent health if needed
- verify replay-window behavior with controlled duplicate submission
- verify degraded/error recovery path remains replayable in theory/runbook and not accidentally blocked

Pass:
- post-rotation live truth holds

Then run a fresh red-team audit loop.

---

## Phase D — Finish roadmap Step 8

### D1. Decide pager mode from evidence
Goal:
- choose dry-run or live based on observed system truth, not preference

Checks:
- if live core path is clean, decide whether to keep pager dry-run or enable live Telegram paging
- if enabling live, verify credentials and perform one intentional live page test

Pass:
- pager mode explicitly chosen and documented

Then run a fresh red-team audit loop.

---

## Phase E — Finish roadmap Step 9

### E1. ACP/Codex tooling flake cleanup
Goal:
- close the known assistant/Codex handoff reliability issue if still actionable

Checks:
- document exact failure mode
- verify whether workaround (local Codex CLI) is still required
- only call this complete if the flake is fixed or explicitly downgraded as non-blocking and documented

Then run a fresh red-team audit loop.

---

## Phase F — Finish roadmap Step 10

### F1. Final closeout ledger
Goal:
- leave a precise record of what changed, what was proven, and what remains monitored

Must include:
- final live commit/deploy truth
- secret rotation completion status
- validation results
- red-team findings
- pager mode decision
- any remaining external blockers

Only do this when prior steps are actually complete.

---

## Immediate Next Action

**Do not move past Phase A.**

Next exact action:
1. update the service-scoped Railway `APIFY_WEBHOOK_SECRET`
2. redeploy/restart
3. rerun stale-secret / replay red-team test
4. report the result plainly
