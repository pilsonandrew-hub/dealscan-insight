# ACE Current Next Steps — 2026-05-05

## Current truth
- Super A.C.E. is a **governed foundation / Phase 0 continuity substrate with multiple narrow local-only proven seams**.
- ACE is **real**.
- ACE is **not V1**.
- The old 8-gate / seam-breadth roadmap is now a **hardening / V2 track**, not the V1 launch path.

## Active V1 critical path
1. `ace/sweep.py` ✅ landed
2. `ace/briefing.py` ✅ landed
3. bounded notification/runtime delivery seam ✅ landed
4. bounded autonomous cycle seam (`ace/cycle.py`) ✅ landed
5. LaunchAgent/runtime scheduling ✅ landed and live-proven
6. one real end-to-end proof ✅ landed and live-proven

## Exact next file to build
- The activation-first launch path is proven. Do not reopen it.
- The broader ownership/recovery hard-gate lane remains blocked on the current local runtime class. Do not reopen it.
- The bounded governed-run lifecycle slice for local-only `ace cycle` is landed and verified.
- The bounded E1 resident supervisor identity slice is landed and verified.
- The bounded E2 startup/shutdown ownership slice is now also landed and verified for the resident supervisor seam.
- The bounded E3 active runtime inspection slice is now also landed and verified for that same resident supervisor seam.
- The bounded E4 runtime failure/recovery contract slice is now also landed and verified for that same resident supervisor seam.
- The bounded E5 anti-inflation boundary proof slice is now also landed and verified for that same resident supervisor seam.
- The bounded E6 distinct minimal slice proof slice is now also landed and verified for that same resident supervisor seam.
- Therefore the next honest build target is whatever bounded post-E6 runtime obligation can be made real on disk without inflating into V1 theater.
- Governing authority for current E1 truth: `reports/ace-e1-resident-supervisor-identity-verdict-2026-05-07.md`
- Governing authority for current E2 truth: `reports/ace-e2-startup-shutdown-ownership-gate-2026-05-07.md`
- Governing authority for current E3 truth: `reports/ace-e3-active-runtime-inspection-surface-verdict-2026-05-07.md`
- Governing authority for current E4 truth: `reports/ace-e4-runtime-failure-recovery-contract-verdict-2026-05-07.md`
- Governing authority for current E5 truth: `reports/ace-e5-anti-inflation-boundary-proof-verdict-2026-05-07.md`
- Governing authority for current E6 truth: `reports/ace-e6-distinct-minimal-slice-proof-verdict-2026-05-07.md`
- Governing execution discipline remains ordered by `reports/ace-next-runtime-evidence-execution-order-2026-05-06.md`
- The failed 2026-05-06 next-runtime-class chain remains closed by `reports/ace-hard-gate-next-runtime-class-chain-closure-2026-05-06.md` and must not be reused as a live build path.

## Anti-drift rule
If a task does not directly improve one of these, it is drift:
- sweep truth
- briefing truth
- notification reliability
- scheduling reality
- end-to-end operational proof

## Recovery anchor
Primary activation-first plan artifact:
- `reports/ace-activation-first-plan-2026-05-05.md`

Primary post-activation hard-gate verdict artifacts:
- `reports/ace-hard-gate-next-program-2026-05-05.md`
- `reports/ace-hard-gate-runtime-ownership-recovery-go-block-2026-05-05.md`

