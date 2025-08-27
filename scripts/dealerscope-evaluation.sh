#!/usr/bin/env bash
set -euo pipefail

# DealerScope Elite Evaluation Script v2.0
# Enhanced frontend evaluation with configurable settings and improved error handling

# Configuration - can be overridden via environment variables
PORT=${EVAL_PORT:-5173}  # Configurable port
OUTDIR=${EVAL_OUTDIR:-"evaluation-reports"}
STARTUP_TIMEOUT=${EVAL_STARTUP_TIMEOUT:-45}  # Configurable startup timeout
PERFORMANCE_RUNS=${EVAL_PERF_RUNS:-5}  # Number of performance test runs
CURL_TIMEOUT=${EVAL_CURL_TIMEOUT:-10}  # Curl timeout in seconds

# Create output directory with enhanced error handling
if ! mkdir -p "$OUTDIR"; then
    echo "❌ Failed to create output directory: $OUTDIR" >&2
    exit 1
fi

bold(){ printf "\033[1m%s\033[0m\n" "$*"; }
log(){ echo "[$(date +'%F %T')] $*"; }
fail(){ echo "❌ $*"; exit 1; }
pass(){ echo "✅ $*"; }

# Enhanced frontend availability check with configurable timeout
bold "Checking DealerScope Frontend (port $PORT)..."
log "Testing connectivity to http://localhost:$PORT..."

# Test with enhanced error reporting
CURL_RESULT=$(curl -fsS --connect-timeout 5 --max-time "$CURL_TIMEOUT" "http://localhost:$PORT" 2>&1) || CURL_EXIT_CODE=$?

if [ "${CURL_EXIT_CODE:-0}" -ne 0 ]; then
  log "Frontend not accessible (curl exit code: ${CURL_EXIT_CODE:-0})"
  bold "Starting DealerScope frontend with enhanced monitoring..."
  
  # Start with port specification
  npm run dev -- --port "$PORT" &
  DEV_PID=$!
  
  # Enhanced cleanup function with better process management
  cleanup() {
    if [ -n "${DEV_PID:-}" ] && kill -0 "$DEV_PID" 2>/dev/null; then
      log "Terminating development server (PID: $DEV_PID)..."
      kill "$DEV_PID" 2>/dev/null || true
      
      # Wait for graceful shutdown
      local attempts=0
      while [ $attempts -lt 10 ] && kill -0 "$DEV_PID" 2>/dev/null; do
        sleep 1
        attempts=$((attempts + 1))
      done
      
      # Force kill if still running
      if kill -0 "$DEV_PID" 2>/dev/null; then
        log "Force terminating development server..."
        kill -9 "$DEV_PID" 2>/dev/null || true
      fi
      
      log "Development server cleanup completed"
    fi
  }
  trap cleanup EXIT INT TERM
  
  # Enhanced startup monitoring with configurable timeout
  log "Waiting for frontend startup (timeout: ${STARTUP_TIMEOUT}s)..."
  ATTEMPTS=0
  SLEEP_INTERVAL=2
  MAX_ATTEMPTS=$((STARTUP_TIMEOUT / SLEEP_INTERVAL))
  
  until curl -fsS --connect-timeout 3 --max-time 5 "http://localhost:$PORT" >/dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ "$ATTEMPTS" -gt "$MAX_ATTEMPTS" ]; then
      log "Last curl attempt error log:"
      curl -fsS --connect-timeout 3 --max-time 5 "http://localhost:$PORT" 2>&1 || true
      fail "Frontend did not start within ${STARTUP_TIMEOUT}s (attempted $ATTEMPTS times)"
    fi
    
    # Progress indicator
    if [ $((ATTEMPTS % 5)) -eq 0 ]; then
      log "Still waiting... (attempt $ATTEMPTS/$MAX_ATTEMPTS)"
    fi
    
    sleep $SLEEP_INTERVAL
  done
  
  log "Frontend startup completed after $((ATTEMPTS * SLEEP_INTERVAL))s"
fi

pass "Frontend is accessible"

json_escape() { 
  python3 - <<'PY' "$1"
import json,sys; print(json.dumps(sys.argv[1]))
PY
}

