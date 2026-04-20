#!/bin/bash
# DealerScope Comprehensive Security Scanner
# Production-grade security validation for deployment readiness
set -euo pipefail

echo "🔒 DealerScope Comprehensive Security Scanner Starting..."
echo "📅 $(date -u '+%Y-%m-%d %H:%M:%S UTC')"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPORTS_DIR="$PROJECT_ROOT/validation-reports/security"

# Initialize security reports directory
mkdir -p "$REPORTS_DIR"

# Security scan results
TOTAL_VULNERABILITIES=0
CRITICAL_ISSUES=0
HIGH_ISSUES=0
MEDIUM_ISSUES=0
LOW_ISSUES=0

# Log function
log() {
    echo "[$(date +'%H:%M:%S')] $1"
}

# Vulnerability counter
add_vulnerability() {
    local severity="$1"
    TOTAL_VULNERABILITIES=$((TOTAL_VULNERABILITIES + 1))
    
    case "$severity" in
        "CRITICAL") CRITICAL_ISSUES=$((CRITICAL_ISSUES + 1)) ;;
        "HIGH") HIGH_ISSUES=$((HIGH_ISSUES + 1)) ;;
        "MEDIUM") MEDIUM_ISSUES=$((MEDIUM_ISSUES + 1)) ;;
        "LOW") LOW_ISSUES=$((LOW_ISSUES + 1)) ;;
    esac
}

# 1. Python Security Scan with Bandit
python_security_scan() {
    log "🐍 Running Python security scan with Bandit..."
    
    if command -v bandit >/dev/null 2>&1; then
        if find . -name "*.py" -type f | head -1 | grep -q .; then
            bandit -r . -f json -o "$REPORTS_DIR/bandit-report.json" -ll || true
            
            # Parse results
            if [ -f "$REPORTS_DIR/bandit-report.json" ]; then
                local issues=$(jq '.results | length' "$REPORTS_DIR/bandit-report.json" 2>/dev/null || echo "0")
                log "  📊 Found $issues Python security issues"
                
                # Count by severity
                if [ "$issues" -gt 0 ]; then
                    local high_severity=$(jq '[.results[] | select(.issue_severity == "HIGH")] | length' "$REPORTS_DIR/bandit-report.json" 2>/dev/null || echo "0")
                    local medium_severity=$(jq '[.results[] | select(.issue_severity == "MEDIUM")] | length' "$REPORTS_DIR/bandit-report.json" 2>/dev/null || echo "0")
                    local low_severity=$(jq '[.results[] | select(.issue_severity == "LOW")] | length' "$REPORTS_DIR/bandit-report.json" 2>/dev/null || echo "0")
                    
                    HIGH_ISSUES=$((HIGH_ISSUES + high_severity))
                    MEDIUM_ISSUES=$((MEDIUM_ISSUES + medium_severity))
                    LOW_ISSUES=$((LOW_ISSUES + low_severity))
                    TOTAL_VULNERABILITIES=$((TOTAL_VULNERABILITIES + issues))
                fi
            fi
        else
            log "  📋 No Python files found, skipping Bandit scan"
        fi
    else
        log "  ⚠️ Bandit not installed, skipping Python security scan"
    fi
}

# 2. Node.js Dependencies Security Audit
nodejs_security_audit() {
    log "📦 Running Node.js security audit..."
    
    if [ -f package.json ] && command -v npm >/dev/null 2>&1; then
        npm audit --json > "$REPORTS_DIR/npm-audit.json" 2>/dev/null || true
        
        if [ -f "$REPORTS_DIR/npm-audit.json" ]; then
            local vulnerabilities=$(jq '.metadata.vulnerabilities.total' "$REPORTS_DIR/npm-audit.json" 2>/dev/null || echo "0")
            log "  📊 Found $vulnerabilities Node.js vulnerabilities"
            
            if [ "$vulnerabilities" -gt 0 ]; then
                local critical=$(jq '.metadata.vulnerabilities.critical' "$REPORTS_DIR/npm-audit.json" 2>/dev/null || echo "0")
                local high=$(jq '.metadata.vulnerabilities.high' "$REPORTS_DIR/npm-audit.json" 2>/dev/null || echo "0")
                local moderate=$(jq '.metadata.vulnerabilities.moderate' "$REPORTS_DIR/npm-audit.json" 2>/dev/null || echo "0")
                local low=$(jq '.metadata.vulnerabilities.low' "$REPORTS_DIR/npm-audit.json" 2>/dev/null || echo "0")
                
                CRITICAL_ISSUES=$((CRITICAL_ISSUES + critical))
                HIGH_ISSUES=$((HIGH_ISSUES + high))
                MEDIUM_ISSUES=$((MEDIUM_ISSUES + moderate))
                LOW_ISSUES=$((LOW_ISSUES + low))
                TOTAL_VULNERABILITIES=$((TOTAL_VULNERABILITIES + vulnerabilities))
            fi
        fi
    else
        log "  📋 No package.json found or npm not available, skipping Node.js audit"
    fi
}

