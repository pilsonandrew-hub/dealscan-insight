#!/usr/bin/env python3
from pathlib import Path
import shutil

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

def copy_tree(src_root: Path, dst_root: Path, rel: str):
    src = src_root / rel
    if not src.exists():
        return 0
    count = 0
    for path in src.rglob('*'):
        if path.is_dir():
            continue
        relpath = path.relative_to(src_root)
        dst = dst_root / relpath
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
        count += 1
    return count

for target in TARGETS:
    total = 0
    for rel in INCLUDE_DIRS:
        total += copy_tree(CANON, target, rel)
    print(f'{target}: copied {total} files')
