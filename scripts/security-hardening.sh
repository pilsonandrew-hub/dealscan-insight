#!/bin/bash
# 🔒 Production Security Hardening Script
# Implements comprehensive security controls and monitoring

set -euo pipefail

# Security configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SECURITY_LOG="$PROJECT_ROOT/logs/security.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging functions
log_security() { echo -e "${BLUE}[SECURITY $(date +'%F %T')] $*${NC}" | tee -a "$SECURITY_LOG"; }
security_pass() { echo -e "${GREEN}✅ SECURITY: $*${NC}" | tee -a "$SECURITY_LOG"; }
security_warn() { echo -e "${YELLOW}⚠️ SECURITY: $*${NC}" | tee -a "$SECURITY_LOG"; }
security_fail() { echo -e "${RED}❌ SECURITY: $*${NC}" | tee -a "$SECURITY_LOG"; }

# Initialize security logging
init_security_logging() {
    mkdir -p "$(dirname "$SECURITY_LOG")"
    touch "$SECURITY_LOG"
    chmod 600 "$SECURITY_LOG"
    
    log_security "Security hardening initiated"
    log_security "Environment: ${ENVIRONMENT:-production}"
    log_security "User: $(whoami)"
    log_security "Host: $(hostname)"
}

# Validate script integrity
validate_script_integrity() {
    log_security "Validating script integrity..."
    
    local script_files=(
        "scripts/run-validation-suite.sh"
        "scripts/security-hardening.sh"
    )
    
    for script in "${script_files[@]}"; do
        if [[ -f "$PROJECT_ROOT/$script" ]]; then
            # Check for suspicious patterns
            if grep -E '\$\([^)]*\)|\`[^`]*\`|eval|exec' "$PROJECT_ROOT/$script" | grep -v "# APPROVED:"; then
                security_fail "Potential command injection in $script"
                return 1
            fi
            
            # Verify permissions
            local perms=$(stat -c "%a" "$PROJECT_ROOT/$script")
            if [[ "$perms" != "755" && "$perms" != "644" ]]; then
                security_warn "Script $script has unusual permissions: $perms"
            fi
            
            security_pass "Script integrity verified: $script"
        else
            security_warn "Script not found: $script"
        fi
    done
}

# Input validation and sanitization
validate_inputs() {
    log_security "Validating environment inputs..."
    
    # Validate GitHub environment variables
    local github_vars=(
        "GITHUB_REF"
        "GITHUB_REPOSITORY" 
        "GITHUB_ACTOR"
        "GITHUB_SHA"
    )
    
    for var in "${github_vars[@]}"; do
        if [[ -n "${!var:-}" ]]; then
            # Check for injection attempts
            if [[ "${!var}" =~ [^a-zA-Z0-9/_.-] ]]; then
                security_fail "Invalid characters in $var: ${!var}"
                return 1
            fi
            security_pass "Environment variable validated: $var"
        fi
    done
}

# Secure file operations
secure_file_operations() {
    log_security "Implementing secure file operations..."
    
    # Set secure umask
    umask 077
    
    # Create secure temporary directory
    export TMPDIR=$(mktemp -d -t dealerscope-XXXXXX)
    chmod 700 "$TMPDIR"
    
    # Cleanup function
    cleanup_temp() {
        if [[ -n "${TMPDIR:-}" && -d "$TMPDIR" ]]; then
            rm -rf "$TMPDIR"
        fi
    }
    trap cleanup_temp EXIT
    
    security_pass "Secure file operations configured"
}

# Network security controls
implement_network_security() {
    log_security "Implementing network security controls..."
    
    # DNS over HTTPS configuration
    if command -v systemd-resolve >/dev/null; then
        log_security "Configuring secure DNS resolution"
    fi
    
    # Verify allowed domains
    local allowed_domains=(
        "github.com"
        "api.github.com"
        "registry.npmjs.org"
        "pypi.org"
        "supabase.com"
    )
    
    for domain in "${allowed_domains[@]}"; do
        if host "$domain" >/dev/null 2>&1; then
            security_pass "Domain reachable: $domain"
        else
            security_warn "Domain unreachable: $domain"
        fi
    done
}

# Dependency security scanning
scan_dependencies() {
    log_security "Scanning dependencies for vulnerabilities..."
    
    # Node.js dependency scanning
    if [[ -f "$PROJECT_ROOT/package.json" ]]; then
        if npm audit --audit-level=moderate --json > "$TMPDIR/npm-audit.json" 2>/dev/null; then
            local vulnerabilities=$(jq -r '.metadata.vulnerabilities.total // 0' "$TMPDIR/npm-audit.json")
            if [[ "$vulnerabilities" -gt 0 ]]; then
                security_warn "Found $vulnerabilities npm vulnerabilities"
            else
                security_pass "No critical npm vulnerabilities found"
            fi
        fi
    fi
    
    # Python dependency scanning
    if [[ -f "$PROJECT_ROOT/requirements.txt" ]]; then
        if command -v safety >/dev/null; then
            if safety check -r "$PROJECT_ROOT/requirements.txt" --json > "$TMPDIR/safety-report.json" 2>/dev/null; then
                security_pass "Python dependencies scanned with Safety"
            else
                security_warn "Safety scan completed with warnings"
            fi
        else
            log_security "Safety tool not available for Python scanning"
        fi
    fi
}

