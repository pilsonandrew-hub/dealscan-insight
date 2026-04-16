#!/usr/bin/env bash
set -euo pipefail

TARGET="/Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/@paperclipai/server/dist/services/plugin-loader.js"

if [[ ! -f "$TARGET" ]]; then
  echo "Target not found: $TARGET" >&2
  exit 1
fi

python3 - <<'PY'
from pathlib import Path
path = Path('/Users/andrewpilson/.npm/_npx/43414d9b790239bb/node_modules/@paperclipai/server/dist/services/plugin-loader.js')
text = path.read_text()
old_import = 'import { fileURLToPath } from "node:url";'
new_import = 'import { fileURLToPath, pathToFileURL } from "node:url";'
if old_import in text and new_import not in text:
    text = text.replace(old_import, new_import, 1)
old_block = '''    async function loadManifestFromPath(manifestPath) {
        let raw;
        try {
            // Dynamic import works for both .js (ESM) and .cjs (CJS) manifests
            const mod = await import(manifestPath);
            // The manifest may be the default export or the module itself
            raw = mod["default"] ?? mod;
        }
        catch (err) {
            throw new Error(`Failed to load manifest module at ${manifestPath}: ${String(err)}`);
        }
        return manifestValidator.parseOrThrow(raw);
    }
'''
new_block = '''    async function loadManifestFromPath(manifestPath) {
        let raw;
        try {
            // Dynamic import caches aggressively in the long-lived server process.
            // Add file-mtime cache busting so local plugin manifest edits are
            // reloaded deterministically during install/upgrade.
            const manifestStat = await stat(manifestPath);
            const manifestUrl = pathToFileURL(manifestPath);
            manifestUrl.searchParams.set("t", String(manifestStat.mtimeMs));
            const mod = await import(manifestUrl.href);
            // The manifest may be the default export or the module itself
            raw = mod["default"] ?? mod;
        }
        catch (err) {
            throw new Error(`Failed to load manifest module at ${manifestPath}: ${String(err)}`);
        }
        return manifestValidator.parseOrThrow(raw);
    }
'''
if old_block in text:
    text = text.replace(old_block, new_block, 1)
elif new_block in text:
    pass
else:
    raise SystemExit('Could not find expected loadManifestFromPath block to patch')
path.write_text(text)
print('Patched', path)
PY

echo "Done. Restart Paperclip to apply the loader patch if it is already running."
