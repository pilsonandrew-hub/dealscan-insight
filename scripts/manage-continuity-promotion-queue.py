#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORKSPACE = Path('/Users/andrewpilson/.openclaw/workspace')
QUEUE_PATH = WORKSPACE / 'continuity' / 'pending-promotions.json'
POLICY_PATH = WORKSPACE / 'continuity' / 'policy.json'
ALLOWED_STATUS = {
    'pending',
    'executing',
    'promoted',
    'dismissed',
    'failed_precondition',
    'failed_partial_mutation',
    'reverted',
    'recovery_required',
}
ALLOWED_DESTINATIONS = {'work_queue', 'closure_board', 'report', 'doctrine', 'policy'}
EXECUTION_CAPABLE_DESTINATIONS = {'work_queue'}
WORK_QUEUE_TARGET_STATUSES = ['ready_for_review', 'closed']


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_queue() -> dict:
    if not QUEUE_PATH.exists():
        return {'version': 1, 'updated_at': None, 'items': []}
    try:
        return json.loads(QUEUE_PATH.read_text())
    except Exception:
        return {'version': 1, 'updated_at': None, 'items': []}


def load_policy() -> dict:
    if not POLICY_PATH.exists():
        return {}
    try:
        return json.loads(POLICY_PATH.read_text())
    except Exception:
        return {}


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
        'destination': None,
        'destination_ref': None,
        'resolution': None,
        'resolved_at': None,
    })
    write_queue(payload)
    print(f'added {args.id}')
    return 0


def load_destination_cfg(destination: str) -> dict:
    policy = load_policy().get('promotion', {})
    cfg = (policy.get('destinations') or {}).get(destination)
    if not cfg:
        raise SystemExit(f'missing destination config for {destination}')
    return cfg


def verify_destination(destination: str, destination_ref: str) -> None:
    cfg = load_destination_cfg(destination)
    if destination in {'work_queue', 'closure_board'}:
        target_path = WORKSPACE / cfg['path']
        if not target_path.exists():
            raise SystemExit(f'missing target file for {destination}: {target_path}')
        content = target_path.read_text()
        expected = f"{cfg.get('match_prefix', '### ')}{destination_ref}"
        if expected not in content:
            raise SystemExit(f'unverified destination ref {destination_ref} in {destination}')
        return
    prefix = cfg.get('path_prefix')
    if not prefix:
        raise SystemExit(f'missing path_prefix for {destination}')
    target_path = WORKSPACE / prefix / destination_ref
    if cfg.get('require_file', False) and not target_path.exists():
        raise SystemExit(f'missing destination file for {destination}: {destination_ref}')


def parse_backticked_value(line: str) -> Optional[str]:
    if '`' not in line:
        return None
    parts = line.split('`')
    return parts[1] if len(parts) >= 3 else None


