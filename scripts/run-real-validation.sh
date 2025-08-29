#!/bin/bash
set -euo pipefail

# REAL DealerScope Validation Runner - NO FAUX CODE
# This script performs ACTUAL testing that can FAIL

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
REPORTS_DIR="$PROJECT_ROOT/validation-reports"
BACKEND_PID=""
FRONTEND_PID=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date +'%T')] $*${NC}"; }
success() { echo -e "${GREEN}✅ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $*${NC}"; }
error() { echo -e "${RED}❌ $*${NC}"; }

# CRITICAL: Always ensure we have outputs even if tests fail
ensure_outputs() {
    mkdir -p "$REPORTS_DIR"/{final,raw,security,performance}
    
    # Create minimal outputs - these will be overwritten by real tests
    cat > "$REPORTS_DIR/final/summary.json" << 'EOF'
{
  "generated_at": "placeholder",
  "overall_status": "UNKNOWN",
  "critical_failures": 999,
  "success_rate": 0.0,
  "p95_api_ms": 999999,
  "memory_mb": 999,
  "security_issues": 999
}
EOF

    cat > "$REPORTS_DIR/final/index.html" << 'EOF'
<!DOCTYPE html>
<html><head><title>Validation In Progress</title></head>
<body><h1>Validation Running...</h1><p>This placeholder will be replaced by real results.</p></body></html>
EOF
}

cleanup() {
    log "🧹 Cleaning up background processes..."
    [ -n "$BACKEND_PID" ] && kill $BACKEND_PID 2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill $FRONTEND_PID 2>/dev/null || true
    
    # Kill any remaining processes
    pkill -f "uvicorn.*webapp" 2>/dev/null || true
    pkill -f "vite.*preview" 2>/dev/null || true
}

trap cleanup EXIT

start_real_backend() {
    log "🚀 Starting REAL FastAPI backend..."
    
    # Find and install Python requirements
    if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
        pip install -r "$PROJECT_ROOT/requirements.txt"
    elif [ -f "$PROJECT_ROOT/webapp/requirements.txt" ]; then
        pip install -r "$PROJECT_ROOT/webapp/requirements.txt"
    else
        warn "No requirements.txt found, installing minimal dependencies"
        pip install fastapi uvicorn
    fi
    
    # Start uvicorn with the correct app
    cd "$PROJECT_ROOT"
    nohup uvicorn webapp.main:app --host 127.0.0.1 --port 8000 --log-level warning > /tmp/api.log 2>&1 &
    BACKEND_PID=$!
    
    # REAL health check - this WILL FAIL if backend doesn't start
    log "⏳ Waiting for backend to start..."
    for i in {1..30}; do
        if curl -f -s http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
            success "Backend started successfully"
            return 0
        fi
        sleep 1
    done
    
    error "Backend failed to start within 30 seconds"
    echo "=== Backend logs ==="
    tail -n 50 /tmp/api.log
    return 1
}

start_real_frontend() {
    log "🎨 Starting frontend preview..."
    
    cd "$PROJECT_ROOT"
    
    # Install frontend dependencies 
    if [ -f "frontend/package.json" ]; then
        cd frontend
        npm ci --no-audit --no-fund
        npm run build
        nohup npm run preview > /tmp/frontend.log 2>&1 &
    elif [ -f "package.json" ]; then
        npm ci --no-audit --no-fund
        npm run build
        nohup npm run preview > /tmp/frontend.log 2>&1 &
    else
        warn "No package.json found, skipping frontend"
        return 0
    fi
    
    FRONTEND_PID=$!
    
    # Wait for frontend
    for i in {1..20}; do
        if curl -f -s http://127.0.0.1:4173 > /dev/null 2>&1; then
            success "Frontend started successfully"
            return 0
        fi
        sleep 1
    done
    
    warn "Frontend may not have started properly"
    return 0  # Don't fail on frontend issues
}

