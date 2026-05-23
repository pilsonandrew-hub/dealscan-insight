# ACE V1.1 B-Cutover-Execute Design

Status: implementation design for the B-cutover-execute script. This document does not authorize executing the live cutover.

Related commits:

- B-append implementation: `a8a6393 ace: harden cutover genesis payload`
- Cutover design base: `58725a8 docs: address Ja'rvontis findings on cutover design before B-append`

Related documents:

- `ace/state/v1_1_required_items/cutover-event-design.md`
- `ace/state/v1_1_required_items/legacy-chain-defects.md`

## 1. Purpose

B-cutover-execute performs the one-time append of the ACE V1.1 cutover genesis event. It must make the atomic boundary explicit:

- Before the database commit, failures are safe to retry because no cutover event has been written.
- After the database commit, the cutover event is durable. Any follow-up failure must be reported as manual-recovery-required, not as a retryable pre-commit failure.

The script created in this slice is implementation only. It must not be run against the live database until Andrew separately approves B-cutover-execute.

## 2. Exact sequence of operations

The script performs these steps in order:

1. Parse arguments.
2. Resolve paths:
   - target ACE database path
   - durable JSONL execution log path
3. Open or create the durable log file and append `run.started` before any database action.
4. Perform read-only prerequisite checks and log before/after each check:
   - authorization token is present and equals `B_CUTOVER_EXECUTE_OPERATOR_APPROVED`
   - database file exists
   - legacy disclosure file exists
   - no existing `ace.chain.cutover.v1_1` row exists
   - legacy event inventory is non-empty
5. Open an ACE write connection with the approved append path.
6. Log `cutover.transaction.begin.before`.
7. Call `append_cutover_genesis_event(...)` inside the immediate transaction.
8. Log `cutover.append.after` with the generated cutover event id before committing.
9. Commit the transaction.
10. Log `cutover.commit.after` immediately after commit returns.
11. Run post-commit follow-up actions:
    - read back the cutover row
    - run `legacy_chain_inventory(db_path)`
    - run `post_cutover_event_hash_chain(db_path)`
    - write a recovery instruction record to the durable log
12. Log `run.completed` and exit success.

## 3. Order of operations and atomicity boundary

The only irreversible database action is the commit containing `append_cutover_genesis_event(...)`.

The script treats this as the boundary:

- `commit_completed=false`: no durable cutover has been committed by this script; failure is a pre-commit failure and is safe to retry after fixing the cause.
- `commit_completed=true`: the cutover event is durable; failure is a post-commit failure and must not be blindly retried. Operator must inspect the log and run recovery verification.

## 4. Failure-window handling

### 4.1 Pre-commit failure

A pre-commit failure is any failure before `connection.commit()` succeeds, including:

- missing/invalid authorization token
- missing database
- existing cutover row
- empty legacy event inventory
- schema/hash maintenance error before append
- append failure before commit

Required behavior:

- rollback the active transaction if one exists
- log `run.failed.pre_commit`
- exit with `10`
- recovery state: safe to retry after the logged cause is fixed

### 4.2 Post-commit failure

A post-commit failure is any failure after `connection.commit()` succeeds but before all follow-up actions complete, including:

- process crash after commit
- failure reading back the cutover row
- follow-up verifier failure
- failure writing the final success marker after commit

Required behavior:

- never rollback or attempt another cutover append
- log `run.failed.post_commit` when possible
- print a loud manual-recovery-required message
- exit with `20`
- recovery state: do not rerun the script as a normal retry; run recovery verification first

## 5. Manual recovery procedure

If the script exits `20` or crashes after `cutover.commit.after` appears in the durable log:

1. Do not rerun B-cutover-execute immediately.
2. Inspect the durable log path from the operator output.
3. Read the cutover event id from either:
   - the `cutover.commit.after` log record, or
   - the database query for the single `ace.chain.cutover.v1_1` event.
4. Run read-only verification:
   - `python3 -m ace.ace --db ace/state/ace.db audit verify`
5. Expected post-cutover state:
   - `audit.verify.legacy_chain_inventory=ok`
   - `audit.verify.event_hash_chain=ok`
   - `audit.verify.post_cutover_event_hash_chain=ok`
   - evidence/governed/runtime checks remain `ok`
6. If those checks pass, record manual recovery completion in the operator notes and continue to the next approved slice.
7. If any check fails, stop and escalate. Do not mutate pre-cutover rows and do not append a second cutover event.

The script writes these instructions into the durable log after commit and includes them in post-commit failure output.

## 6. Logging requirements

The script writes JSONL records to a durable log path before and after each major step. Each record includes:

- `timestamp`
- `run_id`
- `step`
- `status`
- `db_path`
- `commit_completed`
- optional `cutover_event_id`
- optional `detail`
- optional `recovery_instructions`

Required records:

- `run.started`
- `prerequisites.before`
- `prerequisites.after`
- `cutover.transaction.begin.before`
- `cutover.append.after`
- `cutover.commit.after`
- `post_commit.followup.before`
- `post_commit.followup.after`
- `run.completed`

Failure records:

- `run.failed.pre_commit`
- `run.failed.post_commit`

If log writing itself fails before commit, the script must treat that as pre-commit failure and not append the cutover. If log writing fails after commit, the process must return post-commit failure because the durable cutover may already exist without complete follow-up logging.

## 7. Exit codes

- `0` — success: cutover committed and post-commit follow-up completed.
- `10` — pre-commit failure: no cutover committed by this run; safe to retry after fixing the cause.
- `20` — post-commit failure: cutover may be committed; manual recovery required before any retry.
- `2` — CLI usage error from argument parsing.

## 8. Implementation boundaries

The implementation slice may create:

- `ace/scripts/b_cutover_execute.py`
- tests under `ace/tests/`
- this design document

The implementation slice must not execute the live cutover. Tests must use temporary databases only.

The only approved database-write path for the actual genesis row is `append_cutover_genesis_event(...)`. Normal `append_event(...)` must remain forbidden from writing `ace.chain.cutover.v1_1`.