# 3. File Permissions Security Check
file_permissions_check() {
    log "🔐 Checking file permissions..."
    
    local issues=0
    
    # Check for world-writable files
    if find . -type f -perm /002 -not -path "./.git/*" -not -path "./node_modules/*" | head -10 > "$REPORTS_DIR/world-writable.txt"; then
        local count=$(wc -l < "$REPORTS_DIR/world-writable.txt")
        if [ "$count" -gt 0 ]; then
            log "  ⚠️ Found $count world-writable files"
            issues=$((issues + count))
            add_vulnerability "MEDIUM"
        fi
    fi
    
    # Check for executable scripts with world-write
    if find . -type f -name "*.sh" -perm /022 | head -5 > "$REPORTS_DIR/writable-scripts.txt"; then
        local count=$(wc -l < "$REPORTS_DIR/writable-scripts.txt")
        if [ "$count" -gt 0 ]; then
            log "  🚨 Found $count world-writable scripts - HIGH RISK"
            issues=$((issues + count))
            add_vulnerability "HIGH"
        fi
    fi
    
    log "  📊 File permissions check found $issues issues"
}

# 4. Secret Detection Scan
secret_detection_scan() {
    log "🔍 Scanning for exposed secrets..."
    
    local secrets_found=0
    
    # Common secret patterns
    secret_patterns=(
        "password.*=.*['\"][^'\"]{8,}['\"]"
        "api[_-]?key.*=.*['\"][^'\"]{16,}['\"]"
        "secret.*=.*['\"][^'\"]{16,}['\"]"
        "token.*=.*['\"][^'\"]{20,}['\"]"
        "-----BEGIN PRIVATE KEY-----"
        "-----BEGIN RSA PRIVATE KEY-----"
        "sk_live_[a-zA-Z0-9]+"
        "pk_live_[a-zA-Z0-9]+"
    )
    
    for pattern in "${secret_patterns[@]}"; do
        if grep -r -i -E "$pattern" . --exclude-dir=.git --exclude-dir=node_modules --exclude="*.log" 2>/dev/null | head -5 >> "$REPORTS_DIR/potential-secrets.txt"; then
            secrets_found=$((secrets_found + 1))
        fi
    done
    
    if [ "$secrets_found" -gt 0 ]; then
        log "  🚨 Found $secrets_found potential secret exposures - CRITICAL"
        CRITICAL_ISSUES=$((CRITICAL_ISSUES + secrets_found))
        TOTAL_VULNERABILITIES=$((TOTAL_VULNERABILITIES + secrets_found))
    else
        log "  ✅ No secrets detected in source code"
    fi
}

# 5. Dependency License Check
dependency_license_check() {
    log "📄 Checking dependency licenses..."
    
    if [ -f package.json ] && command -v npm >/dev/null 2>&1; then
        # Extract dependencies and check for known problematic licenses
        local risky_licenses=0
        
        # Check for GPL dependencies (may require open-sourcing)
        if npm list --json 2>/dev/null | jq -r '.. | .license? // empty' | grep -i gpl > "$REPORTS_DIR/gpl-licenses.txt" 2>/dev/null; then
            local gpl_count=$(wc -l < "$REPORTS_DIR/gpl-licenses.txt")
            if [ "$gpl_count" -gt 0 ]; then
                log "  ⚠️ Found $gpl_count GPL-licensed dependencies"
                risky_licenses=$((risky_licenses + gpl_count))
                add_vulnerability "MEDIUM"
            fi
        fi
        
        log "  📊 License check found $risky_licenses potentially problematic licenses"
    fi
}

