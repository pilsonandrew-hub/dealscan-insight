# A.C.E. Local Foundation Completion Gate — 2026-05-14

## Verdict

PASS for the local governed resident foundation completion gate.

FAIL / UNEARNED for A.C.E. V1, platform/runtime-fabric, raw live Telegram Bot API polling acceptance, and sleep/network resilience.

This report packages what is actually proven and stops short of the claims that are not earned.

## Baseline

- Source HEAD at gate: `cef4090` (`ace: broaden telegram proceed parser`)
- Runtime DB: `/Users/andrewpilson/.openclaw/workspace/ace/state/ace.db`
- Telegram runtime DB: `/Users/andrewpilson/.openclaw/workspace/ace/state/telegram_runtime.db`
- Production Telegram transport: `ACE_TELEGRAM_TRANSPORT=openclaw_session`
- Raw Bot API shared-token conflict report: `ace/reports/ace-raw-telegram-shared-token-conflict-2026-05-14.md`
- V1 gate definition remains: `ace/reports/ace-next-v1-gates-telegram-sleep-runtime-2026-05-13.md`

## What is done

- Governed item lifecycle exists and is exercised.
- Evidence / approval / done / resolve path exists and is exercised.
- Correction lineage exists.
- Confidence tiers exist.
- Canonical verdicts exist.
- Verdict is wired into closeout gating.
- Closeout requires supporting evidence.
- Launchd-backed supervisor and launchd-triggered cycle execution are live.
- Governed cycle single-flight behavior exists: concurrent cycle attempts record a skipped terminal run with `failure_code=cycle_already_active` instead of executing concurrently.
- Tamper-evident local event hash chain exists and verifies cleanly.
- Telegram transport selector exists with explicit transport modes.
- Safe OpenClaw session-stream transport is pinned in launchd for production.
- OpenClaw session-stream transport records durable `telegram_transport_attempts` rows.
- Parser direct-work gap for `continue` / `proceed` was fixed.
- Fresh post-parser live Telegram direct-work messages reached `VERIFIED_DONE` with `verdict=pass` under launchd-managed cycle execution.

## Gate 1-A — Safe OpenClaw session-stream evidence

This gate is earned for the safe `openclaw_session` path.

Live evidence:

- Launchd-managed governed run: `run_1348435e66ee4a20bff5f42803acd13b`
- Trigger: `launchd`
- Status: `completed`
- Runtime window: `2026-05-14T01:55:26.030273Z` to `2026-05-14T01:57:01.082769Z`
- Transport attempt: `transport=openclaw_session`, `status=ok`, `message_count=129`
- Controlled direct-work message: `telegram:7529788084:34719`
  - Item: `item_124ba0260ee84e0896a493ff92a96cc7`
  - Final state: `VERIFIED_DONE`
  - Verdict: `pass`
- Controlled direct-work message: `telegram:7529788084:34721`
  - Item: `item_ff5627bc2ff54bc495713f8b6029bd35`
  - Final state: `VERIFIED_DONE`
  - Verdict: `pass`

Current later launchd runs also remain healthy; the latest re-grounded terminal run observed during this report was `run_86bd5633af884ebb973ac3848b7ed01f`, `trigger_kind=launchd`, `status=completed`, with no failure code.

## Validation gate

Validation run after the completion evidence:

- Full ACE suite under warnings-as-errors: `PYTHONWARNINGS=error python3 -m unittest discover ace/tests -t .` → `529 OK`
- Event hash chain: `(True, None)`
- Current cycle status: no current run, latest terminal run completed via launchd.

## What is not done

- A.C.E. is not V1.
- A.C.E. is not a broad platform or runtime fabric.
- Raw live Telegram Bot API polling is not accepted for the shared OpenClaw bot token.
- Sleep/wake resilience is not proven.
- Network-blip resilience is not proven.
- Dedicated ACE Telegram bot/token ownership is not implemented.
- OpenClaw-mediated queue/webhook handoff is not implemented.
- Distributed/high-availability behavior is not claimed.

## Raw Telegram Bot API boundary

Raw Bot API polling with the shared OpenClaw Telegram bot token is blocked by Telegram `getUpdates` single-poller conflict.

This is not a missing-token defect. A.C.E. can reach Telegram through the governed OpenClaw token source, but OpenClaw already owns the shared bot token for live inbound chat. Scheduled A.C.E. raw polling cannot safely share that token.

Valid future paths:

1. Dedicated A.C.E. Telegram bot/token.
2. OpenClaw-mediated queue/webhook handoff.
3. Keep `openclaw_session` as the production transport and remove shared-token raw polling from near-term acceptance.

Current recommendation: keep production pinned to `openclaw_session`, stop feature expansion, and move next to resilience proof and packaging.

## Allowed claim

A.C.E. has a tested local governed resident foundation with launchd-backed cycles, tamper-evident local event history, governed closeout rules, and live Telegram direct-work closure through the safe OpenClaw session-stream transport.

## Forbidden claims

Do not claim:

- A.C.E. is V1.
- A.C.E. is a platform.
- A.C.E. is a production runtime fabric.
- Raw Telegram Bot API polling is accepted using the shared OpenClaw bot token.
- Sleep/network resilience is proven.
- Transport ownership is fully solved beyond the current OpenClaw session-stream path.

## Next recommended actions

1. Freeze feature expansion and treat this as the local foundation milestone.
2. Run a controlled sleep/network resilience proof with pre/post supervisor, cycle, transport, and hash-chain evidence.
3. Decide the long-term Telegram ownership model only after resilience proof: dedicated ACE bot, OpenClaw-mediated queue/webhook, or continued OpenClaw session-stream dependency.

## Independent reviewer follow-up — 2026-05-14

Andrew asked whether external reviewers had been consulted on the Telegram/runtime blocker. The earlier Gemini/OpenRouter review had already recommended staying on the safe `openclaw_session` path and packaging the local foundation instead of forcing shared-token raw Bot API polling.

A follow-up consult was retried through the local Paperclip/OpenRouter bridge after route/funding conditions improved:

- Claude route: `openrouter_claude_review` / `anthropic/claude-opus-4.7`
- DeepSeek route: `openrouter_deepseek_workhorse` / `deepseek/deepseek-v3.2`

Reviewer consensus:

- The local governed resident foundation is proven enough to package as a foundation milestone.
- Gate 1-A on `openclaw_session` is the accepted production Telegram path for this milestone.
- Raw Bot API polling with the shared OpenClaw bot token should not be pursued further; Telegram single-poller conflict is a real boundary, not an implementation bug to keep rediscovering.
- A.C.E. must still not be called V1.
- Sleep/network resilience remains unearned and should be tested separately under a controlled gate.
- Any future raw Bot API work should be a separate scoped decision: dedicated ACE bot token or OpenClaw-mediated queue/webhook handoff.

Plain-English decision:

Continue with the OpenClaw runtime event on the safe `openclaw_session` path. Freeze feature expansion for this foundation milestone. Do not pivot transport ownership in this slice. Do not claim V1.
