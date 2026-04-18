#!/usr/bin/env bash
set -euo pipefail

HELPER="/Users/andrewpilson/.openclaw/workspace/scripts/dealerscope-writeback-closeout.sh"

usage() {
  cat <<'EOF'
Close out a meaningful DealerScope/Paperclip governed conversation.

Usage:
  closeout-governed-conversation.sh --summary <text> --artifacts <path1,path2,...>

Required:
  --summary      Short durable summary of what changed
  --artifacts    Comma-separated governed brain file paths relative to brains/dealerscope-brain

Behavior:
  - rejects empty summary
  - rejects missing artifact list
  - rejects non-existent canonical governed files
  - runs governed writeback closeout wrapper

Example:
  closeout-governed-conversation.sh \
    --summary "Routing premium Claude compact contract policy was finalized" \
    --artifacts "reports/DealerScope-Routing-Decision.md,01_Standards/DealerScope-Knowledge-Writeback-Doctrine.md"
EOF
}

SUMMARY=""
ARTIFACTS_RAW=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --summary)
      SUMMARY="${2:-}"
      shift 2
      ;;
    --artifacts)
      ARTIFACTS_RAW="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${SUMMARY// }" ]]; then
  echo "ERROR summary is required" >&2
  usage >&2
  exit 2
fi

if [[ -z "${ARTIFACTS_RAW// }" ]]; then
  echo "ERROR artifacts are required" >&2
  usage >&2
  exit 2
fi

IFS=',' read -r -a RAW_ITEMS <<< "$ARTIFACTS_RAW"
ARTIFACTS=()
for item in "${RAW_ITEMS[@]}"; do
  trimmed="$(printf '%s' "$item" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  if [[ -n "$trimmed" ]]; then
    ARTIFACTS+=("$trimmed")
  fi
done

if [[ ${#ARTIFACTS[@]} -eq 0 ]]; then
  echo "ERROR no valid artifact paths were provided" >&2
  exit 2
fi

echo "Governed conversation closeout"
echo "Summary: $SUMMARY"
echo "Artifacts:"
for artifact in "${ARTIFACTS[@]}"; do
  echo "  - $artifact"
done

"$HELPER" "${ARTIFACTS[@]}"

echo "CONVERSATION_CLOSEOUT_COMPLETE"
