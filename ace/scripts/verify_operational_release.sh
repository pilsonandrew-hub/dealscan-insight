#!/usr/bin/env sh
# Read-only ACE 2.0 operational verification (no network except optional contradictions CI).
set -eu
repo_root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo_root"
if [ -x "$repo_root/.venv/bin/python" ]; then
  py="$repo_root/.venv/bin/python"
else
  py=${PYTHON:-python3}
fi

echo "== ace contradictions (offline) =="
"$py" -m ace.ace contradictions --skip-ci

echo ""
echo "== ace filter-health (current UTC month) =="
"$py" -m ace.ace filter-health

echo ""
echo "== operational pytest subset =="
"$py" -m pytest \
  ace/tests/test_doc_contradictions.py \
  ace/tests/test_digest_resume_context.py \
  ace/tests/test_false_closure_advisory.py \
  ace/tests/test_propose_commitments.py \
  ace/tests/test_filter_health.py \
  -q

echo ""
echo "verify_operational_release=ok"
