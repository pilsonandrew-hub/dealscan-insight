#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

QUEUE_PATH = Path('/Users/andrewpilson/.openclaw/workspace/continuity/pending-promotions.json')


def main() -> int:
    data = json.loads(QUEUE_PATH.read_text())
    changed = False
    for item in data.get('items', []):
        if item.get('status') == 'promoted':
            if not item.get('destination'):
                item['destination'] = 'policy'
                changed = True
            if not item.get('destination_ref'):
                item['destination_ref'] = 'legacy-history-migration'
                changed = True
    if changed:
        QUEUE_PATH.write_text(json.dumps(data, indent=2) + '\n')
    print(f'changed={changed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
