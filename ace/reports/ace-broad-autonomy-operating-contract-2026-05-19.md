# ACE Broad Autonomy Operating Contract — 2026-05-19

## Verdict

ACE is being moved toward a broad autonomous operating layer, but broad does not mean unconstrained. The production contract is:

- ACE may autonomously absorb bounded operator-continuation directives.
- ACE must not silently auto-close broad direct work from Telegram just because the parser recognized it as actionable.
- Broad direct work must carry an explicit governed-execution obligation until ACE attaches concrete execution evidence or escalates.
- Duplicate semantic continuation noise must coalesce rather than create new items or repeat user-facing notifications.

## Intake classes

### 1. Non-actionable chatter
Ignored by parser. No item, no evidence, no obligation.

### 2. Bounded operator continuation
Examples: `continue`, `proceed`, `keep working`, `continue on that path`.

Allowed autonomous behavior:
- create or reuse a Telegram direct-work item;
- mark it autonomy-eligible with explicit policy reason;
- allow the autonomy lane to complete it when bounded evidence supports closeout.

### 3. Broad direct work
Examples: `please investigate`, `audit`, `fix`, `review`, `check`, `harden`, and similar recognized direct-work commands that are not merely continuation directives.

Required behavior:
- create or reuse a Telegram direct-work item;
- preserve source and parser evidence;
- do **not** mark it autonomy-eligible at intake;
- create an open `governed_execution_required` obligation on the item;
- keep the item open until later governed execution evidence or escalation resolves the obligation.

## Current implementation proof

Commit before this report: `e0b61d8 Tighten ACE autonomy boundaries and shutdown control`.

New enforcement added after that commit:
- `ace/telegram_intake.py` now creates a `governed_execution_required` obligation for non-autonomy-eligible actionable Telegram direct work.
- `ace/tests/test_telegram_intake.py` verifies broad direct work gets no autonomy eligibility evidence and receives exactly one governed-execution obligation.
- `ace/tests/test_cycle.py` verifies a launchd cycle keeps broad direct work in `TRIAGE` with an open obligation instead of autonomously closing it.

Validation run:
- `python3 -m unittest ace.tests.test_cycle ace.tests.test_telegram_intake ace.tests.test_telegram_parser ace.tests.test_autonomy_lane`
- Result: `Ran 43 tests in 369.405s — OK`.

## Anti-inflation boundary

This is not yet full broad autonomy. It is the operating contract and first enforcement gate for safe broad autonomy. The next valid slice is a governed executor that can pick up `governed_execution_required` obligations, produce concrete work-plan/execution evidence, resolve the obligation, and only then close the item or escalate.
