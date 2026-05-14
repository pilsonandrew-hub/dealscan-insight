# ACE Sleep/Wake Resilience Proof — 2026-05-14

## Scope

Bounded Item 3 proof attempt for ACE sleep/wake resilience on the current `openclaw_session` path.

Acceptance target:
- capture pre-sleep ACE state
- invoke `pmset sleepnow`
- wake after a fixed interval
- verify supervisor recovered/remained live
- verify event hash chain remained intact
- verify no duplicate cycles
- run the full ACE test suite

## Artifact

Primary artifact:

`/tmp/ace-sleep-wake-proof-20260514T235509Z.txt`

## Pre-state

- Git status: clean (`## master`)
- Pre-cycle state: no current run
- Last terminal run before proof: `run_ab46d94a680940d18a2c4cc611ee3fd7`, `completed`, `trigger_kind=launchd`, no failure
- Supervisor runtime before proof: `runtime_11fd6f78de54427eb8b4b9ac56c721b6`, `status=live`
- Audit verify before proof: `audit.verify.event_hash_chain=ok`
- Direct hash check before proof: `(True, None)`

## Sleep/wake execution result

Attempted wake scheduling and sleep command:

- requested local wake time: `05/14/26 16:56:57`
- `pmset sleepnow` invoked at `2026-05-14T23:55:57Z`
- post-wake observation timestamp: `2026-05-14T23:55:58Z`

The command returned almost immediately. `pmset -g assertions` showed active system sleep blockers, including:

- `PreventSystemSleep = 1`
- `PreventUserIdleSystemSleep = 1`
- `InternalPreventSleep = 1`
- `DenySystemSleep` from `InternetSharingPreferencePlugin`

The attempted fixed wake schedule did not remain listed in `pmset -g sched`; the artifact captured `pmset: This operation must be run as root` during the run. This proof therefore does not establish a full machine sleep interval.

## Post-attempt ACE behavior

After the attempted sleep command, the supervisor remained live:

- supervisor runtime: `runtime_11fd6f78de54427eb8b4b9ac56c721b6`
- status: `live`
- startup status: `completed`
- recovery status: `not_requested`

A post-attempt launchd cycle was triggered and completed cleanly:

- cycle: `run_52575b25ad0a40cf9513a73550e7dea5`
- trigger: `launchd`
- status: `completed`
- started: `2026-05-14T23:56:16.566091Z`
- ended: `2026-05-14T23:56:51.061752Z`
- failure code: `None`
- failure summary: `None`

Transport evidence after the attempt:

- transport: `openclaw_session`
- status: `ok`
- message_count: `57`

## Verification

Full ACE suite:

```text
Ran 548 tests in 40.741s
OK
```

Audit verify:

```text
audit.verify.event_hash_chain=ok
audit.verify.db_path=/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db
```

Direct hash check:

```text
(True, None)
```

Final git status:

```text
## master
```

## Result

Partial evidence only.

The post-attempt ACE path passed: supervisor remained live, the post-attempt launchd cycle completed, `openclaw_session` transport worked, tests passed, and the event hash chain stayed valid.

The full sleep/wake acceptance bar is not met because the host did not demonstrate a real 60-second sleep/wake interval. The concrete blocker is host-level sleep prevention / wake scheduling permission, not an ACE cycle failure.
