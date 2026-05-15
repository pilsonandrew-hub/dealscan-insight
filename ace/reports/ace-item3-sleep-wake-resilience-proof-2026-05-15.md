# ACE Item 3 Sleep/Wake Resilience Proof — 2026-05-15

## Result

FAIL.

This was one bounded Item 3 proof run with the requested six independent checks. Four checks passed and two checks failed.

Primary full artifact:

`/tmp/ace-item3-sleep-wake-proof-20260515T000840Z.json`

Proof runner used for the artifact:

`scripts/ace_sleep_wake_item3_proof.py`

## Commit Evidence

Commit hash/message will be recorded after this report is committed.

Git status before proof:

```text
## master
```

Git head before proof:

```text
45ebcdf ace: record sleep wake proof attempt
```

## Pre-State Snapshot

- test start timestamp: `2026-05-15T00:08:40Z`
- supervisor runtime_instance_id: `runtime_11fd6f78de54427eb8b4b9ac56c721b6`
- supervisor status: `live`
- last heartbeat timestamp: `2026-05-15T00:08:24.712951Z`
- hash chain head event id: `99362`
- hash chain head event_hash: `095f3068a08acd4a528a20239f2a37f0c477cf36e4ce80532b4e821acee2dbdf`
- governed_runs active count: `0`
- items table count: `85`

Pre-run audit verify:

```text
audit.verify.event_hash_chain=ok
audit.verify.db_path=/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db
```

## Trigger / Wake Details

- requested wake interval: minimum 60 seconds
- requested scheduled wake local: `05/14/26 17:10:20`
- `pmset schedule wake` result: `rc=1`, `pmset: This operation must be run as root`
- `pmset sleepnow` result: `rc=0`, stdout `Sleeping now...`
- sleep command start: `2026-05-15T00:08:50Z`
- sleep command returned: `2026-05-15T00:08:50Z`
- post-wake stabilization timestamp: `2026-05-15T00:09:20Z`

Post-attempt assertions still showed active sleep blockers:

- `PreventSystemSleep = 1`
- `PreventUserIdleSystemSleep = 1`
- `DenySystemSleep` from `InternetSharingPreferencePlugin`

## Six Checks

### 1. Supervisor restart semantics — FAIL

Expected: prior runtime marked failed with a specific reason code and a new runtime live/running with recent heartbeat.

Actual:

- pre runtime_instance_id: `runtime_11fd6f78de54427eb8b4b9ac56c721b6`
- post runtime_instance_id: `runtime_11fd6f78de54427eb8b4b9ac56c721b6`
- prior runtime status after proof: `live`
- prior runtime failure_code after proof: `None`
- post runtime status: `live`
- post runtime last_seen_at: `2026-05-15T00:10:28.504508Z`
- recent heartbeat within 120s: `true`

The supervisor stayed live; there was no prior-runtime failure marking and no new runtime instance.

### 2. Hash chain integrity — PASS

Expected: `ace audit verify` ok and chain head same or advanced, not regressed.

Actual:

- pre hash head id: `99362`
- pre hash: `095f3068a08acd4a528a20239f2a37f0c477cf36e4ce80532b4e821acee2dbdf`
- post hash head id: `99380`
- post hash: `fe55d1460bb6a8d2ca8f4a2a434cae5335d6c4450847bc78eb05877b013f6576`
- audit post returncode: `0`

Raw audit output:

```text
audit.verify.event_hash_chain=ok
audit.verify.db_path=/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db
```

### 3. No duplicate cycles — PASS

Expected: no two `governed_runs` rows in `status=running` simultaneously across sampled boundary.

Actual sampled active counts:

- pre: `0`
- post_wake_pre_cycle: `0`
- post_cycle: `0`
- current running rows: `[]`

### 4. No corrupted state — FAIL

Expected: items table count monotonically non-decreasing and no items in invalid state combinations.

Actual:

- pre items count: `85`
- post items count: `86`
- count monotonicity: PASS
- invalid item state combinations: FAIL

The artifact recorded `VERIFIED_DONE` rows with `closed_at=None`, `closed_by=None`, and `closed_reason=None`. The newest invalid row after the proof was:

```json
{
  "id": "item_b8457775b0b84ffaac01308f405da3be",
  "state": "VERIFIED_DONE",
  "verdict": "ship",
  "closed_at": null,
  "closed_by": null,
  "closed_reason": null,
  "updated_at": "2026-05-15T00:10:05.136967Z"
}
```

### 5. Cycle execution post-wake — PASS

Expected: trigger one launchd cycle after wake; confirm it completes with `status=completed` and no `failure_code`.

Actual:

- post-wake cycle run_id: `run_f762c675b1154e1886a2958e27037b22`
- trigger_kind: `launchd`
- status: `completed`
- created_at: `2026-05-15T00:09:27.576647Z`
- started_at: `2026-05-15T00:09:27.589153Z`
- ended_at: `2026-05-15T00:10:33.947567Z`
- failure_code: `None`
- failure_summary: `None`

### 6. Full ACE test suite green — PASS

Expected: full ACE suite passes.

Actual:

```text
Ran 548 tests in 40.903s

OK
```

## Final Raw Audit Output

```text
audit.verify.event_hash_chain=ok
audit.verify.db_path=/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db
```

## Final Result

This proof is not a clean PASS.

Failed checks:

1. Supervisor restart semantics did not occur as specified: the same runtime remained live, with no failed prior runtime and no replacement runtime.
2. No-corrupted-state check found `VERIFIED_DONE` items missing closeout fields.

Passed checks:

- hash chain integrity
- no duplicate running cycles in sampled state
- post-wake launchd cycle completed cleanly
- full ACE suite passed