## Verified current proof
- `ace/sweep.py` is landed as the first bounded activation slice.
- `ace/briefing.py` is landed as the first read-only operator briefing slice grounded in live ACE DB truth.
- `ace/action_runtime.py` now includes a bounded operator-notification action seam (`send_operator_notification`) built on durable `action_queue` semantics with replay-safe enqueue/claim/execute flow and explicit `action_failed_notification` / `action_failed_runtime_error` failure states.
- `ace/action_runtime.py` no longer uses `openclaw message send` CLI for scheduler-path notifications. The live sender path is Gateway loopback `POST /tools/invoke` with bearer auth loaded from local OpenClaw config, specifically to avoid the proven session-transcript lock collision on the CLI path.
- `ace/cycle.py` is landed as the bounded autonomous operator cycle seam: it runs sweep, regenerates the briefing, writes the briefing file, and drives notification orchestration from the live seams instead of faking autonomy through `sweep` alone.
- LaunchAgent/runtime scheduling is live-proven: the user-scoped LaunchAgent loads the real `ace cycle` wrapper and executes on schedule against the live ACE DB.
- Real end-to-end notification proof is live-proven: a seeded stale ACTIVE item (`item_2a98cad966f94e1bace244372ecbc7fe`) produced a completed notification action (`action_0f69b18c6f9f12f7efc288c33bfe5c06844fafcb367bbbe70306394a15d167ad`), canonical `ace://notification/delivery` evidence (`evidence_5b185b8163b14ccb9bb1957d260b0a52`), and OpenClaw-recorded Telegram delivery metadata (`messageId` `29370`, `chatId` `7529788084`).
- Targeted notification runtime proof passes: `python3 -m unittest ace.tests.test_action_runtime` and `PYTHONWARNINGS=error python3 -m unittest ace.tests.test_action_runtime` both pass at 21 tests OK.
- Targeted cycle proof passes: `python3 -m unittest ace.tests.test_cycle` and `PYTHONWARNINGS=error python3 -m unittest ace.tests.test_cycle` both pass at 3 tests OK.
- Bounded governed-run lifecycle slice is now landed for local-only `ace cycle`:
  - dedicated `governed_runs` persistence surface
  - dedicated governed lifecycle helper module
  - bounded `cycle-status` inspection surface
  - cycle success/failure/interruption terminalization with bounded briefing/notification references
  - targeted governed-run slice validation passes: `python3 -m unittest ace.tests.test_governed_run_runtime ace.tests.test_cycle ace.tests.test_governed_run_cli` -> 9 tests OK
- `python3 -m unittest discover ace/tests` passes: 422 tests OK.
- staged-tree re-verification also passes cleanly: 422 tests OK.
- CLI smoke proof passes for the real bounded cycle: `python3 ace/ace.py --db /tmp/ace-cycle-smoke.db cycle --briefing-path /tmp/ace_briefing.md` writes the briefing file and completes without fake notification claims when there are no actionable findings.
- SQLite hygiene defect was real and is now fixed in affected tests by replacing misleading `with sqlite3.connect(...)` usage with explicit close discipline.
- Post-implementation verification artifact exists for the bounded governed-run slice:
  - `reports/ace-hard-gate-governed-run-lifecycle-slice-post-implementation-verification-2026-05-05.md`
- The later 2026-05-06 next-runtime-class authority chain is closed as a failed forward implementation program because its implementation gate resolves to the same slice already landed above.
- Closure authority: `reports/ace-hard-gate-next-runtime-class-chain-closure-2026-05-06.md`
- The bounded resident supervisor seam now also carries explicit startup/shutdown ownership truth with targeted supervisor validation at 13/13 and full-suite validation at 417/417.
- That same resident supervisor seam now also carries bounded active runtime inspection truth with append-only transition history surfaced through supervisor inspection, targeted supervisor validation at 14/14, and full-suite validation at 418/418.
- That same resident supervisor seam now also carries bounded runtime failure/recovery contract truth with ACE-owned recovery request/result history surfaced through supervisor inspection, targeted supervisor validation at 18/18, and full-suite validation at 422/422.
- That same resident supervisor seam now also carries bounded anti-inflation boundary proof with explicit inspection-surface claims/non-claims surfaced through supervisor inspection, targeted supervisor validation at 18/18, and full-suite validation at 422/422.
- That same resident supervisor seam now also carries bounded distinct minimal slice proof with explicit slice definition, exact E1–E5 artifact bundle, and explicit non-reduction proof surfaced through supervisor inspection, targeted supervisor validation at 18/18, and full-suite validation at 422/422.
