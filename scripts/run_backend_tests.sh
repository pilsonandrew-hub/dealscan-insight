#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
  elif command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3.11)"
  else
    PYTHON_BIN="$(command -v python3)"
  fi
fi

PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [[ "$PYTHON_VERSION" != "3.11" ]]; then
  echo "Warning: Python 3.11 is recommended for backend work, found $PYTHON_VERSION" >&2
fi

if ! "$PYTHON_BIN" -m pytest --version >/dev/null 2>&1; then
  cat <<'EOF' >&2
pytest is not installed in the selected Python environment.
Install backend test dependencies first:
  python -m pip install -r requirements-dev.txt
EOF
  exit 1
fi

cd "$PROJECT_ROOT"
DEFAULT_TEST_TARGET="tests/test_analytics_trust_model.py"
if [[ $# -eq 0 ]]; then
  set -- "$DEFAULT_TEST_TARGET"
fi

PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m pytest "$@"
