#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

CANON = Path('/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain')
TARGETS = [
    Path('/Users/andrewpilson/Documents/Obsidian Vault/DealerScope Brain'),
]
INCLUDE_DIRS = [
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
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def copy_tree(src_root: Path, dst_root: Path, rel: str) -> tuple[int, int]:
    src = src_root / rel
    if not src.exists():
        return 0, 0
    copied = 0
    skipped = 0
    for path in src.rglob('*'):
        if path.is_dir():
            continue
        relpath = path.relative_to(src_root)
        dst = dst_root / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists() and dst.is_file():
            if sha256_file(path) == sha256_file(dst):
                skipped += 1
                continue
        shutil.copy2(path, dst)
        copied += 1
    return copied, skipped


def main() -> int:
    if not CANON.exists():
        print(f'ERROR canonical brain missing: {CANON}', file=sys.stderr)
        return 2

    total_copied = 0
    total_skipped = 0
    for target in TARGETS:
        if not target.exists():
            print(f'ERROR target mirror missing: {target}', file=sys.stderr)
            return 2
        copied = 0
        skipped = 0
        for rel in INCLUDE_DIRS:
            c, s = copy_tree(CANON, target, rel)
            copied += c
            skipped += s
        total_copied += copied
        total_skipped += skipped
        print(f'{target}: copied {copied} files, skipped {skipped} already-matching files')

    print(f'TOTAL copied={total_copied} skipped={total_skipped}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
