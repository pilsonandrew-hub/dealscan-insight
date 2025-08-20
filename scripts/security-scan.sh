#!/bin/bash
set -euo pipefail

# DealerScope Security Scanner
# Automated security checks for production readiness

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

msg() { echo "[$(date +'%F %T')] $*"; }
warn() { echo "⚠️  WARNING: $*" >&2; }
error() { echo "❌ ERROR: $*" >&2; }
success() { echo "✅ $*"; }

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

main() {
    msg "🛡️  Starting DealerScope Security Scan"
    
    local issues=0
    
    # Check 1: Dependency vulnerabilities
    msg "📦 Scanning dependencies for vulnerabilities..."
    if command -v npm &> /dev/null; then
        if npm audit --audit-level=high --json > /tmp/audit.json 2>/dev/null; then
            local high_vulns=$(jq -r '.metadata.vulnerabilities.high // 0' /tmp/audit.json 2>/dev/null || echo "0")
            local critical_vulns=$(jq -r '.metadata.vulnerabilities.critical // 0' /tmp/audit.json 2>/dev/null || echo "0")
            
            if [ "$high_vulns" -gt 0 ] || [ "$critical_vulns" -gt 0 ]; then
                error "Found $critical_vulns critical and $high_vulns high severity vulnerabilities"
                issues=$((issues + 1))
            else
                success "No high/critical dependency vulnerabilities found"
            fi
        else
            warn "Could not run npm audit"
        fi
    fi
    
    # Check 2: Hardcoded secrets/keys patterns
    msg "🔍 Scanning for hardcoded secrets..."
    local secret_patterns=(
        "api[_-]?key"
        "secret[_-]?key"
        "password"
        "token"
        "private[_-]?key"
        "aws[_-]?access"
        "aws[_-]?secret"
        "bearer[[:space:]]+[a-zA-Z0-9]"
    )
    
    local secrets_found=0
    for pattern in "${secret_patterns[@]}"; do
        if grep -r -i "$pattern" "$PROJECT_ROOT/src" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" 2>/dev/null | grep -v "// SAFE:" | head -1 > /dev/null; then
            secrets_found=1
            break
        fi
    done
    
    if [ $secrets_found -eq 1 ]; then
        error "Potential hardcoded secrets detected"
        issues=$((issues + 1))
    else
        success "No hardcoded secrets detected"
    fi
    
    # Check 3: SQL injection patterns (in case of server-side code)
    msg "💉 Scanning for SQL injection vulnerabilities..."
    local sql_injection_patterns=(
        "query.*=.*input"
        "execute.*\+.*user"
        "SELECT.*\+.*req\."
        "INSERT.*\+.*params"
    )
    
    local sql_vulns=0
    for pattern in "${sql_injection_patterns[@]}"; do
        if grep -r -E "$pattern" "$PROJECT_ROOT/src" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" 2>/dev/null | head -1 > /dev/null; then
            sql_vulns=1
            break
        fi
    done
    
    if [ $sql_vulns -eq 1 ]; then
        error "Potential SQL injection vulnerabilities detected"
        issues=$((issues + 1))
    else
        success "No SQL injection patterns detected"
    fi
    
    # Check 4: XSS vulnerabilities
    msg "🌐 Scanning for XSS vulnerabilities..."
    if grep -r "dangerouslySetInnerHTML" "$PROJECT_ROOT/src" --include="*.tsx" --include="*.jsx" 2>/dev/null | head -1 > /dev/null; then
        warn "Found dangerouslySetInnerHTML usage - verify input sanitization"
        issues=$((issues + 1))
    else
        success "No dangerouslySetInnerHTML usage found"
    fi
    
    # Check 5: Environment variable exposure
    msg "🔧 Checking environment variable security..."
    if grep -r "console\.log.*process\.env" "$PROJECT_ROOT/src" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.jsx" 2>/dev/null | head -1 > /dev/null; then
        error "Environment variables logged to console"
        issues=$((issues + 1))
    else
        success "No environment variables exposed in console"
    fi
    
    # Check 6: File upload security
    msg "📁 Checking file upload security..."
    if [ -f "$PROJECT_ROOT/src/components/UploadInterface.tsx" ]; then
        if grep -q "file\.type" "$PROJECT_ROOT/src/components/UploadInterface.tsx" && \
           grep -q "file\.size" "$PROJECT_ROOT/src/components/UploadInterface.tsx"; then
            success "File upload validation implemented"
        else
            warn "File upload component may lack proper validation"
            issues=$((issues + 1))
        fi
    fi
    
    # Generate security report
    mkdir -p "$PROJECT_ROOT/security-reports"
    local report_file="$PROJECT_ROOT/security-reports/security-scan-$(date +%Y%m%d-%H%M%S).json"
    
    cat > "$report_file" <<EOF
{
  "scan_date": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "total_issues": $issues,
  "status": "$([ $issues -eq 0 ] && echo "PASS" || echo "FAIL")",
  "checks_performed": [
    "dependency_vulnerabilities",
    "hardcoded_secrets",
    "sql_injection",
    "xss_vulnerabilities",
    "environment_exposure",
    "file_upload_security"
  ],
  "recommendations": [
    "Enable pre-commit hooks",
    "Regular dependency updates",
    "Input validation on all user data",
    "Content Security Policy implementation",
    "Regular security audits"
  ]
}
EOF
    
    msg "📊 Security report saved to: $report_file"
    
    if [ $issues -eq 0 ]; then
        success "Security scan completed successfully - no critical issues found"
        return 0
    else
        error "Security scan found $issues issue(s) - review required"
        return 1
    fi
}

# Install pre-commit hooks if not already installed
install_hooks() {
    if command -v pre-commit &> /dev/null; then
        msg "Installing pre-commit hooks..."
        pre-commit install
        success "Pre-commit hooks installed"
    else
        warn "pre-commit not installed. Install with: pip install pre-commit"
    fi
}

# Parse command line arguments
case "${1:-scan}" in
    scan|--scan|-s)
        main
        ;;
    install|--install|-i)
        install_hooks
        ;;
    both|--both|-b)
        install_hooks
        main
        ;;
    --help|-h)
        echo "DealerScope Security Scanner"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  scan     Run security scan (default)"
        echo "  install  Install pre-commit hooks"
        echo "  both     Install hooks and run scan"
        echo "  --help   Show this help"
        ;;
    *)
        echo "Unknown command: $1"
        echo "Use --help for usage information"
        exit 1
        ;;
esac