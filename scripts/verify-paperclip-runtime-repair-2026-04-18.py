#!/usr/bin/env python3
from pathlib import Path
import hashlib, json, sys

manifest_path = Path('/Users/andrewpilson/.openclaw/workspace/reports/paperclip-runtime-repair-manifest-2026-04-18.json')
manifest = json.loads(manifest_path.read_text())
live_root = Path(manifest['liveRoot'])
mirrors = {name: Path(path) for name, path in manifest['mirrors'].items()}
failed = False

for item in manifest['files']:
    rel = item['path']
    live_path = live_root / rel
    if not live_path.exists():
        print(f'MISSING live {rel}', file=sys.stderr)
        failed = True
        continue
    live_sha = hashlib.sha256(live_path.read_bytes()).hexdigest()
    if live_sha != item['liveSha256']:
        print(f'DRIFT live {rel} expected={item["liveSha256"]} actual={live_sha}', file=sys.stderr)
        failed = True
    else:
        print(f'OK live {rel} {live_sha}')
    for name, root in mirrors.items():
        mirror_path = root / rel
        if not mirror_path.exists():
            print(f'MISSING {name} {rel}', file=sys.stderr)
            failed = True
            continue
        sha = hashlib.sha256(mirror_path.read_bytes()).hexdigest()
        expected = item['mirrors'][name]['sha256']
        if sha != expected or sha != live_sha:
            print(f'DRIFT {name} {rel} expected={expected} actual={sha} live={live_sha}', file=sys.stderr)
            failed = True
        else:
            print(f'OK {name} {rel} {sha}')

sys.exit(1 if failed else 0)
