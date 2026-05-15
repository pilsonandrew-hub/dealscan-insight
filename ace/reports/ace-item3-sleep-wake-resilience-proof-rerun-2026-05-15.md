# ACE Item 3 Sleep/Wake Resilience Proof Re-run — 2026-05-15

Status: PASS

Commit under proof:
- `7562039 ace: accept sleep survival in item 3 proof`

Artifact:
- `/tmp/ace-item3-sleep-wake-proof-20260515T055227Z.json`

Raw audit output:
```text
audit.verify.event_hash_chain=ok
audit.verify.db_path=/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db
```

Full ACE test suite:
```text
Ran 552 tests in 43.063s
OK
```

Git status after proof:
```text
## master
```

## Pre-state snapshot

- runtime_instance_id: `runtime_809e6f4210f74534867bd99ce46e7647`
- last heartbeat / last_seen_at: `2026-05-15T05:52:23.445142Z`
- hash chain head: event id `101019`, hash `c954a44ba042b1a1c34e2c559807829112a8a9b9eee7b0b9159e5f58d1691e9f`
- governed_runs active count: `0`
- items table count: `94`

## Post-state snapshot

- runtime_instance_id: `runtime_809e6f4210f74534867bd99ce46e7647`
- last heartbeat / last_seen_at: `2026-05-15T05:54:24.242495Z`
- hash chain head: event id `101036`, hash `96d84e3b284612abdc73a81cda8654acaf77bd3e1fe179dd3c0f2905cb6ccadd`
- governed_runs active count: `0`
- items table count: `95`
- invalid item state rows: `0`
- post-wake cycle: `run_b7ea5604987647928f4aa50fd63680b1`, status `completed`, failure_code `None`

## Six independent checks

1. Supervisor restart semantics — PASS
   - Sleep-survival path: same runtime instance remained live and heartbeat advanced from `2026-05-15T05:52:23.445142Z` to `2026-05-15T05:54:24.242495Z`.

2. Hash chain integrity — PASS
   - `ace audit verify` returned `event_hash_chain=ok`.
   - Hash head advanced from event `101019` to event `101036` with no regression.

3. No duplicate cycles — PASS
   - governed_runs active count sampled `0 / 0 / 0` across pre, post-before-cycle, and post-after-cycle snapshots.

4. No corrupted state — PASS
   - items count was monotonically non-decreasing: `94 -> 95`.
   - invalid item state rows: `0`.
   - VERIFIED_DONE closeout metadata check passed.

5. Cycle execution post-wake — PASS
   - Post-wake launchd cycle `run_b7ea5604987647928f4aa50fd63680b1` completed with no failure_code.

6. Test suite green — PASS
   - Full ACE suite passed: `Ran 552 tests in 43.063s — OK`.

## Verdict

Item 3 sleep/wake resilience proof is clean PASS for the six specified checks.
