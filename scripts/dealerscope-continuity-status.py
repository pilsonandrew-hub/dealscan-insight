#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable

WORKSPACE = Path('/Users/andrewpilson/.openclaw/workspace')
CANON = WORKSPACE / 'brains/dealerscope-brain'
MIRROR = Path('/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain')
CONTINUITY_DIR = WORKSPACE / 'continuity'
STATE_PATH = CONTINUITY_DIR / 'continuity-state.json'
EVENTS_PATH = CONTINUITY_DIR / 'continuity-events.jsonl'
METRICS_PATH = CONTINUITY_DIR / 'continuity-metrics.json'
CLOSEOUT_PATH = CONTINUITY_DIR / 'closeout-evaluation.json'
OPEN_LOOPS_PATH = CONTINUITY_DIR / 'open-loops.json'
POLICY_PATH = CONTINUITY_DIR / 'policy.json'
PENDING_PROMOTIONS_PATH = CONTINUITY_DIR / 'pending-promotions.json'
DAILY_MEMORY_DIR = WORKSPACE / 'memory'
INCLUDE_DIRS = {
    '00_Start-Here',
    '01_Standards',
    '02_Architecture',
    '03_Operations',
    '05_Incidents',
    '06_Integrations',
    '90_Templates',
    'people',
    'companies',
    'concepts',
    'deals',
    'meetings',
    'operations',
    'projects',
    'systems',
    'sources',
    'reports',
    'originals',
}
SYNC_SCRIPT = WORKSPACE / 'scripts/dealerscope-brain-sync.py'


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + '\n')


def append_event(event_type: str, severity: str, workstream: str, details: dict) -> None:
    CONTINUITY_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        'timestamp': now_iso(),
        'event_type': event_type,
        'source': 'scripts/dealerscope-continuity-status.py',
        'severity': severity,
        'workstream': workstream,
        'details': details,
        'correlation_id': details.get('correlation_id', 'continuity-status'),
    }
    with EVENTS_PATH.open('a') as f:
        f.write(json.dumps(record) + '\n')


def update_metrics(state: str, advisory_count: int, blocking_count: int, recall_required: bool) -> None:
    today = datetime.now().date().isoformat()
    metrics = load_json(METRICS_PATH, {'version': 1, 'days': {}})
    days = metrics.setdefault('days', {})
    day = days.setdefault(today, {
        'events_written_today': 0,
        'closeout_checks_today': 0,
        'advisory_violations_today': 0,
        'blocking_violations_today_if_enforced': 0,
        'sync_failures_today': 0,
        'briefing_failures_today': 0,
        'recall_required_today': 0,
        'overrides_today': 0,
        'last_state': None,
    })
    day['events_written_today'] += 1
    day['closeout_checks_today'] += 1
    day['advisory_violations_today'] += advisory_count
    day['blocking_violations_today_if_enforced'] += blocking_count
    if recall_required:
        day['recall_required_today'] += 1
    day['last_state'] = state
    write_json(METRICS_PATH, metrics)


def load_open_loops() -> list[dict]:
    payload = load_json(OPEN_LOOPS_PATH, {'items': []})
    items = payload.get('items') or []
    return [item for item in items if isinstance(item, dict)]


def load_pending_promotions(queue_path: Path) -> list[dict]:
    payload = load_json(queue_path, {'items': []})
    items = payload.get('items') or []
    return [item for item in items if isinstance(item, dict)]


def malformed_open_loops(items: list[dict]) -> list[dict]:
    bad = []
    required = ['id', 'title', 'status', 'severity', 'next_start', 'closure_condition', 'owner']
    allowed_status = {'open', 'blocked', 'waiting', 'closed'}
    allowed_severity = {'low', 'medium', 'high', 'critical'}
    for item in items:
        if any(not item.get(key) for key in required):
            bad.append(item)
            continue
        if item.get('status') not in allowed_status:
            bad.append(item)
            continue
        if item.get('severity') not in allowed_severity:
            bad.append(item)
            continue
    return bad


def find_latest_matching(glob_pattern: str, root: Path | None = None, exclude_names: set[str] | None = None) -> str | None:
    ignored_roots = {'node_modules', '.git', '.tmp', 'workspace-gateway-5d55f022-d60c-44d1-a777-bd291c352331'}
    exclude_names = exclude_names or set()
    search_root = root or WORKSPACE
    matches = []
    for path in search_root.rglob(glob_pattern):
        if not path.is_file():
            continue
        if path.name in exclude_names:
            continue
        rel = path.relative_to(WORKSPACE)
        if rel.parts and rel.parts[0] in ignored_roots:
            continue
        matches.append(path)
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for path in matches:
        return str(path.relative_to(WORKSPACE))
    return None


