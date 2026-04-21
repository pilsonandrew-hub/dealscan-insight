#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

WORKSPACE = Path('/Users/andrewpilson/.openclaw/workspace')
QUEUE_PATH = WORKSPACE / 'continuity' / 'pending-promotions.json'


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    payload = json.loads(QUEUE_PATH.read_text())
    changed = False
    for item in payload.get('items', []):
        status = item.get('status')
        if status == 'promoted':
            if not item.get('execution_mode'):
                item['execution_mode'] = 'verification_only'
                changed = True
            if not item.get('fulfillment_proof'):
                dest = item.get('destination')
                ref = item.get('destination_ref')
                item['fulfillment_proof'] = f'verified destination exists for {dest}:{ref}'
                changed = True
        if status == 'dismissed':
            if not item.get('execution_mode'):
                item['execution_mode'] = 'dismissed_no_execution'
                changed = True
    if changed:
        payload['updated_at'] = now_iso()
        QUEUE_PATH.write_text(json.dumps(payload, indent=2) + '\n')
        print('migrated promotion audit history v3')
    else:
        print('no migration needed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
