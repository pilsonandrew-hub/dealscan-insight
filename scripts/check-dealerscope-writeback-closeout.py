#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Iterable

CANON = Path('/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain')
MIRROR = Path('/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def normalize_relpath(raw: str) -> Path:
    rel = Path(raw)
    if rel.is_absolute():
        raise ValueError(f'expected path relative to canonical brain, got absolute path: {raw}')
    parts = rel.parts
    if not parts:
        raise ValueError('empty relative path is not allowed')
    if parts[0] == 'brains' and len(parts) >= 2 and parts[1] == 'dealerscope-brain':
        rel = Path(*parts[2:])
    if '..' in rel.parts:
        raise ValueError(f'parent traversal is not allowed: {raw}')
    return rel


def check_one(rel: Path) -> tuple[bool, str]:
    canon_path = CANON / rel
    mirror_path = MIRROR / rel

    if not canon_path.exists():
        return False, f'MISSING_CANON {rel}'
    if canon_path.is_dir():
        return False, f'CANON_IS_DIR {rel}'
    if not mirror_path.exists():
        return False, f'MISSING_MIRROR {rel}'
    if mirror_path.is_dir():
        return False, f'MIRROR_IS_DIR {rel}'

    canon_hash = sha256_file(canon_path)
    mirror_hash = sha256_file(mirror_path)

    if canon_hash != mirror_hash:
        return False, f'HASH_MISMATCH {rel}'

    return True, f'OK {rel}'


def iter_candidate_paths(paths: Iterable[str]) -> list[Path]:
    normalized = []
    for raw in paths:
        normalized.append(normalize_relpath(raw))
    seen = []
    seen_set = set()
    for rel in normalized:
        if rel not in seen_set:
            seen.append(rel)
            seen_set.add(rel)
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Verify DealerScope governed writeback closeout by checking canonical brain files against the Obsidian mirror.'
    )
    parser.add_argument(
        'paths',
        nargs='+',
        help='One or more file paths relative to brains/dealerscope-brain (or prefixed with brains/dealerscope-brain/...)',
    )
    args = parser.parse_args()

    if not CANON.exists():
        print(f'ERROR canonical brain missing: {CANON}', file=sys.stderr)
        return 2
    if not MIRROR.exists():
        print(f'ERROR mirror missing: {MIRROR}', file=sys.stderr)
        return 2

    try:
        relpaths = iter_candidate_paths(args.paths)
    except ValueError as exc:
        print(f'ERROR {exc}', file=sys.stderr)
        return 2

    print('DealerScope writeback closeout verification')
    print(f'Canonical: {CANON}')
    print(f'Mirror:    {MIRROR}')

    failures = 0
    for rel in relpaths:
        ok, msg = check_one(rel)
        print(msg)
        if not ok:
            failures += 1

    if failures:
        print(f'FAIL {failures} path(s) not fully closed out')
        return 1

    print(f'PASS {len(relpaths)} path(s) verified with exact hash parity')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