def mutate_work_queue_item(item: dict, destination_ref: str, note: Optional[str], target_status: str) -> dict:
    if note and '[simulate-partial-failure]' in note:
        raise SystemExit('simulated partial mutation failure requested for enterprise recovery test')
    cfg = load_destination_cfg('work_queue')
    execution_cfg = cfg.get('execution') or {}
    if not execution_cfg.get('enabled', False):
        raise SystemExit('work_queue execution is not enabled by policy')
    if target_status not in set(execution_cfg.get('allowed_new_statuses') or []):
        raise SystemExit(f'target status not allowed by policy: {target_status}')
    if execution_cfg.get('require_resolution_note', False) and not note:
        raise SystemExit('work_queue execution requires --note')

    target_path = WORKSPACE / cfg['path']
    if not target_path.exists():
        raise SystemExit(f'missing target file for work_queue: {target_path}')
    lines = target_path.read_text().splitlines()
    heading_prefix = f"{cfg.get('match_prefix', '### ')}{destination_ref}"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().startswith(heading_prefix))
    except StopIteration:
        raise SystemExit(f'unverified destination ref {destination_ref} in work_queue')
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].startswith('### '):
            end = i
            break
    block = lines[start:end]
    status_idx = next((i for i, line in enumerate(block) if line.startswith('- Status:')), None)
    next_idx = next((i for i, line in enumerate(block) if line.startswith('- Next action:')), None)
    evidence_idx = next((i for i, line in enumerate(block) if line.startswith('- Evidence/source basis:')), None)
    if status_idx is None or next_idx is None or evidence_idx is None:
        raise SystemExit(f'work_queue item missing required fields for mutation: {destination_ref}')

    current_status = parse_backticked_value(block[status_idx])
    if current_status not in set(execution_cfg.get('allowed_target_statuses') or []):
        raise SystemExit(f'current work_queue status not eligible for execution mutation: {current_status}')

    block[status_idx] = f"- Status: `{target_status}`"
    if execution_cfg.get('set_next_action_from_resolution', False):
        block[next_idx] = f"- Next action: {note}"
    if execution_cfg.get('append_promotion_evidence', False):
        evidence_text = block[evidence_idx]
        addition = f"promotion `{item['id']}`"
        if addition not in evidence_text:
            block[evidence_idx] = evidence_text.rstrip() + f", {addition}"
    promotion_note_line = f"- Promotion resolution note: {note}"
    existing_note_idx = next((i for i, line in enumerate(block) if line.startswith('- Promotion resolution note:')), None)
    if existing_note_idx is not None:
        block[existing_note_idx] = promotion_note_line
    else:
        inserted = False
        for i, line in enumerate(block):
            if line.startswith('- Originating sweep/carry-forward context:'):
                block.insert(i + 1, promotion_note_line)
                inserted = True
                break
        if not inserted:
            block.append(promotion_note_line)
    pre_status = current_status
    pre_next_action = block[next_idx]
    pre_evidence = block[evidence_idx]
    lines[start:end] = block
    target_path.write_text('\n'.join(lines) + '\n')
    return {
        'execution_mode': 'destination_mutation',
        'target_path': str(target_path.relative_to(WORKSPACE)),
        'target_status': target_status,
        'fulfillment_proof': f'updated {destination_ref} in work_queue to {target_status}',
        'pre_mutation_evidence': {
            'status': pre_status,
            'next_action': pre_next_action,
            'evidence': pre_evidence,
        },
        'post_mutation_evidence': {
            'status': target_status,
            'next_action': block[next_idx],
            'evidence': block[evidence_idx],
        },
    }


def fail_item(payload: dict, item: dict, status: str, reason: str, destination: Optional[str] = None, destination_ref: Optional[str] = None) -> int:
    item['status'] = status
    item['resolution'] = reason
    item['resolved_at'] = now_iso()
    item['failure_stage'] = 'precondition' if status == 'failed_precondition' else 'mutation'
    item['failure_reason'] = reason
    item['recovery_status'] = 'not_required' if status == 'failed_precondition' else 'pending'
    item['final_resolution_classification'] = 'failed_precondition' if status == 'failed_precondition' else 'failed_partial_mutation'
    if destination:
        item['destination'] = destination
    if destination_ref:
        item['destination_ref'] = destination_ref
    write_queue(payload)
    print(f'{status} {item["id"]}')
    return 0


