#!/usr/bin/env bash
# Investment-Grade SLO Enforcement Script
# Enforces Service Level Objectives for production deployment
set -euo pipefail

echo "🎯 Enforcing Service Level Objectives..."

# Configuration
SUMMARY_FILE="${1:-validation-reports/final/summary.json}"
REPORTS_DIR="${2:-validation-reports/final}"

# SLO Thresholds (Investment Grade)
readonly MAX_SECURITY_ISSUES=3
readonly MAX_API_LATENCY_MS=200
readonly MAX_MEMORY_USAGE_MB=150
readonly MIN_SUCCESS_RATE=95

# Validate inputs
if [[ ! -f "$SUMMARY_FILE" ]]; then
    echo "::error::SLO enforcement failed - summary file not found: $SUMMARY_FILE"
    echo "Available files in validation-reports:"
    find validation-reports -type f -name "*.json" 2>/dev/null || echo "No JSON files found"
    exit 1
fi

if [[ ! -f "$REPORTS_DIR/index.html" ]]; then
    echo "::error::SLO enforcement failed - dashboard not found: $REPORTS_DIR/index.html"
    exit 1
fi

echo "📊 Analyzing validation results..."

# Extract metrics from summary
extract_metric() {
    local key="$1"
    local default="$2"
    grep -o "\"$key\":[^,}]*" "$SUMMARY_FILE" | cut -d':' -f2 | tr -d ' "' || echo "$default"
}

# Parse critical metrics
overall_status=$(extract_metric "overall_status" "UNKNOWN")
security_issues=$(extract_metric "security_issues" "999")
api_latency=$(extract_metric "p95_api_ms" "999")
memory_usage=$(extract_metric "memory_mb" "999")
success_rate=$(extract_metric "success_rate" "0")

echo "Current Metrics:"
echo "  Overall Status: $overall_status"
echo "  Security Issues: $security_issues"
echo "  API Latency: ${api_latency}ms"
echo "  Memory Usage: ${memory_usage}MB"
echo "  Success Rate: ${success_rate}%"

# SLO Gate Enforcement
failed_gates=()
gate_status="PASS"

echo ""
echo "🚪 Evaluating SLO Gates..."

# Security Gate
if [[ "$security_issues" -gt "$MAX_SECURITY_ISSUES" ]]; then
    echo "❌ Security Gate FAILED: $security_issues issues (max: $MAX_SECURITY_ISSUES)"
    failed_gates+=("SECURITY")
    gate_status="FAIL"
else
    echo "✅ Security Gate PASSED: $security_issues issues (max: $MAX_SECURITY_ISSUES)"
fi

# Performance Gate
if [[ "$api_latency" -gt "$MAX_API_LATENCY_MS" ]]; then
    echo "❌ Performance Gate FAILED: ${api_latency}ms (max: ${MAX_API_LATENCY_MS}ms)"
    failed_gates+=("PERFORMANCE")
    gate_status="FAIL"
else
    echo "✅ Performance Gate PASSED: ${api_latency}ms (max: ${MAX_API_LATENCY_MS}ms)"
fi

# Memory Gate
if [[ "$memory_usage" -gt "$MAX_MEMORY_USAGE_MB" ]]; then
    echo "❌ Memory Gate FAILED: ${memory_usage}MB (max: ${MAX_MEMORY_USAGE_MB}MB)"
    failed_gates+=("MEMORY")
    gate_status="FAIL"
else
    echo "✅ Memory Gate PASSED: ${memory_usage}MB (max: ${MAX_MEMORY_USAGE_MB}MB)"
fi

# Success Rate Gate
if [[ "$success_rate" -lt "$MIN_SUCCESS_RATE" ]]; then
    echo "❌ Success Rate Gate FAILED: ${success_rate}% (min: ${MIN_SUCCESS_RATE}%)"
    failed_gates+=("SUCCESS_RATE")
    gate_status="FAIL"
else
    echo "✅ Success Rate Gate PASSED: ${success_rate}% (min: ${MIN_SUCCESS_RATE}%)"
fi

# Overall Status Check
if [[ "$overall_status" != "PASS" ]]; then
    echo "❌ Overall Status Gate FAILED: $overall_status"
    failed_gates+=("OVERALL_STATUS")
    gate_status="FAIL"
else
    echo "✅ Overall Status Gate PASSED: $overall_status"
fi

echo ""

# Final Decision
if [[ "$gate_status" == "PASS" ]]; then
    echo "🎉 All SLO gates satisfied - DEPLOYMENT APPROVED"
    echo "Investment-grade quality standards met."
    
    # Update summary with SLO status
    if command -v jq >/dev/null 2>&1; then
        jq '. + {"slo_enforcement": {"status": "PASSED", "gates_failed": [], "enforced_at": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}}' \
           "$SUMMARY_FILE" > "${SUMMARY_FILE}.tmp" && mv "${SUMMARY_FILE}.tmp" "$SUMMARY_FILE"
    fi
    
    exit 0
else
    echo "💥 SLO ENFORCEMENT FAILED"
    echo "Failed gates: ${failed_gates[*]}"
    echo ""
    echo "Investment-grade standards NOT met:"
    for gate in "${failed_gates[@]}"; do
        echo "  - $gate gate failed"
    done
    echo ""
    echo "🚫 DEPLOYMENT BLOCKED - Fix issues before retry"
    
    # Update summary with failure details
    if command -v jq >/dev/null 2>&1; then
        jq '. + {"slo_enforcement": {"status": "FAILED", "gates_failed": ["'$(IFS='","'; echo "${failed_gates[*]}").'"], "enforced_at": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'"}}' \
           "$SUMMARY_FILE" > "${SUMMARY_FILE}.tmp" && mv "${SUMMARY_FILE}.tmp" "$SUMMARY_FILE"
    fi
    
    exit 1
fi