def malformed_pending_promotions(items: list[dict], audit_cfg: dict | None = None) -> list[dict]:
    bad = []
    audit_cfg = audit_cfg or {}
    required = ['id', 'title', 'source', 'reason', 'created_at', 'status']
    allowed_status = {'pending', 'promoted', 'dismissed'}
    allowed_destinations = {'work_queue', 'closure_board', 'report', 'doctrine', 'policy'}
    required_promoted_fields = audit_cfg.get('required_promoted_fields') or []
    required_executed_fields = audit_cfg.get('required_executed_fields') or []
    for item in items:
        if any(not item.get(key) for key in required):
            bad.append(item)
            continue
        if item.get('status') not in allowed_status:
            bad.append(item)
            continue
        if item.get('status') == 'promoted':
            if item.get('destination') not in allowed_destinations:
                bad.append(item)
                continue
            if not item.get('destination_ref'):
                bad.append(item)
                continue
            for field in required_promoted_fields:
                if not item.get(field):
                    bad.append(item)
                    break
            else:
                if item.get('execution_mode') == 'destination_mutation':
                    if any(not item.get(field) for field in required_executed_fields):
                        bad.append(item)
                        continue
    return bad


def verified_destination_failures(items: list[dict], promotion_cfg: dict) -> list[str]:
    if not promotion_cfg.get('verify_destinations', False):
        return []
    destinations = promotion_cfg.get('destinations') or {}
    failures: list[str] = []
    for item in items:
        if item.get('status') != 'promoted':
            continue
        destination = item.get('destination')
        destination_ref = item.get('destination_ref')
        if not destination or not destination_ref:
            continue
        cfg = destinations.get(destination) or {}
        if destination in {'work_queue', 'closure_board'}:
            raw_path = cfg.get('path')
            if not raw_path:
                failures.append(f"{item.get('id')}:missing_destination_config")
                continue
            target_path = WORKSPACE / raw_path
            if not target_path.exists():
                failures.append(f"{item.get('id')}:{destination}:missing_target_file")
                continue
            content = target_path.read_text()
            expected = f"{cfg.get('match_prefix', '### ')}{destination_ref}"
            if expected not in content:
                failures.append(f"{item.get('id')}:{destination}:{destination_ref}:missing_reference")
        else:
            prefix = cfg.get('path_prefix')
            if not prefix:
                failures.append(f"{item.get('id')}:missing_destination_config")
                continue
            target_path = WORKSPACE / prefix / destination_ref
            if cfg.get('require_file', False) and not target_path.exists():
                failures.append(f"{item.get('id')}:{destination}:{destination_ref}:missing_file")
    return failures


def active_pending_promotions(items: list[dict]) -> list[dict]:
    return [item for item in items if item.get('status') == 'pending']