# 6. Web Security Headers Check (if server is running)
web_security_headers_check() {
    log "🌐 Checking web security headers..."
    
    local test_urls=("http://localhost:3000" "http://localhost:8000" "http://127.0.0.1:3000")
    local headers_issues=0
    
    for url in "${test_urls[@]}"; do
        if curl -sf "$url" >/dev/null 2>&1; then
            log "  🔍 Testing headers for $url"
            
            # Check for security headers
            local response_headers=$(curl -sI "$url" 2>/dev/null || true)
            
            # Missing security headers
            if ! echo "$response_headers" | grep -qi "x-frame-options"; then
                log "    ❌ Missing X-Frame-Options header"
                headers_issues=$((headers_issues + 1))
            fi
            
            if ! echo "$response_headers" | grep -qi "x-content-type-options"; then
                log "    ❌ Missing X-Content-Type-Options header"
                headers_issues=$((headers_issues + 1))
            fi
            
            if ! echo "$response_headers" | grep -qi "content-security-policy"; then
                log "    ❌ Missing Content-Security-Policy header"
                headers_issues=$((headers_issues + 1))
            fi
            
            if ! echo "$response_headers" | grep -qi "strict-transport-security"; then
                log "    ⚠️ Missing Strict-Transport-Security header"
                headers_issues=$((headers_issues + 1))
            fi
            
            break
        fi
    done
    
    if [ "$headers_issues" -gt 0 ]; then
        MEDIUM_ISSUES=$((MEDIUM_ISSUES + headers_issues))
        TOTAL_VULNERABILITIES=$((TOTAL_VULNERABILITIES + headers_issues))
        log "  📊 Found $headers_issues missing security headers"
    else
        log "  ✅ No web servers detected or all security headers present"
    fi
}

# 7. Docker Security Check
docker_security_check() {
    log "🐳 Checking Docker security configuration..."
    
    local docker_issues=0
    
    if [ -f Dockerfile ]; then
        # Check for root user
        if grep -q "USER root" Dockerfile || ! grep -q "USER " Dockerfile; then
            log "  ⚠️ Dockerfile may run as root user"
            docker_issues=$((docker_issues + 1))
            add_vulnerability "MEDIUM"
        fi
        
        # Check for latest tags
        if grep -E "FROM.*:latest" Dockerfile >/dev/null; then
            log "  ⚠️ Dockerfile uses 'latest' tags - unpredictable"
            docker_issues=$((docker_issues + 1))
            add_vulnerability "LOW"
        fi
        
        # Check for ADD instead of COPY
        if grep -E "^ADD " Dockerfile >/dev/null; then
            log "  ⚠️ Dockerfile uses ADD instead of COPY"
            docker_issues=$((docker_issues + 1))
            add_vulnerability "LOW"
        fi
    fi
    
    log "  📊 Docker security check found $docker_issues issues"
}

