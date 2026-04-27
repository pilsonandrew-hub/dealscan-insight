# ACE Operator Handoff Checklist

Date: 2026-04-27

## What ACE is
- Governed Foundation / Phase 0 continuity substrate
- local-only
- operator-invoked
- SQLite-backed
- bounded to landed seams and governed doctrine

## What ACE is not
- not V1
- not a daemon/service
- not a scheduler or worker-pool runtime
- not a generalized orchestration platform
- not a continuity-source writeback system
- not a production runtime product

## Safe things to rely on
- current bounded seam behavior proven by tests
- local runtime ownership behavior
- local resume/recovery behavior
- owned-recovery composed lifecycle behavior
- replay-healing only where explicitly proven
- evidence non-duplication only where explicitly proven

## Unsafe claims to avoid
- “ACE is production-ready”
- “ACE is V1”
- “ACE owns external/source writeback”
- “ACE is a generalized runtime platform”
- “ACE has daemon/scheduler/service guarantees”

## Baseline check before trusting state
Run:
- `python3 -m unittest ace.tests.test_runtime_ownership`
- `python3 -m unittest ace.tests.test_resume_runtime`
- `python3 -m unittest ace.tests.test_resume_recovery_runtime`
- `python3 -m unittest ace.tests.test_owned_recovery_runtime`
- `python3 -m unittest discover -s ace/tests -t .`

Expected current truth:
- runtime ownership: 10 OK
- resume runtime: 7 OK
- resume recovery runtime: 6 OK
- owned recovery runtime: 4 OK
- full suite: 374 OK

## If someone wants to push ACE toward V1 later
Do not restart seam-mining.
First make an explicit decision to open a larger runtime-class expansion program.

## Primary closure artifacts
- `reports/ace-option-a-governed-foundation-decision-2026-04-27.md`
- `reports/ace-executive-summary-2026-04-27.md`
- `reports/ace-foundation-vs-v1-runtime-decision-memo-2026-04-27.md`

## Bottom line
Operate ACE as a trustworthy bounded internal foundation.
Do not describe it as more than that without a deliberate new program.