RESULTS_JSON="$OUTDIR/frontend-results.json"
HTML_REPORT="$OUTDIR/frontend-report.html"
echo '{"tests":[],"metrics":{},"summary":{},"timestamp":"'$(date -Iseconds)'"}' > "$RESULTS_JSON"

add_result() {
  local name="$1" status="$2" detail="${3:-}"
  python3 - "$RESULTS_JSON" "$name" "$status" "$detail" <<'PY'
import json,sys
p=sys.argv[1]; name=sys.argv[2]; status=sys.argv[3]; detail=sys.argv[4] if len(sys.argv)>4 else ""
d=json.load(open(p))
d["tests"].append({"name":name,"status":status,"detail":detail,"timestamp":"$(date -Iseconds)"})
json.dump(d,open(p,"w"),indent=2)
PY
}

set_metric() {
  local key="$1" val="$2"
  python3 - "$RESULTS_JSON" "$key" "$val" <<'PY'
import json,sys
p=sys.argv[1]; k=sys.argv[2]; v=sys.argv[3]
d=json.load(open(p))
d.setdefault("metrics",{})[k]=v
json.dump(d,open(p,"w"),indent=2)
PY
}

bold "Running DealerScope Frontend Evaluation..."

# ---- Frontend Tests ----

# 1. Basic Load Test
if HTML=$(curl -fsS "http://localhost:$PORT" 2>/dev/null); then
  if echo "$HTML" | grep -qi "DealerScope" || echo "$HTML" | grep -qi "vite"; then
    add_result "frontend-loads" "pass" "Frontend loads successfully"
  else
    add_result "frontend-loads" "fail" "Frontend loads but missing expected content"
  fi
else
  add_result "frontend-loads" "fail" "Frontend failed to load"
fi

# 2. Security Headers Test
HEADERS=$(curl -sI "http://localhost:$PORT" 2>/dev/null || true)
if echo "$HEADERS" | grep -qi "Content-Security-Policy\|X-Frame-Options\|X-Content-Type-Options"; then
  add_result "security-headers" "pass" "Security headers present"
else
  add_result "security-headers" "warn" "Security headers missing (dev mode expected)"
fi

# 3. Enhanced Performance Test - Page Load Times with error handling
bold "Testing page load performance (${PERFORMANCE_RUNS} runs)..."
LOAD_TIMES=()
FAILED_REQUESTS=0

for i in $(seq 1 "$PERFORMANCE_RUNS"); do
  log "Performance test run $i/$PERFORMANCE_RUNS..."
  
  # Enhanced curl with timeout and error handling
  if TIME_OUTPUT=$(curl -s --connect-timeout 5 --max-time "$CURL_TIMEOUT" \
                     -w "%{time_total},%{http_code},%{size_download}" \
                     -o /dev/null "http://localhost:$PORT" 2>&1); then
    
    TIME_TOTAL=$(echo "$TIME_OUTPUT" | cut -d',' -f1)
    HTTP_CODE=$(echo "$TIME_OUTPUT" | cut -d',' -f2)
    SIZE_BYTES=$(echo "$TIME_OUTPUT" | cut -d',' -f3)
    
    if [ "$HTTP_CODE" = "200" ]; then
      TIME_MS=$(awk "BEGIN {printf(\"%.0f\", $TIME_TOTAL * 1000)}")
      LOAD_TIMES+=("$TIME_MS")
      log "Run $i: ${TIME_MS}ms (${SIZE_BYTES} bytes)"
    else
      log "Run $i failed: HTTP $HTTP_CODE"
      FAILED_REQUESTS=$((FAILED_REQUESTS + 1))
    fi
  else
    log "Run $i failed: Network error"
    FAILED_REQUESTS=$((FAILED_REQUESTS + 1))
  fi
done

# Report failed requests
if [ "$FAILED_REQUESTS" -gt 0 ]; then
  set_metric "failed_requests" "$FAILED_REQUESTS"
  add_result "network-reliability" "warn" "$FAILED_REQUESTS/$PERFORMANCE_RUNS requests failed"
else
  add_result "network-reliability" "pass" "All $PERFORMANCE_RUNS requests successful"
fi

# Calculate average
TOTAL=0
for time in "${LOAD_TIMES[@]}"; do
  TOTAL=$((TOTAL + time))
