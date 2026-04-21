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


def main() -> int:
    state = load_json(STATE_PATH, {})
    closeout = load_json(CLOSEOUT_PATH, {})
    open_loops = load_json(OPEN_LOOPS_PATH, {"items": []}).get("items", [])
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    blocking = state.get('blocking_reasons', [])
    advisory = state.get('advisory_reasons', [])
    derived_state = state.get('derived_state', 'unknown')
    open_active = state.get('open_loops', {}).get('active', 0)

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
        "## Next Actions",
        "- Resolve governed dirty state or classify it explicitly via future override path",
        "- Keep Stage 0 in audit mode until closeout and briefing surfaces are trustworthy",
        "- Do not claim clean continuity while blocking reasons remain",
        "",
        "## CTO Note",
        "- Continuity OS Stage 0 is live but not clean. The system is now detecting real drift instead of producing fake green status. Current drag is governed workspace dirtiness, and the next hardening step is making daily briefing and closeout semantics operationally trustworthy.",
        "",
    ])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines))
    print(str(OUTPUT_PATH))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
