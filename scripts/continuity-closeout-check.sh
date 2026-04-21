#!/bin/zsh
set -euo pipefail

cd /Users/andrewpilson/.openclaw/workspace
python3 scripts/dealerscope-continuity-status.py "$@"
cat continuity/closeout-evaluation.json
