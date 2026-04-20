#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

CANON = Path('/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain')
MIRROR = Path('/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain')
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    if not CANON.exists():
        print(f'ERROR canonical brain missing: {CANON}', file=sys.stderr)
        return 2
    if not MIRROR.exists():
        print(f'ERROR mirror missing: {MIRROR}', file=sys.stderr)
        return 2

    checked = 0
    missing: list[str] = []
    mismatched: list[str] = []

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

    print(f'CHECKED {checked}')
    print(f'MISSING {len(missing)}')
    print(f'MISMATCH {len(mismatched)}')

    if missing:
        print('MISSING_PATHS')
        for rel in missing:
            print(rel)
    if mismatched:
        print('MISMATCH_PATHS')
        for rel in mismatched:
            print(rel)

    if missing or mismatched:
        print('FAIL mirror is not in exact parity')
        return 1

    print('PASS mirror is in exact parity')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
