#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path('/Users/andrewpilson/.openclaw/workspace')
QUEUE_PATH = WORKSPACE / 'continuity' / 'pending-promotions.json'
ALLOWED_STATUS = {'pending', 'promoted', 'dismissed'}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_queue() -> dict:
    if not QUEUE_PATH.exists():
        return {'version': 1, 'updated_at': None, 'items': []}
    try:
        return json.loads(QUEUE_PATH.read_text())
    except Exception:
        return {'version': 1, 'updated_at': None, 'items': []}


def write_queue(payload: dict) -> None:
    payload['updated_at'] = now_iso()
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(payload, indent=2) + '\n')


def find_item(items: list[dict], item_id: str) -> dict | None:
    for item in items:
        if item.get('id') == item_id:
            return item
    return None


def cmd_add(args) -> int:
    payload = load_queue()
    items = payload.setdefault('items', [])
    if find_item(items, args.id):
        raise SystemExit(f'item already exists: {args.id}')
    items.append({
        'id': args.id,
        'title': args.title,
        'source': args.source,
        'reason': args.reason,
        'created_at': now_iso(),
        'status': 'pending',
        'resolution': None,
        'resolved_at': None,
    })
    write_queue(payload)
    print(f'added {args.id}')
    return 0


def cmd_update(args, status: str) -> int:
    payload = load_queue()
    items = payload.setdefault('items', [])
    item = find_item(items, args.id)
    if not item:
        raise SystemExit(f'missing item: {args.id}')
    item['status'] = status
    item['resolution'] = args.note or None
    item['resolved_at'] = now_iso()
    write_queue(payload)
    print(f'{status} {args.id}')
    return 0


def cmd_list(args) -> int:
    payload = load_queue()
    items = payload.get('items', [])
    if args.status:
        items = [item for item in items if item.get('status') == args.status]
    print(json.dumps({'version': payload.get('version', 1), 'updated_at': payload.get('updated_at'), 'items': items}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Manage continuity promotion queue lifecycle')
    sub = parser.add_subparsers(dest='command', required=True)

    add = sub.add_parser('add')
    add.add_argument('--id', required=True)
    add.add_argument('--title', required=True)
    add.add_argument('--source', required=True)
    add.add_argument('--reason', required=True)
    add.set_defaults(func=cmd_add)

    resolve = sub.add_parser('resolve')
    resolve.add_argument('--id', required=True)
    resolve.add_argument('--note')
    resolve.set_defaults(func=lambda args: cmd_update(args, 'promoted'))

    dismiss = sub.add_parser('dismiss')
    dismiss.add_argument('--id', required=True)
    dismiss.add_argument('--note')
    dismiss.set_defaults(func=lambda args: cmd_update(args, 'dismissed'))

    ls = sub.add_parser('list')
    ls.add_argument('--status', choices=sorted(ALLOWED_STATUS))
    ls.set_defaults(func=cmd_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