test_api_performance() {
    log "⚡ REAL API Performance Test (P95 < 200ms)"
    
    # Install autocannon globally if not available
    if ! command -v autocannon &> /dev/null; then
        npm install -g autocannon
    fi
    
    # REAL performance test that can FAIL
    mkdir -p "$REPORTS_DIR/performance"
    
    autocannon -d 10 -c 20 http://127.0.0.1:8000/healthz --json > "$REPORTS_DIR/performance/api_perf.json"
    
    # Extract REAL P95 latency
    local p95=$(jq '.latency.p95' < "$REPORTS_DIR/performance/api_perf.json")
    log "📊 API P95 latency: ${p95}ms"
    
    # HARD FAIL if P95 > 200ms
    if (( $(echo "$p95 > 200" | bc -l) )); then
        error "API P95 latency (${p95}ms) exceeds 200ms threshold"
        return 1
    fi
    
    success "API performance acceptable (P95: ${p95}ms)"
    echo "{\"p95_ms\": $p95, \"status\": \"pass\"}" > "$REPORTS_DIR/performance/api_latency.json"
}

test_memory_usage() {
    log "🧠 REAL Memory Usage Test (RSS < 120MB)"
    
    # Find the actual uvicorn process
    local pid=$(pgrep -f 'uvicorn.*webapp.*app' | head -1)
    
    if [ -z "$pid" ]; then
        error "No uvicorn process found"
        return 1
    fi
    
    # Get REAL memory usage from /proc
    local rss_kb=$(grep VmRSS /proc/$pid/status | awk '{print $2}')
    local mb=$(( (rss_kb + 1023) / 1024 ))
    
    log "📊 Backend RSS: ${mb}MB"
    
    # HARD FAIL if memory > 120MB
    if [ "$mb" -gt 120 ]; then
        error "Memory usage (${mb}MB) exceeds 120MB threshold"
        return 1
    fi
    
    success "Memory usage acceptable (${mb}MB)"
    echo "{\"memory_mb\": $mb, \"status\": \"pass\"}" > "$REPORTS_DIR/performance/memory.json"
}

test_404_behavior() {
    log "🔍 REAL 404 Test"
    
    # Test a non-existent endpoint - this WILL FAIL if 404 handling is broken
    local code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/__this_does_not_exist__)
    
    log "📊 404 endpoint returned: $code"
    
    if [ "$code" != "404" ]; then
        error "Expected 404, got $code - 404 handling is broken"
        return 1
    fi
    
    success "404 handling works correctly"
    echo "{\"status_code\": $code, \"status\": \"pass\"}" > "$REPORTS_DIR/performance/404_test.json"
}

test_cache_performance() {
    log "💾 REAL Cache Performance Test"
    
    # Test an endpoint that should be cacheable
    local url="http://127.0.0.1:8000/healthz"
    
    # Cold request
    local cold_time=$(curl -s -w '%{time_total}' -o /dev/null "$url")
    
    # Warm request (should hit cache if implemented)
    local warm_time=$(curl -s -w '%{time_total}' -o /dev/null "$url")
    
    log "📊 Cache test - Cold: ${cold_time}s, Warm: ${warm_time}s"
    
    # Simple cache detection: warm should be significantly faster
    local hit_detected=0
    if (( $(echo "$warm_time <= ($cold_time * 0.7)" | bc -l) )); then
        hit_detected=1
        success "Cache hit detected (warm significantly faster)"
    else
        warn "No cache hit detected (warm not significantly faster)"
    fi
    
    echo "{\"cold_time\": $cold_time, \"warm_time\": $warm_time, \"cache_hit\": $hit_detected}" > "$REPORTS_DIR/performance/cache.json"
}

