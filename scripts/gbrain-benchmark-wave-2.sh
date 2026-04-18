#!/bin/bash
set -euo pipefail

ROOT="/Users/andrewpilson/.openclaw/workspace/brains/dealerscope-brain"
GBRAIN_ROOT="/Users/andrewpilson/.openclaw/workspace/tools/gbrain"
export PATH="$HOME/.bun/bin:$PATH"

run_baseline() {
  local label="$1"
  local query="$2"
  echo "[baseline] $label"
  grep -Rin "$query" "$ROOT" | head -5 || true
  echo
}

run_gbrain() {
  local label="$1"
  local query="$2"
  echo "[gbrain] $label"
  (cd "$GBRAIN_ROOT" && gbrain search "$query") || true
  echo
}

run_baseline "proven-state" "enterprise-operated"
run_gbrain   "proven-state" "enterprise-operated"

run_baseline "paperclip-role" "Paperclip"
run_gbrain   "paperclip-role" "Paperclip role"

run_baseline "deterministic-boundary" "deterministic"
run_gbrain   "deterministic-boundary" "deterministic logic AI augmentation"

run_baseline "env-obligations" "dedicated backend target"
run_gbrain   "env-obligations" "development environment activation checklist"
