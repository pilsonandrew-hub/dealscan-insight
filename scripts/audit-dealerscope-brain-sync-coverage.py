#!/usr/bin/env python3
from pathlib import Path

CANON = Path('/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain')
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
IGNORE = {'.git'}

actual = sorted(
    p.relative_to(CANON).as_posix()
    for p in CANON.iterdir()
    if p.is_dir() and p.name not in IGNORE
)
include = sorted(INCLUDE_DIRS)
actual_set = set(actual)
include_set = set(include)

missing_from_include = [p for p in actual if p not in include_set]
stale_includes = [p for p in include if not (CANON / p).exists()]

print('DealerScope brain sync coverage audit')
print(f'Canonical root: {CANON}')
print('')
print('Included directories:')
for p in include:
    print(f'  - {p}')
print('')
print('Canonical top-level directories:')
for p in actual:
    print(f'  - {p}')
print('')
if missing_from_include:
    print('MISSING_FROM_INCLUDE:')
    for p in missing_from_include:
        print(f'  - {p}')
else:
    print('MISSING_FROM_INCLUDE: none')
print('')
if stale_includes:
    print('STALE_INCLUDE_ENTRIES:')
    for p in stale_includes:
        print(f'  - {p}')
else:
    print('STALE_INCLUDE_ENTRIES: none')

if missing_from_include or stale_includes:
    raise SystemExit(1)
