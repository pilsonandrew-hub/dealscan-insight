# ACE 1.0 Final Verification Bundle

Date: 2026-05-21
Verified proof source: `049e3c90362efc4d51a325fc68c25252395268ef` (`049e3c9 ace: exclude accepted historical health debt`)
Closeout/taggable HEAD: `94d3ebc1e295e1f7845e290e09990469338314aa` (`94d3ebc ci: quiet ace checkout default branch hint`)

## Classification

PASS — bounded ACE 1.0 local launchd + resident-supervisor + governed-cycle endurance slice.

This bundle is evidence-backed and intentionally narrow. It does not claim ACE 1.1, broad V1 platform/runtime fabric, distributed availability, raw Telegram Bot API inbound ownership, broad NLU, or production multi-tenant operation.

## Primary endurance artifact

- Path: `ace/state/endurance/24h-proof-20260520T042532Z.md`
- Proof window: `2026-05-20T04:25:32Z` → `2026-05-21T04:25:32Z`
- End snapshot verified at: `2026-05-21T04:28:50Z`
- End classification: `PASS`
- Restart performed before verification: `false`

Endurance PASS basis recorded in the artifact:

- Resident supervisor runtime stayed live across the full proof window and continued heartbeating after the 24h mark.
- Launchd cycle remained loaded and produced 48 completed launchd-triggered cycles after proof start.
- No failed, interrupted, skipped, stale runtime, action queue, or alert delivery blockers appeared after proof start.
- ACE audit verification passed at the end snapshot.
- Health summary was green with `issue_count=0`.
- ACE CI for proof HEAD `049e3c9` completed successfully.

## Source and status artifact

- `ace/STATUS.md` updated for closeout to current verified commit `049e3c9`.
- STATUS includes the endurance PASS reference, health summary at end of proof window, audit verify dimensions, local suite count, ACE CI run ID, and explicit proof/non-proof boundaries.

## Local test evidence

Command:

```bash
PYTHONWARNINGS=error python3 -m unittest discover ace/tests -t .
```

Result:

```text
Ran 606 tests in 69.217s
OK
```

## CI evidence

ACE CI for the verified proof source:

- Run ID: `26140889116`
- Head SHA: `049e3c90362efc4d51a325fc68c25252395268ef`
- Status: `completed`
- Conclusion: `success`
- Created: `2026-05-20T04:15:01Z`
- Updated: `2026-05-20T04:15:55Z`
- URL: `https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/26140889116`

ACE CI for closeout/taggable HEAD after the bundle and CI-warning cleanup:

- Run ID: `26206618235`
- Head SHA: `94d3ebc1e295e1f7845e290e09990469338314aa`
- Status: `completed`
- Conclusion: `success`
- Log scan: 0 `::error`, 0 `::warning`, 0 `deprecated`, 0 Node20-action deprecation hits, 0 default-branch hints
- URL: `https://github.com/pilsonandrew-hub/dealscan-insight/actions/runs/26206618235`

## Audit verification evidence

Command:

```bash
python3 -m ace.ace --db ace/state/ace.db audit verify
```

Result:

```text
audit.verify.event_hash_chain=ok
audit.verify.evidence_consistency=ok
audit.verify.governed_run_integrity=ok
audit.verify.runtime_instance_integrity=ok
audit.verify.db_path=ace/state/ace.db
```

The four named passing dimensions are:

1. `event_hash_chain`
2. `evidence_consistency`
3. `governed_run_integrity`
4. `runtime_instance_integrity`

## Health evidence at endurance end

From `ace/state/endurance/24h-proof-20260520T042532Z.md` end snapshot:

```text
health.ok=true
health.issue_count=0
health.active_action_count=0
health.failed_action_count=0
health.active_run_count=0
health.failed_run_count=0
health.skipped_run_count=0
health.active_runtime_count=1
health.stale_runtime_count=0
health.failed_runtime_count=0
health.failed_alert_count=0
health.alert_gap_count=0
```