def derive_pending_promotions(policy: dict, closeout_blocking: list[str], malformed_loops: list[dict], open_loops: list[dict], queue_items: list[dict]) -> list[dict]:
    derived = []
    if policy.get('closeout_blocking_creates_candidate', True):
        for reason in closeout_blocking:
            derived.append({
                'id': f'closeout-{reason}',
                'title': f'Closeout pressure: {reason}',
                'source': 'continuity-status',
                'reason': f'blocking_reason:{reason}',
                'created_at': now_iso(),
                'status': 'pending',
            })
    if policy.get('malformed_open_loops_create_candidate', True) and malformed_loops:
        derived.append({
            'id': 'malformed-open-loops',
            'title': 'Malformed open loops require process or schema promotion',
            'source': 'continuity-status',
            'reason': f'malformed_open_loops:{len(malformed_loops)}',
            'created_at': now_iso(),
            'status': 'pending',
        })
    if policy.get('open_loop_promote_flag', True):
        for item in open_loops:
            if item.get('promote') is True:
                derived.append({
                    'id': f"open-loop-{item.get('id', 'missing-id')}",
                    'title': item.get('title', 'untitled'),
                    'source': 'open-loops',
                    'reason': 'promote_flag',
                    'created_at': now_iso(),
                    'status': 'pending',
                })

    merged = []
    seen = set()
    for item in [*queue_items, *derived]:
        key = item.get('id')
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def get_briefing_health(briefing_cfg: dict, git: dict) -> dict:
    root_raw = briefing_cfg.get('daily_briefing_root')
    root = (WORKSPACE / root_raw) if root_raw else WORKSPACE
    today_name = f"DealerScope-Morning-Briefing-{datetime.now().date().isoformat()}.md"
    today_rel = None
    if root_raw:
        today_rel = str(Path(root_raw) / today_name)
    today_path = root / today_name
    mirror_rel = Path(today_name)
    mirror_path = MIRROR / '03_Operations' / mirror_rel
    freshness_max_hours = int(briefing_cfg.get('freshness_max_hours', 18))
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=freshness_max_hours)
    exists_today = today_path.exists() and today_path.is_file()
    projected = exists_today and mirror_path.exists() and mirror_path.is_file()
    mirrored_hash_match = projected and sha256_file(today_path) == sha256_file(mirror_path)
    fresh = False
    age_hours = None
    if exists_today:
        modified = datetime.fromtimestamp(today_path.stat().st_mtime, tz=timezone.utc)
        age_hours = round((datetime.now(timezone.utc) - modified).total_seconds() / 3600, 2)
        fresh = modified >= freshness_cutoff
    return {
        'today_relpath': today_rel,
        'exists_today': exists_today,
        'fresh': fresh,
        'age_hours': age_hours,
        'projected_to_mirror': projected,
        'mirror_hash_match': mirrored_hash_match,
        'projection_artifact': bool(briefing_cfg.get('projection_artifact', False)),
        'tracked_canonical_expected': bool(briefing_cfg.get('tracked_canonical', False)),
        'canonical_repo_dirty': git['dirty'],
    }


def run_git(args: list[str]) -> str:
    proc = subprocess.run(
        ['git', *args],
        cwd=CANON,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f'git {args} failed')
    return proc.stdout.strip()


def git_status() -> dict:
    dirty = bool(run_git(['status', '--porcelain']))
    head = run_git(['rev-parse', 'HEAD'])
    branch = run_git(['rev-parse', '--abbrev-ref', 'HEAD'])
    try:
        upstream = run_git(['rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{u}'])
        ahead_behind = run_git(['rev-list', '--left-right', '--count', 'HEAD...@{u}'])
        ahead, behind = [int(x) for x in ahead_behind.split()]
    except Exception:
        upstream = ''
        ahead = 0
        behind = 0
    return {
        'dirty': dirty,
        'head': head,
        'branch': branch,
        'upstream': upstream,
        'ahead': ahead,
        'behind': behind,
    }


def normalize_relpath(raw: str) -> Path:
    rel = Path(raw)
    if rel.is_absolute():
        raise ValueError(f'expected relative path, got absolute: {raw}')
    parts = rel.parts
    if parts and parts[0] == 'brains' and len(parts) >= 2 and parts[1] == 'dealerscope-brain':
        rel = Path(*parts[2:])
    if '..' in rel.parts:
        raise ValueError(f'parent traversal not allowed: {raw}')
    return rel


def check_named_paths(paths: Iterable[str]) -> tuple[list[str], list[str]]:
    missing_or_bad = []
    ok = []
    for raw in paths:
        rel = normalize_relpath(raw)
        canon_path = CANON / rel
        mirror_path = MIRROR / rel
        if not canon_path.exists() or not canon_path.is_file():
            missing_or_bad.append(f'MISSING_CANON {rel}')
            continue
        if not mirror_path.exists() or not mirror_path.is_file():
            missing_or_bad.append(f'MISSING_MIRROR {rel}')
            continue
        if sha256_file(canon_path) != sha256_file(mirror_path):
            missing_or_bad.append(f'HASH_MISMATCH {rel}')
            continue
        ok.append(str(rel))
    return ok, missing_or_bad


