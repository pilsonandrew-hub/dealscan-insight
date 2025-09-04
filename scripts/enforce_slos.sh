#!/usr/bin/env bash
set -euo pipefail

SUMMARY="validation-reports/final/summary.json"
INDEX="validation-reports/final/index.html"

if [[ ! -f "$SUMMARY" || ! -f "$INDEX" ]]; then
  echo "required reports missing"
  exit 1
fi

status=$(jq -r '.status // "failure"' "$SUMMARY")
if [[ "$status" != "success" ]]; then
  echo "status=$status"
  exit 1
fi

echo "SLOs satisfied"