test_real_security() {
    log "🔒 REAL Security Tests"
    mkdir -p "$REPORTS_DIR/security"
    
    local security_issues=0
    
    # 1. Node.js audit (REAL)
    if [ -f "package.json" ] || [ -f "frontend/package.json" ]; then
        log "🔍 Running npm audit..."
        local npm_dir="."
        [ -f "frontend/package.json" ] && npm_dir="frontend"
        
        if ! (cd "$npm_dir" && npm audit --omit=dev --audit-level=high --json > "$REPORTS_DIR/security/npm_audit.json"); then
            warn "npm audit found high severity issues"
            ((security_issues++))
        fi
    fi
    
    # 2. Python dependency audit (REAL)
    log "🔍 Running Python security audit..."
    pip install --upgrade pip-audit safety bandit
    
    local req_file="requirements.txt"
    [ -f "webapp/requirements.txt" ] && req_file="webapp/requirements.txt"
    
    if [ -f "$req_file" ]; then
        if ! pip-audit -r "$req_file" --format=json --output="$REPORTS_DIR/security/pip_audit.json"; then
            warn "pip-audit found vulnerabilities"
            ((security_issues++))
        fi
        
        if ! safety check -r "$req_file" --json --output "$REPORTS_DIR/security/safety_scan.json"; then
            warn "Safety check found vulnerabilities"
            ((security_issues++))
        fi
    fi
    
    # 3. SAST with Bandit (REAL)
    if [ -d "webapp" ]; then
        log "🔍 Running Bandit SAST scan..."
        if ! bandit -r webapp/ -f json -o "$REPORTS_DIR/security/bandit_scan.json"; then
            warn "Bandit found security issues"
            ((security_issues++))
        fi
    fi
    
    # 4. Secrets scan with gitleaks (REAL)
    log "🔍 Running secrets scan..."
    if ! command -v gitleaks &> /dev/null; then
        # Download gitleaks
        curl -sSL "https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks_$(uname -s)_$(uname -m).tar.gz" | tar -xz gitleaks
        chmod +x gitleaks
        mv gitleaks /tmp/
    fi
    
    if ! /tmp/gitleaks detect --no-banner --redact --report-format json --report-path "$REPORTS_DIR/security/gitleaks.json"; then
        warn "Gitleaks found potential secrets"
        ((security_issues++))
    fi
    
    # 5. Rate limiting test (REAL)
    log "🔍 Testing rate limiting..."
    local rate_limit_working=0
    local codes_file="/tmp/rate_test_codes.txt"
    > "$codes_file"  # Clear file
    
    # Rapid fire requests to trigger rate limiting
    for i in $(seq 1 50); do
        curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/healthz || echo "000"
    done > "$codes_file"
    
    local hits_429=$(grep -c '^429$' "$codes_file" || echo "0")
    if [ "$hits_429" -ge 1 ]; then
        success "Rate limiting working (got $hits_429 429 responses)"
        rate_limit_working=1
    else
        warn "Rate limiting not working (no 429 responses)"
        ((security_issues++))
    fi
    
    echo "{\"security_issues\": $security_issues, \"rate_limit_working\": $rate_limit_working}" > "$REPORTS_DIR/security/summary.json"
    
    if [ $security_issues -gt 5 ]; then
        error "Too many security issues found: $security_issues"
        return 1
    fi
    
    success "Security scan completed with $security_issues issues"
}