done
AVG_LOAD_TIME=$((TOTAL / ${#LOAD_TIMES[@]}))

set_metric "avg_load_time_ms" "$AVG_LOAD_TIME"
if [ "$AVG_LOAD_TIME" -lt 1000 ]; then
  add_result "load-performance" "pass" "Avg load time: ${AVG_LOAD_TIME}ms (<1000ms)"
elif [ "$AVG_LOAD_TIME" -lt 2000 ]; then
  add_result "load-performance" "warn" "Avg load time: ${AVG_LOAD_TIME}ms (1000-2000ms)"
else
  add_result "load-performance" "fail" "Avg load time: ${AVG_LOAD_TIME}ms (>2000ms)"
fi

# 4. Bundle Size Analysis (if build exists)
if [ -d "dist" ]; then
  bold "Analyzing bundle size..."
  BUNDLE_SIZE=$(du -sh dist/ 2>/dev/null | cut -f1 || echo "unknown")
  set_metric "bundle_size" "$BUNDLE_SIZE"
  add_result "bundle-analysis" "pass" "Bundle size: $BUNDLE_SIZE"
else
  add_result "bundle-analysis" "skip" "No dist/ folder found (dev mode)"
fi

# 5. React/Component Tests (check for React in page source)
if echo "$HTML" | grep -qi "react\|__vite\|root"; then
  add_result "react-app" "pass" "React application detected"
else
  add_result "react-app" "fail" "React application not detected"
fi

# 6. CSS/Styling Tests
if echo "$HTML" | grep -qi "tailwind\|css\|style"; then
  add_result "styling-present" "pass" "Styling/CSS detected"
else
  add_result "styling-present" "fail" "No styling detected"
fi

# 7. Error Handling Test (404 page)
HTTP_404=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$PORT/nonexistent-page" || echo "000")
if [ "$HTTP_404" = "404" ] || [ "$HTTP_404" = "200" ]; then
  add_result "error-handling" "pass" "404 handling works (HTTP $HTTP_404)"
else
  add_result "error-handling" "fail" "Unexpected 404 response: HTTP $HTTP_404"
fi

# 8. Accessibility Basic Check
if echo "$HTML" | grep -qi 'alt=\|aria-\|role=\|tabindex'; then
  add_result "accessibility-basics" "pass" "Basic accessibility attributes found"
else
  add_result "accessibility-basics" "warn" "Limited accessibility attributes"
fi

# 9. Mobile Responsiveness
if echo "$HTML" | grep -qi 'viewport.*responsive\|device-width'; then
  add_result "mobile-responsive" "pass" "Viewport meta tag found"
else
  add_result "mobile-responsive" "fail" "Mobile viewport not configured"
fi

# 10. Modern Features Test
if echo "$HTML" | grep -qi 'type="module"\|es6\|async\|defer'; then
  add_result "modern-features" "pass" "Modern JavaScript features detected"
else
  add_result "modern-features" "warn" "Limited modern features detected"
fi

# ---- Generate Summary ----
bold "Generating evaluation summary..."

python3 - "$RESULTS_JSON" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p))
total=len(d["tests"]) 
passed=sum(1 for t in d["tests"] if t["status"]=="pass")
warned=sum(1 for t in d["tests"] if t["status"]=="warn") 
failed=sum(1 for t in d["tests"] if t["status"]=="fail")
skipped=sum(1 for t in d["tests"] if t["status"]=="skip")

score_pct = round(100.0 * (passed + warned*0.5) / max(1,total-skipped), 1)

d["summary"]={
  "total":total,
  "passed":passed, 
  "warned":warned,
  "failed":failed,
  "skipped":skipped,
  "score_pct":score_pct,
  "grade": "A" if score_pct >= 90 else "B" if score_pct >= 80 else "C" if score_pct >= 70 else "D" if score_pct >= 60 else "F"
}
json.dump(d,open(p,"w"),indent=2)
print(f"Score: {score_pct}% (Grade: {d['summary']['grade']})")
print(f"Results: {passed} passed, {warned} warnings, {failed} failed, {skipped} skipped")
PY

# ---- Generate HTML Report ----
python3 - "$RESULTS_JSON" "$HTML_REPORT" <<'PY'
import json,sys,html
from datetime import datetime

data=json.load(open(sys.argv[1]))
out=sys.argv[2]
summary=data["summary"]

status_icons = {"pass": "✅", "fail": "❌", "warn": "⚠️", "skip": "⏭️"}
status_colors = {"pass": "#22c55e", "fail": "#ef4444", "warn": "#f59e0b", "skip": "#6b7280"}

rows = "\n".join(
    f'<tr style="background-color: {status_colors.get(t["status"], "#f3f4f6")}20">'
    f'<td>{html.escape(t["name"])}</td>'
    f'<td style="text-align: center">{status_icons.get(t["status"], "❓")}</td>'
    f'<td>{html.escape(t.get("detail", ""))}</td></tr>'
    for t in data["tests"]
)

metrics_rows = "\n".join(
    f"<tr><td><b>{html.escape(k)}</b></td><td>{html.escape(str(v))}</td></tr>"
    for k, v in data.get("metrics", {}).items()
)

grade_color = {"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D": "#f97316", "F": "#ef4444"}.get(summary["grade"], "#6b7280")

with open(out, "w") as f:
    f.write(f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DealerScope Frontend Evaluation Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f8fafc; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); padding: 30px; }}
        h1 {{ color: #1e293b; margin-bottom: 10px; }}
        .grade {{ display: inline-block; padding: 8px 16px; border-radius: 8px; color: white; font-weight: bold; font-size: 1.2em; background: {grade_color}; }}
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
        .metric-card {{ background: #f1f5f9; padding: 15px; border-radius: 8px; text-align: center; }}
        .metric-value {{ font-size: 1.5em; font-weight: bold; color: #1e293b; }}
        .metric-label {{ color: #64748b; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f8fafc; font-weight: 600; color: #374151; }}
        .timestamp {{ color: #64748b; font-size: 0.9em; }}
        .summary-stats {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat {{ text-align: center; }}
        .stat-number {{ font-size: 2em; font-weight: bold; }}
        .stat-label {{ color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 DealerScope Frontend Evaluation</h1>
        <p class="timestamp">Generated: {data.get("timestamp", "Unknown")}</p>
        
        <div style="display: flex; align-items: center; gap: 20px; margin: 20px 0;">
            <span class="grade">{summary["grade"]}</span>
            <div>
                <div style="font-size: 1.5em; font-weight: bold;">{summary["score_pct"]}% Overall Score</div>
                <div class="timestamp">{summary["passed"]} passed, {summary["warned"]} warnings, {summary["failed"]} failed</div>
            </div>
        </div>

        <div class="summary-stats">
            <div class="stat" style="color: #22c55e;">
                <div class="stat-number">{summary["passed"]}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat" style="color: #f59e0b;">
                <div class="stat-number">{summary["warned"]}</div>
                <div class="stat-label">Warnings</div>
            </div>
            <div class="stat" style="color: #ef4444;">
                <div class="stat-number">{summary["failed"]}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat" style="color: #6b7280;">
                <div class="stat-number">{summary["skipped"]}</div>
                <div class="stat-label">Skipped</div>
            </div>
        </div>

        <h2>📊 Performance Metrics</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            {metrics_rows}
        </table>

        <h2>🧪 Test Results</h2>
        <table>
            <tr><th>Test Name</th><th>Status</th><th>Details</th></tr>
            {rows}
        </table>

        <h2>📝 Recommendations</h2>
        <div style="background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;">
            <h3 style="margin-top: 0;">Performance Optimization</h3>
            <ul>
                <li>Implement code splitting for better load times</li>
                <li>Add service worker for offline capabilities</li>
                <li>Optimize images and assets</li>
            </ul>
        </div>
        
        <div style="background: #fee2e2; padding: 15px; border-radius: 8px; border-left: 4px solid #ef4444; margin-top: 15px;">
            <h3 style="margin-top: 0;">Security Enhancements</h3>
            <ul>
                <li>Add Content Security Policy headers</li>
                <li>Implement proper error boundaries</li>
                <li>Add input validation and sanitization</li>
            </ul>
        </div>
    </div>
</body>
</html>''')

print(f"HTML report generated: {out}")
PY

bold "✅ Evaluation Complete!"
echo ""
echo "📊 Results:"
echo "  JSON: $RESULTS_JSON" 
echo "  HTML: $HTML_REPORT"
echo ""
echo "🚀 Open the HTML report in your browser for detailed analysis"