def cmd_update(args, status: str) -> int:
    payload = load_queue()
    policy = load_policy()
    audit_cfg = ((policy.get('promotion') or {}).get('audit') or {})
    items = payload.setdefault('items', [])
    item = find_item(items, args.id)
    if not item:
        raise SystemExit(f'missing item: {args.id}')
    execution_result = None
    if status == 'promoted':
        if not args.destination or args.destination not in ALLOWED_DESTINATIONS:
            raise SystemExit(f'valid --destination required for promoted item: {sorted(ALLOWED_DESTINATIONS)}')
        if not args.destination_ref:
            raise SystemExit('--destination-ref required for promoted item')
        try:
            verify_destination(args.destination, args.destination_ref)
        except SystemExit as exc:
            return fail_item(payload, item, 'failed_precondition', str(exc), args.destination, args.destination_ref)
        if args.execute:
            if args.destination not in EXECUTION_CAPABLE_DESTINATIONS:
                return fail_item(payload, item, 'failed_precondition', f'{args.destination} execution is intentionally disabled by the single-supported-destination model', args.destination, args.destination_ref)
            item['status'] = 'executing'
            item['destination'] = args.destination
            item['destination_ref'] = args.destination_ref
            item['execution_mode'] = 'destination_mutation'
            write_queue(payload)
            try:
                if args.destination == 'work_queue':
                    execution_result = mutate_work_queue_item(item, args.destination_ref, args.note, args.target_status)
                else:
                    raise SystemExit(f'--execute is not yet supported for destination: {args.destination}')
            except SystemExit as exc:
                item['partial_mutation_evidence'] = {
                    'destination': args.destination,
                    'destination_ref': args.destination_ref,
                    'attempted_target_status': args.target_status,
                }
                item['degraded_subsystem'] = args.destination
                item['recovery_action'] = 'manual_or_scripted_revert_required'
                item['recovery_status'] = 'pending'
                return fail_item(payload, item, 'failed_partial_mutation', str(exc), args.destination, args.destination_ref)
        item['destination'] = args.destination
        item['destination_ref'] = args.destination_ref
    item['status'] = status
    item['resolution'] = args.note or None
    item['resolved_at'] = now_iso()
    if status == 'reverted':
        item['recovery_status'] = 'resolved'
        item['final_resolution_classification'] = 'reverted_after_partial_failure'
        item['recovery_evidence'] = args.note or 'reverted cleanly'
    elif status == 'recovery_required':
        item['recovery_status'] = 'pending_manual_recovery'
        item['final_resolution_classification'] = 'recovery_required'
    else:
        item.pop('failure_stage', None)
        item.pop('failure_reason', None)
        item.pop('partial_mutation_evidence', None)
        item.pop('degraded_subsystem', None)
        item.pop('recovery_action', None)
        item.pop('recovery_status', None)
        item.pop('recovery_evidence', None)
        item.pop('final_resolution_classification', None)
    if execution_result:
        item.update(execution_result)
        item['recovery_status'] = 'not_required'
        item['final_resolution_classification'] = 'promoted_executed'
    elif status == 'promoted':
        item['execution_mode'] = 'verification_only'
        item.setdefault('fulfillment_proof', f'verified destination exists for {item["destination"]}:{item["destination_ref"]}')
        item.setdefault('target_status', None)
        item['final_resolution_classification'] = 'promoted_verified_only'
    required_promoted_fields = audit_cfg.get('required_promoted_fields') or []
    required_executed_fields = audit_cfg.get('required_executed_fields') or []
    if status == 'promoted' and audit_cfg.get('require_uniform_resolution_metadata', False):
        for field in required_promoted_fields:
            if not item.get(field):
                raise SystemExit(f'missing required promoted audit field: {field}')
        if item.get('execution_mode') == 'destination_mutation':
            for field in required_executed_fields:
                if not item.get(field):
                    raise SystemExit(f'missing required executed audit field: {field}')
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
    resolve.add_argument('--destination', choices=sorted(ALLOWED_DESTINATIONS), required=True)
    resolve.add_argument('--destination-ref', required=True)
    resolve.add_argument('--note')
    resolve.add_argument('--execute', action='store_true')
    resolve.add_argument('--target-status', choices=WORK_QUEUE_TARGET_STATUSES, default='ready_for_review')
    resolve.set_defaults(func=lambda args: cmd_update(args, 'promoted'))

    dismiss = sub.add_parser('dismiss')
    dismiss.add_argument('--id', required=True)
    dismiss.add_argument('--note')
    dismiss.set_defaults(func=lambda args: cmd_update(args, 'dismissed'))

    recover = sub.add_parser('recover')
    recover.add_argument('--id', required=True)
    recover.add_argument('--note', required=True)
    recover.add_argument('--status', choices=['reverted', 'recovery_required'], required=True)
    recover.set_defaults(func=lambda args: cmd_update(args, args.status))

    ls = sub.add_parser('list')
    ls.add_argument('--status', choices=sorted(ALLOWED_STATUS))
    ls.set_defaults(func=cmd_list)

    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
