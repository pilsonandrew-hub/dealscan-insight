#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PYTHONPATH="${REPO_ROOT}:${SCRIPT_DIR}:${PYTHONPATH:-}"

CHECK_CMD=(python3 "${SCRIPT_DIR}/check_recent_ingest_runs.py")
TMP_OUTPUT="$(mktemp)"
trap 'rm -f "${TMP_OUTPUT}"' EXIT

ENV_FILE=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  case "${args[i]}" in
    --env-file)
      if (( i + 1 < ${#args[@]} )); then
        ENV_FILE="${args[i + 1]}"
      fi
      ;;
    --env-file=*)
      ENV_FILE="${args[i]#--env-file=}"
      ;;
  esac
done

if [[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]]; then
  while IFS= read -r -d '' key && IFS= read -r -d '' value; do
    if [[ -z "${!key+x}" ]]; then
      export "${key}=${value}"
    fi
  done < <(
    python3 - "${ENV_FILE}" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

target_keys = {
    "INGEST_HEALTH_NOTIFY_ENABLED",
    "INGEST_HEALTH_NOTIFY_DRY_RUN",
    "INGEST_HEALTH_CONTEXT",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
}

path = Path(sys.argv[1])
for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if key not in target_keys:
        continue
    value = value.strip().strip("'").strip('"')
    sys.stdout.write(key)
    sys.stdout.write("\0")
    sys.stdout.write(value)
    sys.stdout.write("\0")
PY
  )
fi

set +e
"${CHECK_CMD[@]}" "$@" >"${TMP_OUTPUT}" 2>&1
status=$?
set -e

if [[ "${status}" -eq 0 ]]; then
  cat "${TMP_OUTPUT}"
  exit 0
fi
cat "${TMP_OUTPUT}" >&2

if [[ "${INGEST_HEALTH_NOTIFY_ENABLED:-false}" != "true" ]]; then
  exit "${status}"
fi

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "INGEST_HEALTH_NOTIFY_ENABLED=true but TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing; skipping alert." >&2
  exit "${status}"
fi

MESSAGE="$(
  INGEST_HEALTH_OUTPUT_PATH="${TMP_OUTPUT}" \
  INGEST_HEALTH_EXIT_CODE="${status}" \
  INGEST_HEALTH_CONTEXT="${INGEST_HEALTH_CONTEXT:-}" \
  python3 <<'PY'
from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from pathlib import Path

output_path = Path(os.environ["INGEST_HEALTH_OUTPUT_PATH"])
exit_code = os.environ["INGEST_HEALTH_EXIT_CODE"]
context = os.environ.get("INGEST_HEALTH_CONTEXT", "").strip()

try:
    output = output_path.read_text(encoding="utf-8").strip()
except FileNotFoundError:
    output = ""

lines = [line.rstrip() for line in output.splitlines() if line.strip()]
excerpt = lines[:20]
if len(lines) > 20:
    excerpt.append(f"... ({len(lines) - 20} more lines omitted)")

message_lines = [
    "DealerScope ingest health check failed",
    f"exit_code={exit_code}",
    f"host={platform.node() or 'unknown'}",
    f"utc={datetime.now(timezone.utc).isoformat(timespec='seconds')}",
]
if context:
    message_lines.append(f"context={context}")
if excerpt:
    message_lines.append("")
    message_lines.append("check output:")
    message_lines.extend(excerpt)

message = "\n".join(message_lines)
print(message[:3500])
PY
)"

if [[ "${INGEST_HEALTH_NOTIFY_DRY_RUN:-true}" == "true" ]]; then
  echo "[DRY RUN] Telegram alert suppressed." >&2
  printf '%s\n' "${MESSAGE}" >&2
  exit "${status}"
fi

INGEST_HEALTH_MESSAGE="${MESSAGE}" python3 <<'PY'
from __future__ import annotations

import json
import os
from urllib import request

payload = json.dumps(
    {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": os.environ["INGEST_HEALTH_MESSAGE"],
        "disable_web_page_preview": True,
    }
).encode("utf-8")

req = request.Request(
    f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with request.urlopen(req, timeout=15) as response:
    body = json.loads(response.read().decode("utf-8"))

if body.get("ok") is not True:
    raise RuntimeError(
        f"telegram send failed: {body.get('description') or 'missing ok=true response'}"
    )

message_id = ((body.get("result") or {}).get("message_id"))
if message_id in {None, ""}:
    raise RuntimeError("telegram send failed: missing message_id in Telegram response")
PY

exit "${status}"