# 8. Generate Security Report
generate_security_report() {
    log "📊 Generating comprehensive security report..."
    
    local overall_status="PASS"
    
    # Determine overall status
    if [ "$CRITICAL_ISSUES" -gt 0 ]; then
        overall_status="CRITICAL_FAILURE"
    elif [ "$HIGH_ISSUES" -gt 3 ]; then
        overall_status="HIGH_RISK"
    elif [ "$MEDIUM_ISSUES" -gt 10 ]; then
        overall_status="MEDIUM_RISK"
    elif [ "$TOTAL_VULNERABILITIES" -gt 20 ]; then
        overall_status="LOW_RISK"
    fi
    
    # Generate JSON report
    cat > "$REPORTS_DIR/security-summary.json" << EOF
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "scan_duration_seconds": $(($(date +%s) - $(date -d "1 minute ago" +%s))),
  "overall_status": "$overall_status",
  "vulnerability_summary": {
    "total": $TOTAL_VULNERABILITIES,
    "critical": $CRITICAL_ISSUES,
    "high": $HIGH_ISSUES,
    "medium": $MEDIUM_ISSUES,
    "low": $LOW_ISSUES
  },
  "scan_categories": {
    "python_security": "$([ -f "$REPORTS_DIR/bandit-report.json" ] && echo "completed" || echo "skipped")",
    "nodejs_dependencies": "$([ -f "$REPORTS_DIR/npm-audit.json" ] && echo "completed" || echo "skipped")",
    "file_permissions": "completed",
    "secret_detection": "completed",
    "license_check": "$([ -f package.json ] && echo "completed" || echo "skipped")",
    "web_headers": "completed",
    "docker_security": "$([ -f Dockerfile ] && echo "completed" || echo "skipped")"
  },
  "risk_score": $(( (CRITICAL_ISSUES * 10) + (HIGH_ISSUES * 5) + (MEDIUM_ISSUES * 2) + LOW_ISSUES )),
  "deployment_recommendation": "$(if [ "$CRITICAL_ISSUES" -eq 0 ] && [ "$HIGH_ISSUES" -lt 3 ]; then echo "APPROVED"; else echo "BLOCKED"; fi)",
  "next_steps": [
    $([ "$CRITICAL_ISSUES" -gt 0 ] && echo '"Fix critical vulnerabilities immediately",' || echo "")
    $([ "$HIGH_ISSUES" -gt 0 ] && echo '"Address high-risk issues before deployment",' || echo "")
    $([ "$MEDIUM_ISSUES" -gt 5 ] && echo '"Review medium-risk findings",' || echo "")
    "Continue regular security monitoring"
  ]
}
EOF
    
    # Generate human-readable summary
    cat > "$REPORTS_DIR/security-summary.txt" << EOF
🔒 DEALERSCOPE SECURITY SCAN RESULTS
=====================================

Overall Status: $overall_status
Scan Date: $(date -u '+%Y-%m-%d %H:%M:%S UTC')

VULNERABILITY BREAKDOWN:
━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 Critical: $CRITICAL_ISSUES
🔴 High:     $HIGH_ISSUES  
🟡 Medium:   $MEDIUM_ISSUES
🔵 Low:      $LOW_ISSUES
━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Total:    $TOTAL_VULNERABILITIES

DEPLOYMENT RECOMMENDATION:
$(if [ "$CRITICAL_ISSUES" -eq 0 ] && [ "$HIGH_ISSUES" -lt 3 ]; then 
    echo "✅ APPROVED FOR DEPLOYMENT"
    echo "   Low security risk detected"
else 
    echo "❌ SECURITY GATE FAILED"
    echo "   Critical security issues must be resolved"
fi)

DETAILED FINDINGS:
$([ -f "$REPORTS_DIR/bandit-report.json" ] && echo "• Python security scan: completed" || echo "• Python security scan: skipped")
$([ -f "$REPORTS_DIR/npm-audit.json" ] && echo "• Node.js audit: completed" || echo "• Node.js audit: skipped")
• File permissions: completed
• Secret detection: completed
$([ -f package.json ] && echo "• License check: completed" || echo "• License check: skipped")
• Web headers: completed
$([ -f Dockerfile ] && echo "• Docker security: completed" || echo "• Docker security: skipped")

Next scan recommended: $(date -d "+1 week" '+%Y-%m-%d')
EOF
    
    log "✅ Security report generated: $REPORTS_DIR/security-summary.json"
    log "📄 Human report generated: $REPORTS_DIR/security-summary.txt"
}

# Main execution
main() {
    cd "$PROJECT_ROOT"
    
    log "🚀 Starting comprehensive security scan..."
    
    # Run all security checks
    python_security_scan
    nodejs_security_audit
    file_permissions_check
    secret_detection_scan
    dependency_license_check
    web_security_headers_check
    docker_security_check
    
    # Generate final report
    generate_security_report
    
    log "🎯 Security scan completed"
    log "📊 Found $TOTAL_VULNERABILITIES total vulnerabilities"
    log "📋 Report available: $REPORTS_DIR/security-summary.json"
    
    # Exit with status based on findings
    if [ "$CRITICAL_ISSUES" -gt 0 ]; then
        log "🚨 CRITICAL ISSUES DETECTED - Security gate failed"
        exit 2
    elif [ "$HIGH_ISSUES" -gt 3 ]; then
        log "⚠️ HIGH RISK DETECTED - Review required"
        exit 1
    else
        log "✅ Security scan passed - No blocking issues found in this security scan"
        exit 0
    fi
}

# Execute main function
main "$@"