def check_full_scope() -> tuple[int, list[str], list[str]]:
    checked = 0
    missing = []
    mismatched = []
    for path in sorted(CANON.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(CANON)
        if rel.parts[0] not in INCLUDE_DIRS:
            continue
        checked += 1
        mirror_path = MIRROR / rel
        if not mirror_path.exists() or not mirror_path.is_file():
            missing.append(str(rel))
            continue
        if sha256_file(path) != sha256_file(mirror_path):
            mismatched.append(str(rel))
    return checked, missing, mismatched


def run_sync() -> None:
    proc = subprocess.run(['python3', str(SYNC_SCRIPT)], text=True, capture_output=True, check=False)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise RuntimeError('mirror sync failed')


def artifact_family_status(policy: dict) -> dict:
    families = policy.get('artifact_families') or {}
    summary = {}
    for name, cfg in families.items():
        summary[name] = {
            'classification': cfg.get('classification'),
            'roots': cfg.get('roots') or [],
        }
    return summary


def destination_model_status(policy: dict) -> dict:
    promotion = policy.get('promotion') or {}
    return {
        'execution_model': promotion.get('execution_model'),
        'architecture_decision': promotion.get('architecture_decision'),
        'system_grade_classification': promotion.get('system_grade_classification') or {},
        'execution_scope_decision': promotion.get('execution_scope_decision'),
        'scope_interpretation': promotion.get('scope_interpretation'),
        'execution_complete_destinations': promotion.get('execution_complete_destinations') or [],
        'verification_only_destinations': promotion.get('verification_only_destinations') or [],
    }


def composite_state(git: dict, named_failures: list[str], full_missing: list[str], full_mismatched: list[str], malformed_loops: list[dict], recall_required: bool) -> str:
    mirror_bad = bool(named_failures or full_missing or full_mismatched)
    if malformed_loops or recall_required:
        return 'advisory_drift'
    if git['dirty'] and (git['ahead'] > 0 or mirror_bad):
        return 'needs_sync_and_push'
    if git['dirty']:
        return 'governed_dirty'
    if mirror_bad and git['ahead'] > 0:
        return 'needs_sync_and_push'
    if mirror_bad:
        return 'mirror_drift'
    if git['ahead'] > 0:
        return 'needs_push'
    return 'aligned'


def main() -> int:
    parser = argparse.ArgumentParser(description='DealerScope continuity status and autonomous sync control check')
    parser.add_argument('--sync', action='store_true', help='Run brain -> mirror sync before verification')
    parser.add_argument('--paths', nargs='*', default=[], help='Named governed artifact paths to verify')
    parser.add_argument('--full', action='store_true', help='Verify full governed mirror scope')
    parser.add_argument('--post-gap', action='store_true', help='Mark this run as a post-gap continuity check requiring recall')
    parser.add_argument('--post-compaction', action='store_true', help='Mark this run as a post-compaction continuity check requiring recall')
    args = parser.parse_args()

    if not CANON.exists():
        print(f'ERROR canonical brain missing: {CANON}', file=sys.stderr)
        return 2
    if not MIRROR.exists():
        print(f'ERROR mirror missing: {MIRROR}', file=sys.stderr)
        return 2

    if args.sync:
        run_sync()

    policy = load_json(POLICY_PATH, {'enforcement_mode': 'audit', 'mirror': {'named_paths': []}, 'recall': {}, 'briefing': {}, 'promotion': {}})
    configured_paths = (policy.get('mirror') or {}).get('named_paths') or []
    requested_paths = args.paths or configured_paths
    briefing_cfg = policy.get('briefing') or {}
    promotion_cfg = policy.get('promotion') or {}
    audit_cfg = promotion_cfg.get('audit') or {}
    artifact_families = artifact_family_status(policy)
    destination_model = destination_model_status(policy)

    git = git_status()
    named_ok, named_failures = check_named_paths(requested_paths) if requested_paths else ([], [])
    checked = 0
    full_missing: list[str] = []
    full_mismatched: list[str] = []
    if args.full:
        checked, full_missing, full_mismatched = check_full_scope()

    open_loops = load_open_loops()
    bad_loops = malformed_open_loops(open_loops)
    serious_open_loops = [item for item in open_loops if item.get('status') != 'closed']
    queue_rel = promotion_cfg.get('queue_path', 'continuity/pending-promotions.json')
    queue_path = WORKSPACE / queue_rel
    queue_items = load_pending_promotions(queue_path)
    bad_queue_items = malformed_pending_promotions(queue_items, audit_cfg)
    destination_failures = verified_destination_failures(queue_items, promotion_cfg)
    recall_policy = policy.get('recall') or {}
    recall_required = bool(
        (args.post_gap and recall_policy.get('post_gap_requires_recall', True))
        or (args.post_compaction and recall_policy.get('post_compaction_requires_recall', True))
    )
    daily_memory_today = DAILY_MEMORY_DIR / f"{datetime.now().date().isoformat()}.md"
    briefing_root_raw = briefing_cfg.get('daily_briefing_root')
    briefing_root = (WORKSPACE / briefing_root_raw) if briefing_root_raw else WORKSPACE
    exclude_names = {'DealerScope-Morning-Briefing-Protocol.md', 'DealerScope-Morning-Briefing-Template.md'} if briefing_cfg.get('ignore_protocol_and_template', True) else set()
    latest_daily_briefing = find_latest_matching(briefing_cfg.get('daily_briefing_glob', 'Daily Briefing*.md'), briefing_root, exclude_names=exclude_names)
    latest_cto_note = find_latest_matching(briefing_cfg.get('cto_note_glob', '*CTO*.md'))
    briefing_health = get_briefing_health(briefing_cfg, git)

    blocking_reasons = []
    advisory_reasons = []
    pending_replication = []
    if git['dirty']:
        blocking_reasons.append('governed_dirty')
    if git['ahead'] > 0:
        pending_replication.append('needs_push')
        blocking_reasons.append('needs_push')
    if named_failures or full_missing or full_mismatched:
        pending_replication.append('mirror_drift')
        blocking_reasons.append('mirror_drift')

    state = composite_state(git, named_failures, full_missing, full_mismatched, bad_loops, recall_required)
    pending_promotions = derive_pending_promotions(promotion_cfg, blocking_reasons, bad_loops, open_loops, active_pending_promotions(queue_items))

    if bad_loops:
        advisory_reasons.append('malformed_open_loops')
    if promotion_cfg.get('require_queue_file', True) and not queue_path.exists():
        advisory_reasons.append('missing_promotion_queue')
    if bad_queue_items:
        advisory_reasons.append('malformed_pending_promotions')
    if destination_failures:
        advisory_reasons.append('promotion_destination_unverified')
    if recall_required:
        advisory_reasons.append('needs_recall')
    if not daily_memory_today.exists():
        advisory_reasons.append('missing_daily_memory_today')
    if latest_daily_briefing is None:
        advisory_reasons.append('missing_daily_briefing')
    if briefing_cfg.get('require_today_file', True) and not briefing_health['exists_today']:
        advisory_reasons.append('briefing_not_generated_today')
    if briefing_health['exists_today'] and not briefing_health['fresh']:
        advisory_reasons.append('briefing_stale')
    if briefing_cfg.get('require_mirror_projection', True) and briefing_health['exists_today'] and not briefing_health['projected_to_mirror']:
        blocking_reasons.append('briefing_not_projected')
    if briefing_cfg.get('require_mirror_projection', True) and briefing_health['exists_today'] and briefing_health['projected_to_mirror'] and not briefing_health['mirror_hash_match']:
        blocking_reasons.append('briefing_projection_mismatch')
    if latest_cto_note is None:
        advisory_reasons.append('missing_cto_note')

    overall_state = 'aligned'
    if blocking_reasons and policy.get('enforcement_mode', 'audit') == 'enforce':
        overall_state = 'blocked'
    elif blocking_reasons or advisory_reasons:
        overall_state = 'advisory_drift'

    generated_at = now_iso()
    state_payload = {
        'generated_at': generated_at,
        'overall_state': overall_state,
        'derived_state': state,
        'enforcement_mode': policy.get('enforcement_mode', 'audit'),
        'governed_dirty': git['dirty'],
        'branch': git['branch'],
        'head': git['head'],
        'upstream': git['upstream'] or None,
        'ahead': git['ahead'],
        'behind': git['behind'],
        'mirror_status': {
            'named_paths_checked': len(requested_paths),
            'named_paths_ok': len(named_ok),
            'named_paths_failed': named_failures,
            'full_scope_checked': checked if args.full else None,
            'full_scope_missing': full_missing if args.full else [],
            'full_scope_mismatched': full_mismatched if args.full else [],
        },
        'push_status': 'needs_push' if git['ahead'] > 0 else 'aligned',
        'recall_status': 'required' if recall_required else 'not_required',
        'open_loops': {
            'total': len(open_loops),
            'active': len(serious_open_loops),
            'malformed': len(bad_loops),
        },
        'blocking_reasons': blocking_reasons,
        'advisory_reasons': advisory_reasons,
        'pending_promotions': pending_promotions,
        'pending_replication': pending_replication,
        'pending_verification': [],
        'override_active': False,
        'degraded_subsystems': [],
        'daily_memory_today_present': daily_memory_today.exists(),
        'last_successful_daily_briefing': latest_daily_briefing,
        'last_successful_cto_note': latest_cto_note,
        'last_successful_weekly_audit': find_latest_matching('*anti-regression*.md'),
        'briefing_health': briefing_health,
        'artifact_families': artifact_families,
        'destination_model': destination_model,
    }
    write_json(STATE_PATH, state_payload)

    closeout_payload = {
        'generated_at': generated_at,
        'enforcement_mode': policy.get('enforcement_mode', 'audit'),
        'cleanly_closable': overall_state == 'aligned',
        'conditionally_closable': overall_state == 'advisory_drift',
        'blocked_if_enforced': bool(blocking_reasons),
        'blocking_reasons': blocking_reasons,
        'advisory_reasons': advisory_reasons,
        'briefing_health': briefing_health,
        'artifact_families': artifact_families,
        'destination_model': destination_model,
        'missing_requirements': {
            'malformed_open_loops': len(bad_loops),
            'malformed_pending_promotions': len(bad_queue_items),
            'promotion_destination_failures': destination_failures,
            'pending_replication': pending_replication,
            'recall_required': recall_required,
            'audit_policy_enforced': bool(audit_cfg.get('require_uniform_resolution_metadata', False)),
        },
    }
    write_json(CLOSEOUT_PATH, closeout_payload)

    append_event('continuity_state_computed', 'info', 'dealerscope-continuity', {
        'overall_state': overall_state,
        'derived_state': state,
        'blocking_reasons': blocking_reasons,
        'advisory_reasons': advisory_reasons,
        'briefing_health': briefing_health,
    })
    update_metrics(overall_state, len(advisory_reasons), len(blocking_reasons), recall_required)

    print('DEALERSCOPE_CONTINUITY_STATUS')
    print(f'branch={git["branch"]}')
    print(f'head={git["head"]}')
    print(f'upstream={git["upstream"] or "<none>"}')
    print(f'dirty={str(git["dirty"]).lower()}')
    print(f'ahead={git["ahead"]}')
    print(f'behind={git["behind"]}')
    print(f'state={overall_state}')
    print(f'derived_state={state}')
    print(f'open_loops_total={len(open_loops)}')
    print(f'open_loops_malformed={len(bad_loops)}')
    print(f'recall_required={str(recall_required).lower()}')
    if requested_paths:
        print(f'named_paths_checked={len(requested_paths)}')
        print(f'named_paths_ok={len(named_ok)}')
        print(f'named_paths_failed={len(named_failures)}')
        for item in named_failures:
            print(item)
    if args.full:
        print(f'full_scope_checked={checked}')
        print(f'full_scope_missing={len(full_missing)}')
        print(f'full_scope_mismatched={len(full_mismatched)}')
        for rel in full_missing:
            print(f'MISSING {rel}')
        for rel in full_mismatched:
            print(f'MISMATCH {rel}')
    for reason in blocking_reasons:
        print(f'BLOCKING {reason}')
    execution_model = destination_model.get('execution_model') or '<unset>'
    architecture_decision = destination_model.get('architecture_decision') or '<unset>'
    system_grade = destination_model.get('system_grade_classification') or {}
    broad_grade = system_grade.get('broad_enterprise_system_claim', '<unset>')
    narrow_grade = system_grade.get('narrow_explicitly_scoped_architecture', '<unset>')
    execution_scope_decision = destination_model.get('execution_scope_decision') or '<unset>'
    scope_interpretation = destination_model.get('scope_interpretation') or '<unset>'
    print(f'DESTINATION_MODEL execution_model={execution_model}')
    print(f'DESTINATION_MODEL architecture_decision={architecture_decision}')
    print(f'DESTINATION_MODEL broad_enterprise_system_claim={broad_grade}')
    print(f'DESTINATION_MODEL narrow_explicitly_scoped_architecture={narrow_grade}')
    print(f'DESTINATION_MODEL execution_scope_decision={execution_scope_decision}')
    print(f'DESTINATION_MODEL scope_interpretation={scope_interpretation}')
    print('DESTINATION_MODEL execution_complete=' + ','.join(destination_model.get('execution_complete_destinations') or []))
    print('DESTINATION_MODEL verification_only=' + ','.join(destination_model.get('verification_only_destinations') or []))
    for family_name, family in artifact_families.items():
        print(f"ARTIFACT_FAMILY {family_name} classification={family.get('classification')}")
    for reason in advisory_reasons:
        print(f'ADVISORY {reason}')

    if overall_state == 'blocked':
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