Post-start blocker counters in the endurance artifact:

```text
new_runtime_rows_since_start=0
new_failed_or_stale_runtime_rows_since_start=0
non_completed_cycles_since_start=0
failed_interrupted_skipped_runs_since_start=0
new_action_queue_blockers_since_start=0
new_alert_failures_since_start=0
```

## Supervisor/runtime evidence

Endurance-window runtime:

```text
current_runtime.runtime_instance_id=runtime_e5ec064dd5ff4db0848291f6ab9111be
current_runtime.status=live
current_runtime.started_at=2026-05-20T04:03:23.838516Z
current_runtime.shutdown_status=not_requested
current_runtime.recovery_status=not_requested
supervisor_heartbeat_count_since_start=16995
new_runtime_rows_since_start=0
new_failed_or_stale_runtime_rows_since_start=0
```

Post-closeout re-verification observed the same runtime ID still live:

```text
current_runtime.runtime_instance_id=runtime_e5ec064dd5ff4db0848291f6ab9111be
current_runtime.status=live
current_runtime.started_at=2026-05-20T04:03:23.838516Z
current_runtime.last_seen_at=2026-05-21T04:57:09.552037Z
current_runtime.startup_status=completed
current_runtime.shutdown_status=not_requested
current_runtime.recovery_status=not_requested
```

The older terminal runtime row visible in supervisor status is historical pre-window debt already accepted/excluded by commit `049e3c9`; it is not a current blocker:

```text
last_terminal_runtime.runtime_instance_id=runtime_ce0af3d6d7594fe49a1581b4d8a06bab
last_terminal_runtime.status=failed
last_terminal_runtime.failure_code=supervisor_process_missing
```

## Launchd/cycle evidence

Endurance end snapshot:

```text
launchd.ai.superace.cycle=loaded pid=- last_exit=0
launchd.ai.superace.supervisor=loaded pid=44408 last_exit=-15
cycle_start_interval_seconds=1800
cycles_since_start=48
last_terminal_run.run_id=run_71c8bf4a26204513b7bf99ba0c18504b
last_terminal_run.status=completed
last_terminal_run.trigger_kind=launchd
last_terminal_run.ended_at=2026-05-21T04:08:07.355936Z
failed_interrupted_skipped_runs_since_start=0
```

Post-closeout re-verification observed a newer completed launchd cycle:

```text
current_run_present=false
last_terminal_run.run_id=run_1963fb515dc84ba6a12e741943cd378e
last_terminal_run.trigger_kind=launchd
last_terminal_run.status=completed
last_terminal_run.created_at=2026-05-21T04:38:07.851213Z
last_terminal_run.started_at=2026-05-21T04:38:07.853842Z
last_terminal_run.ended_at=2026-05-21T04:38:08.906376Z
last_terminal_run.failure_code=None
last_terminal_run.failure_summary=None
```

## Current proof boundary

ACE 1.0 proves:

- bounded local launchd cycle continuity;
- resident supervisor continuity over the 24h proof window;
- governed run lifecycle/audit integrity;
- accepted historical-health-debt handling at commit `049e3c9`;
- green health summary with zero current issue count at closeout;
- full local ACE test suite success under `PYTHONWARNINGS=error`;
- ACE CI success for the verified source commit.

ACE 1.0 does not prove:

- ACE 1.1 scope;
- broad natural-language understanding;
- raw Telegram Bot API inbound ownership;
- distributed or high-availability runtime fabric;
- external provider spend attribution;
- broad platform autonomy;
- production multi-tenant operation.

## Tagging rule

Tag `ace-1.0` must point at the closeout/taggable HEAD that contains this bundle and `ace/STATUS.md`, not at an older pre-bundle commit. V1.1 work must not begin until the corrected `ace-1.0` tag exists on that closeout commit.
