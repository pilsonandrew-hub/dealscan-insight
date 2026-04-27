# ACE V1 Program 3 — Failure and Recovery Breadth Charter

Date: 2026-04-27
Status: opened / charter only

## Grounded baseline
- Main HEAD: `40d9805`
- `test_runtime_ownership`: 10 OK
- `test_resume_runtime`: 7 OK
- `test_resume_recovery_runtime`: 6 OK
- `test_owned_recovery_runtime`: 4 OK
- Full ACE suite: 374 OK

## Why Program 3 exists
Program 1 runtime breadth is blocked on the current bounded seam family.
The next highest-leverage V1 substance gap is broader failure and recovery truth.

ACE has real bounded failure/recovery proofs today, but they are still too narrow to justify V1.

## Current honest starting point
ACE today is:
- a governed foundation / Phase 0 continuity substrate
- local-only
- operator-invoked
- SQLite-backed
- proof-oriented
- bounded to explicitly landed seams

ACE today is not:
- V1
- a daemon
- a scheduler
- a worker pool
- a generalized orchestration platform
- a production runtime service
- a continuity-source writeback system

## Program 3 goal
Prove materially broader local-only failure and recovery truth than the current bounded seam family.

## Program 3 success condition
Program 3 succeeds only if Gate 4 can move from partial/blocked into pass by proving broader failure/recovery truth in code/tests/governed truth.

## Candidate directions
A candidate survives only if it materially broadens at least one real dimension such as:
- terminal failure shape
- bounded failure ordering shape
- replay-after-failure obligation shape
- inspectable failure contract shape
- connected cross-seam failure/recovery shape

## Not allowed
Program 3 must reject:
- renamed clones of already-landed failure/recovery seam cases
- doctrine churn without new failure/recovery leverage
- raw test-count inflation
- daemon/service/platform/writeback inflation
- schema widening before proof necessity

## Required execution order
1. distinctness review
2. keep at most one real survivor
3. implementation-proof spec
4. isolated TDD lane only if the survivor remains real
5. main landing only if validated
6. governed truth update only if landing is real
7. explicit Gate 4 verdict

## First question
What is the first materially broader failure/recovery family that survives distinctness review without collapsing into the already-landed seam proofs?

## Blocker rule
If no materially broader survivor exists, Program 3 must stop cleanly and report blocked instead of inventing work.

## Bottom line
Program 3 is now the active next larger V1 program.
No code is justified yet.
The next honest step is Program 3 distinctness review.