generate_real_summary() {
    log "📊 Generating REAL validation summary..."
    
    local overall_status="PASS"
    local critical_failures=0
    
    # Read actual performance data
    local p95_ms=999999
    local memory_mb=999
    local security_issues=999
    
    if [ -f "$REPORTS_DIR/performance/api_perf.json" ]; then
        p95_ms=$(jq '.latency.p95' < "$REPORTS_DIR/performance/api_perf.json")
    fi
    
    if [ -f "$REPORTS_DIR/performance/memory.json" ]; then
        memory_mb=$(jq '.memory_mb' < "$REPORTS_DIR/performance/memory.json")
    fi
    
    if [ -f "$REPORTS_DIR/security/summary.json" ]; then
        security_issues=$(jq '.security_issues' < "$REPORTS_DIR/security/summary.json")
    fi
    
    # Calculate success rate based on actual tests
    local tests_passed=0
    local total_tests=0
    
    # Count performance tests
    for test_file in "$REPORTS_DIR/performance"/*.json; do
        if [ -f "$test_file" ]; then
            ((total_tests++))
            if jq -e '.status == "pass"' "$test_file" > /dev/null 2>&1; then
                ((tests_passed++))
            fi
        fi
    done
    
    # Apply REAL SLO gates
    if (( $(echo "$p95_ms > 200" | bc -l) )); then
        overall_status="FAIL"
        ((critical_failures++))
    fi
    
    if [ "$memory_mb" -gt 120 ]; then
        overall_status="FAIL"
        ((critical_failures++))
    fi
    
    if [ "$security_issues" -gt 5 ]; then
        overall_status="FAIL"
        ((critical_failures++))
    fi
    
    local success_rate=0
    if [ $total_tests -gt 0 ]; then
        success_rate=$(echo "scale=2; ($tests_passed * 100.0) / $total_tests" | bc)
    fi
    
    # Generate REAL summary.json
    cat > "$REPORTS_DIR/final/summary.json" << EOF
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "overall_status": "$overall_status",
  "critical_failures": $critical_failures,
  "success_rate": $success_rate,
  "p95_api_ms": $p95_ms,
  "memory_mb": $memory_mb,
  "security_issues": $security_issues,
  "tests_passed": $tests_passed,
  "total_tests": $total_tests,
  "slo_gates": {
    "api_p95_under_200ms": $([ $(echo "$p95_ms <= 200" | bc -l) -eq 1 ] && echo "true" || echo "false"),
    "memory_under_120mb": $([ "$memory_mb" -le 120 ] && echo "true" || echo "false"),
    "security_issues_under_5": $([ "$security_issues" -le 5 ] && echo "true" || echo "false")
  }
}
EOF

    # Generate REAL HTML dashboard
    local status_color="red"
    local status_text="FAILED"
    if [ "$overall_status" = "PASS" ]; then
        status_color="green"
        status_text="PASSED"
    fi
    
    cat > "$REPORTS_DIR/final/index.html" << EOF
<!DOCTYPE html>
<html>
<head>
    <title>DealerScope Validation Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .status-pass { color: green; }
        .status-fail { color: red; }
        .metric { margin: 10px 0; padding: 10px; border-left: 4px solid #ccc; }
        .metric.critical { border-left-color: red; }
        .metric.pass { border-left-color: green; }
    </style>
</head>
<body>
    <h1>🚀 DealerScope Validation Results</h1>
    <h2 class="status-$status_color">Overall Status: $status_text</h2>
    
    <h3>📊 Real Metrics</h3>
    <div class="metric $([ $(echo "$p95_ms <= 200" | bc -l) -eq 1 ] && echo "pass" || echo "critical")">
        <strong>API P95 Latency:</strong> ${p95_ms}ms (SLO: ≤200ms)
    </div>
    <div class="metric $([ "$memory_mb" -le 120 ] && echo "pass" || echo "critical")">
        <strong>Memory Usage:</strong> ${memory_mb}MB (SLO: ≤120MB)
    </div>
    <div class="metric $([ "$security_issues" -le 5 ] && echo "pass" || echo "critical")">
        <strong>Security Issues:</strong> $security_issues (SLO: ≤5)
    </div>
    <div class="metric">
        <strong>Test Success Rate:</strong> ${success_rate}% (${tests_passed}/${total_tests})
    </div>
    
    <h3>🔗 Raw Reports</h3>
    <ul>
        <li><a href="../performance/api_perf.json">API Performance Data</a></li>
        <li><a href="../security/summary.json">Security Scan Results</a></li>
        <li><a href="./summary.json">Complete Summary JSON</a></li>
    </ul>
    
    <p><small>Generated: $(date)</small></p>
</body>
</html>
EOF

    log "📋 Summary generated - Status: $overall_status, Critical failures: $critical_failures"
}

enforce_slo_gates() {
    log "🚪 Enforcing REAL SLO Gates..."
    
    if ! [ -f "$REPORTS_DIR/final/summary.json" ]; then
        error "No summary.json found - validation incomplete"
        return 1
    fi
    
    # HARD GATE: Use jq to enforce actual numeric SLOs
    if ! jq -e '
        (.p95_api_ms <= 200) and
        (.memory_mb <= 120) and  
        (.security_issues <= 5) and
        (.success_rate >= 80)
    ' "$REPORTS_DIR/final/summary.json" > /dev/null; then
        error "❌ SLO gates FAILED"
        jq '.' "$REPORTS_DIR/final/summary.json"
        return 1
    fi
    
    success "✅ All SLO gates PASSED"
}

main() {
    echo "🎯 DealerScope REAL Validation Runner - NO FAUX CODE!"
    
    # Always ensure we have some output
    ensure_outputs
    
    # Start real services
    start_real_backend || return 1
    start_real_frontend
    
    # Run REAL tests that can FAIL
    local exit_code=0
    
    test_api_performance || exit_code=1
    test_memory_usage || exit_code=1
    test_404_behavior || exit_code=1
    test_cache_performance || exit_code=1
    test_real_security || exit_code=1
    
    # Generate real summary from real data
    generate_real_summary
    
    # Apply HARD SLO gates
    enforce_slo_gates || exit_code=1
    
    if [ $exit_code -eq 0 ]; then
        success "🎉 ALL VALIDATIONS PASSED - Ready for production!"
    else
        error "💥 VALIDATION FAILURES DETECTED - Not ready for production"
    fi
    
    return $exit_code
}

# Run it
main "$@"