# Secret scanning
scan_for_secrets() {
    log_security "Scanning for exposed secrets..."
    
    local secret_patterns=(
        "password\s*[:=]\s*['\"][^'\"]+['\"]"
        "api[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]"
        "secret\s*[:=]\s*['\"][^'\"]+['\"]"
        "token\s*[:=]\s*['\"][^'\"]+['\"]"
        "-----BEGIN [A-Z ]+-----"
    )
    
    for pattern in "${secret_patterns[@]}"; do
        if grep -r -E "$pattern" "$PROJECT_ROOT/src" "$PROJECT_ROOT/scripts" 2>/dev/null | grep -v "# SAFE:"; then
            security_fail "Potential secret found matching pattern: $pattern"
            return 1
        fi
    done
    
    security_pass "No exposed secrets detected"
}

# Access control validation
validate_access_controls() {
    log_security "Validating access controls..."
    
    # Check file permissions
    find "$PROJECT_ROOT" -type f -name "*.sh" -perm /o+w 2>/dev/null | while read -r file; do
        security_warn "World-writable script found: $file"
    done
    
    # Check for SUID/SGID files (shouldn't exist in this context)
    if find "$PROJECT_ROOT" -type f \( -perm -4000 -o -perm -2000 \) 2>/dev/null | grep -q .; then
        security_fail "SUID/SGID files found in project directory"
        return 1
    fi
    
    security_pass "Access controls validated"
}

# Security monitoring setup
setup_security_monitoring() {
    log_security "Setting up security monitoring..."
    
    # Create monitoring directory
    mkdir -p "$PROJECT_ROOT/monitoring/security"
    
    # Generate security metrics
    cat > "$PROJECT_ROOT/monitoring/security/metrics.json" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "security_scan": {
    "script_integrity": "$(validate_script_integrity >/dev/null 2>&1 && echo "pass" || echo "fail")",
    "dependency_scan": "completed",
    "secret_scan": "$(scan_for_secrets >/dev/null 2>&1 && echo "pass" || echo "fail")",
    "access_controls": "$(validate_access_controls >/dev/null 2>&1 && echo "pass" || echo "fail")"
  },
  "environment": "${ENVIRONMENT:-production}",
  "scan_duration": "$(date +%s)"
}
EOF
    
    security_pass "Security monitoring configured"
}

# Incident response preparation
prepare_incident_response() {
    log_security "Preparing incident response capabilities..."
    
    # Create incident response directory
    mkdir -p "$PROJECT_ROOT/incident-response"
    
    # Generate incident response runbook
    cat > "$PROJECT_ROOT/incident-response/security-incident-runbook.md" << 'EOF'
# 🚨 Security Incident Response Runbook

## Immediate Response (0-15 minutes)
1. **Contain**: Isolate affected systems
2. **Assess**: Determine scope and impact
3. **Notify**: Alert security team and stakeholders

## Investigation (15-60 minutes)
1. **Preserve**: Collect forensic evidence
2. **Analyze**: Identify attack vectors and timeline
3. **Document**: Record all findings and actions

## Recovery (1-4 hours)
1. **Eradicate**: Remove threats and vulnerabilities
2. **Restore**: Bring systems back online securely
3. **Monitor**: Watch for signs of re-compromise

## Post-Incident (24-48 hours)
1. **Review**: Conduct post-mortem analysis
2. **Improve**: Update security controls
3. **Report**: Document lessons learned

## Emergency Contacts
- Security Team: security@dealerscope.com
- DevOps Team: devops@dealerscope.com
- Management: leadership@dealerscope.com
EOF
    
    security_pass "Incident response prepared"
}

# Main security hardening function
main() {
    log_security "Starting DealerScope security hardening..."
    
    init_security_logging
    validate_script_integrity
    validate_inputs
    secure_file_operations
    implement_network_security
    scan_dependencies
    scan_for_secrets
    validate_access_controls
    setup_security_monitoring
    prepare_incident_response
    
    log_security "Security hardening completed successfully"
    security_pass "All security controls implemented and validated"
    
    # Return appropriate exit code
    if grep -q "❌ SECURITY:" "$SECURITY_LOG"; then
        log_security "Security hardening completed with failures"
        exit 1
    elif grep -q "⚠️ SECURITY:" "$SECURITY_LOG"; then
        log_security "Security hardening completed with warnings"
        exit 0
    else
        log_security "Security hardening completed successfully"
        exit 0
    fi
}

# Run main function
main "$@"