#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path('/Users/andrewpilson/.openclaw/workspace')
CONTINUITY = WORKSPACE / 'continuity'
CANON = WORKSPACE / 'brains/dealerscope-brain' / '03_Operations'
STATE_PATH = CONTINUITY / 'continuity-state.json'
CLOSEOUT_PATH = CONTINUITY / 'closeout-evaluation.json'
OPEN_LOOPS_PATH = CONTINUITY / 'open-loops.json'
OUTPUT_PATH = CANON / f"DealerScope-Morning-Briefing-{datetime.now().date().isoformat()}.md"


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def infer_promotion_candidates(state: dict, closeout: dict, open_loops: list[dict]) -> list[str]:
    candidates: list[str] = []
    pending_promotions = state.get('pending_promotions', [])
    for item in pending_promotions:
        candidates.append(f"pending_promotion: {item}")

    if closeout.get('blocked_if_enforced'):
        candidates.append("closeout_policy_or_state_change: current closeout would block if enforcement were enabled")

    malformed = state.get('open_loops', {}).get('malformed', 0)
    if malformed:
        candidates.append(f"open_loop_schema_or_process_fix: {malformed} malformed open loops detected")

    for loop in open_loops:
        if loop.get('promote') is True:
            candidates.append(f"open_loop_marked_for_promotion: {loop.get('id', 'missing-id')} {loop.get('title', 'untitled')}")

    deduped = []
    seen = set()
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def main() -> int:
    state = load_json(STATE_PATH, {})
    closeout = load_json(CLOSEOUT_PATH, {})
    open_loops = load_json(OPEN_LOOPS_PATH, {"items": []}).get("items", [])
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    blocking = state.get('blocking_reasons', [])
    advisory = state.get('advisory_reasons', [])
    derived_state = state.get('derived_state', 'unknown')
    open_active = state.get('open_loops', {}).get('active', 0)
    promotion_candidates = infer_promotion_candidates(state, closeout, open_loops)

    lines = [
        f"# DealerScope Morning Briefing - {datetime.now().date().isoformat()}",
        "",
        f"Generated at: {now}",
        "",
        "## Continuity Status",
        f"- overall_state: {state.get('overall_state', 'unknown')}",
        f"- derived_state: {derived_state}",
        f"- blocked_if_enforced: {closeout.get('blocked_if_enforced', False)}",
        f"- branch: {state.get('branch', 'unknown')}",
        f"- head: {state.get('head', 'unknown')}",
        "",
        "## Blocking Reasons",
    ]
    if blocking:
        lines.extend([f"- {item}" for item in blocking])
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Advisory Reasons",
    ])
    if advisory:
        lines.extend([f"- {item}" for item in advisory])
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Open Loops",
        f"- active_count: {open_active}",
    ])
    if open_loops:
        for item in open_loops:
            lines.append(f"- {item.get('id', 'missing-id')}: {item.get('title', 'untitled')} [{item.get('status', 'unknown')}] next_start={item.get('next_start', 'missing')}")
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Replication",
        f"- pending_replication: {', '.join(closeout.get('missing_requirements', {}).get('pending_replication', [])) or 'none'}",
        f"- mirror_named_paths_failed: {len(state.get('mirror_status', {}).get('named_paths_failed', []))}",
        "",
        "## Promotion Candidates",
    ])
    if promotion_candidates:
        lines.extend([f"- {item}" for item in promotion_candidates])
    else:
        lines.append("- none")

    next_actions = []
    if blocking:
        next_actions.append("Resolve blocking continuity reasons before claiming closure")
    if advisory:
        next_actions.append("Resolve advisory drift before tightening enforcement posture")
    if promotion_candidates:
        next_actions.append("Classify and promote any durable truth surfaced in promotion candidates")
    if not next_actions:
        next_actions.append("Maintain clean aligned continuity state while expanding promotion discipline and later-stage controls")

    lines.extend([
        "",
        "## Next Actions",
    ])
    lines.extend([f"- {item}" for item in next_actions])

    lines.extend([
        "",
        "## CTO Note",
        f"- Continuity OS current state: {state.get('overall_state', 'unknown')} / {derived_state}. Briefing projection integrity is now explicit. Next hardening priority is promotion discipline becoming first-class operational output instead of living only in doctrine.",
        "",
    ])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines))
    print(str(OUTPUT_PATH))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
