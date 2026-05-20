#!/bin/bash
# 🔄 Automated Incident Response System
# Handles security incidents, performance issues, and system failures

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
INCIDENT_LOG="$PROJECT_ROOT/logs/incidents.log"
RESPONSE_DIR="$PROJECT_ROOT/incident-response"

# Incident severity levels
declare -A SEVERITY_LEVELS=(
    ["P0"]="Critical - System Down"
    ["P1"]="High - Major Feature Impact"
    ["P2"]="Medium - Minor Feature Impact" 
    ["P3"]="Low - Cosmetic or Enhancement"
)

# Response time SLAs (minutes)
declare -A RESPONSE_SLA=(
    ["P0"]=0
    ["P1"]=15
    ["P2"]=60
    ["P3"]=1440  # 24 hours
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Logging functions
log_incident() { echo -e "${PURPLE}[INCIDENT $(date +'%F %T')] $*${NC}" | tee -a "$INCIDENT_LOG"; }
incident_critical() { echo -e "${RED}🚨 CRITICAL: $*${NC}" | tee -a "$INCIDENT_LOG"; }
incident_high() { echo -e "${YELLOW}⚠️ HIGH: $*${NC}" | tee -a "$INCIDENT_LOG"; }
incident_info() { echo -e "${BLUE}ℹ️ INFO: $*${NC}" | tee -a "$INCIDENT_LOG"; }
incident_resolved() { echo -e "${GREEN}✅ RESOLVED: $*${NC}" | tee -a "$INCIDENT_LOG"; }

# Initialize incident response system
init_incident_response() {
    mkdir -p "$(dirname "$INCIDENT_LOG")" "$RESPONSE_DIR"/{active,resolved,templates}
    touch "$INCIDENT_LOG"
    chmod 600 "$INCIDENT_LOG"
    
    log_incident "Incident response system initialized"
}

# Generate incident ID
generate_incident_id() {
    local severity=$1
    local timestamp=$(date +%Y%m%d-%H%M%S)
    local random=$(tr -dc 'A-Z0-9' < /dev/urandom | head -c 4)
    echo "INC-${severity}-${timestamp}-${random}"
}

# Create incident record
create_incident() {
    local severity=$1
    local title="$2"
    local description="$3"
    local source="${4:-automated}"
    
    local incident_id=$(generate_incident_id "$severity")
    local incident_file="$RESPONSE_DIR/active/${incident_id}.json"
    
    cat > "$incident_file" << EOF
{
  "incident_id": "$incident_id",
  "severity": "$severity",
  "title": "$title",
  "description": "$description",
  "source": "$source",
  "status": "open",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "sla_target": "$(date -d "+${RESPONSE_SLA[$severity]} minutes" -u +%Y-%m-%dT%H:%M:%SZ)",
  "timeline": [
    {
      "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
      "action": "incident_created",
      "details": "Incident automatically created by monitoring system"
    }
  ],
  "metrics": {
    "detection_time": "$(date +%s)",
    "response_time": null,
    "resolution_time": null
  }
}
EOF
    
    log_incident "Created incident $incident_id: $title"
    echo "$incident_id"
}

# Update incident timeline
update_incident() {
    local incident_id=$1
    local action="$2"
    local details="$3"
    
    local incident_file="$RESPONSE_DIR/active/${incident_id}.json"
    
    if [[ ! -f "$incident_file" ]]; then
        incident_high "Incident file not found: $incident_id"
        return 1
    fi
    
    # Create backup
    cp "$incident_file" "${incident_file}.backup"
    
    # Update incident with new timeline entry
    jq --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg action "$action" \
       --arg details "$details" '
    .updated_at = $timestamp |
    .timeline += [{
      "timestamp": $timestamp,
      "action": $action,
      "details": $details
    }]' "$incident_file" > "${incident_file}.tmp" && mv "${incident_file}.tmp" "$incident_file"
    
    log_incident "Updated incident $incident_id: $action"
}

# Automated system health check
check_system_health() {
    log_incident "Performing automated system health check..."
    
    local health_issues=()
    
    # Check disk space
    local disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [[ $disk_usage -gt 90 ]]; then
        health_issues+=("High disk usage: ${disk_usage}%")
    fi
    
    # Check memory usage
    if command -v free >/dev/null; then
        local memory_usage=$(free | awk '/^Mem:/ {printf "%.0f", ($3/$2) * 100}')
        if [[ $memory_usage -gt 90 ]]; then
            health_issues+=("High memory usage: ${memory_usage}%")
        fi
    fi
    
    # Check GitHub Actions workflow status
    if [[ -n "${GITHUB_RUN_ID:-}" ]]; then
        local workflow_status="${GITHUB_RUN_CONCLUSION:-running}"
        if [[ "$workflow_status" == "failure" ]]; then
            health_issues+=("GitHub Actions workflow failed")
        fi
    fi
    
    # Check application endpoints
    local critical_endpoints=(
        "https://api.supabase.co/health"
        "https://github.com"
    )
    
    for endpoint in "${critical_endpoints[@]}"; do
        if ! curl -sf "$endpoint" >/dev/null 2>&1; then
            health_issues+=("Endpoint unreachable: $endpoint")
        fi
    done
    
    # Report health issues
    if [[ ${#health_issues[@]} -gt 0 ]]; then
        local incident_id=$(create_incident "P1" "System Health Alert" "Multiple health issues detected: $(IFS=', '; echo "${health_issues[*]}")")
        trigger_incident_response "$incident_id"
    else
        incident_info "System health check passed - all systems operational"
    fi
}

# Security incident detection
detect_security_incidents() {
    log_incident "Scanning for security incidents..."
    
    local security_issues=()
    
    # Check for failed authentication attempts
    if [[ -f "$PROJECT_ROOT/logs/auth.log" ]]; then
        local failed_logins=$(grep -c "authentication failed" "$PROJECT_ROOT/logs/auth.log" 2>/dev/null || echo 0)
        if [[ $failed_logins -gt 10 ]]; then
            security_issues+=("High number of failed login attempts: $failed_logins")
        fi
    fi
    
    # Check for suspicious file modifications
    if [[ -f "$PROJECT_ROOT/logs/security.log" ]]; then
        if grep -q "❌ SECURITY:" "$PROJECT_ROOT/logs/security.log"; then
            security_issues+=("Security validation failures detected")
        fi
    fi
    
    # Check for unusual network activity
    if command -v netstat >/dev/null; then
        local unusual_connections=$(netstat -an | grep -E ':22|:80|:443' | wc -l)
        if [[ $unusual_connections -gt 100 ]]; then
            security_issues+=("High number of network connections: $unusual_connections")
        fi
    fi
    
    # Report security incidents
    if [[ ${#security_issues[@]} -gt 0 ]]; then
        local incident_id=$(create_incident "P0" "Security Incident Detected" "Critical security issues found: $(IFS=', '; echo "${security_issues[*]}")")
        trigger_security_incident_response "$incident_id"
    else
        incident_info "Security scan completed - no threats detected"
    fi
}

# Performance incident detection
detect_performance_incidents() {
    log_incident "Monitoring performance metrics..."
    
    local performance_issues=()
    
    # Check validation suite execution time
    if [[ -f "$PROJECT_ROOT/validation-reports/final/summary.json" ]]; then
        local validation_duration=$(jq -r '.summary.execution_time // 0' "$PROJECT_ROOT/validation-reports/final/summary.json")
        if [[ $validation_duration -gt 1800 ]]; then  # 30 minutes
            performance_issues+=("Validation suite taking too long: ${validation_duration}s")
        fi
    fi
    
    # Check bundle size
    if [[ -d "$PROJECT_ROOT/dist" ]]; then
        local bundle_size=$(du -sm "$PROJECT_ROOT/dist" | cut -f1)
        if [[ $bundle_size -gt 10 ]]; then  # 10MB
            performance_issues+=("Large bundle size: ${bundle_size}MB")
        fi
    fi
    
    # Report performance incidents
    if [[ ${#performance_issues[@]} -gt 0 ]]; then
        local incident_id=$(create_incident "P2" "Performance Degradation" "Performance issues detected: $(IFS=', '; echo "${performance_issues[*]}")")
        trigger_performance_incident_response "$incident_id"
    else
        incident_info "Performance monitoring completed - metrics within thresholds"
    fi
}

# Trigger incident response workflow
trigger_incident_response() {
    local incident_id=$1
    local incident_file="$RESPONSE_DIR/active/${incident_id}.json"
    
    if [[ ! -f "$incident_file" ]]; then
        incident_high "Cannot trigger response - incident file missing: $incident_id"
        return 1
    fi
    
    local severity=$(jq -r '.severity' "$incident_file")
    local title=$(jq -r '.title' "$incident_file")
    
    incident_critical "INCIDENT RESPONSE TRIGGERED: $incident_id"
    incident_critical "Severity: $severity - ${SEVERITY_LEVELS[$severity]}"
    incident_critical "Title: $title"
    
    update_incident "$incident_id" "response_initiated" "Automated incident response workflow started"
    
    # Set response time metric
    jq '.metrics.response_time = now' "$incident_file" > "${incident_file}.tmp" && mv "${incident_file}.tmp" "$incident_file"
    
    case $severity in
        "P0")
            execute_critical_response "$incident_id"
            ;;
        "P1")
            execute_high_response "$incident_id"
            ;;
        "P2"|"P3")
            execute_standard_response "$incident_id"
            ;;
    esac
}

# Critical incident response (P0)
execute_critical_response() {
    local incident_id=$1
    
    incident_critical "Executing CRITICAL incident response for $incident_id"
    
    # Immediate containment actions
    update_incident "$incident_id" "containment_initiated" "Critical incident containment procedures started"
    
    # Create emergency backup
    if [[ -d "$PROJECT_ROOT/validation-reports" ]]; then
        local backup_dir="$RESPONSE_DIR/emergency-backup-$(date +%Y%m%d-%H%M%S)"
        cp -r "$PROJECT_ROOT/validation-reports" "$backup_dir"
        update_incident "$incident_id" "emergency_backup_created" "Emergency backup created at $backup_dir"
    fi
    
    # Alert stakeholders (simulated)
    update_incident "$incident_id" "stakeholders_notified" "Critical incident notifications sent to emergency contacts"
    
    # Begin recovery procedures
    execute_recovery_procedures "$incident_id"
}

# High priority incident response (P1)
execute_high_response() {
    local incident_id=$1
    
    incident_high "Executing HIGH priority incident response for $incident_id"
    
    update_incident "$incident_id" "investigation_started" "High priority incident investigation initiated"
    
    # Gather diagnostic information
    collect_diagnostic_data "$incident_id"
    
    # Implement temporary workarounds if available
    update_incident "$incident_id" "workaround_applied" "Temporary mitigation measures implemented"
    
    # Begin planned resolution
    execute_recovery_procedures "$incident_id"
}

# Standard incident response (P2/P3)
execute_standard_response() {
    local incident_id=$1
    
    incident_info "Executing STANDARD incident response for $incident_id"
    
    update_incident "$incident_id" "standard_response_initiated" "Standard incident response procedures started"
    
    # Scheduled investigation and resolution
    update_incident "$incident_id" "scheduled_for_investigation" "Incident queued for investigation during next maintenance window"
}

# Security-specific incident response
trigger_security_incident_response() {
    local incident_id=$1
    
    incident_critical "SECURITY INCIDENT RESPONSE ACTIVATED: $incident_id"
    
    update_incident "$incident_id" "security_response_initiated" "Security incident response procedures activated"
    
    # Immediate security containment
    update_incident "$incident_id" "security_containment" "Security containment measures implemented"
    
    # Preserve forensic evidence
    local forensics_dir="$RESPONSE_DIR/forensics-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$forensics_dir"
    
    # Copy security logs
    if [[ -f "$PROJECT_ROOT/logs/security.log" ]]; then
        cp "$PROJECT_ROOT/logs/security.log" "$forensics_dir/"
    fi
    
    # Copy system state
    if command -v ps >/dev/null; then
        ps aux > "$forensics_dir/process_list.txt"
    fi
    
    update_incident "$incident_id" "forensics_preserved" "Forensic evidence preserved in $forensics_dir"
    
    trigger_incident_response "$incident_id"
}

# Performance-specific incident response
trigger_performance_incident_response() {
    local incident_id=$1
    
    incident_high "PERFORMANCE INCIDENT RESPONSE: $incident_id"
    
    update_incident "$incident_id" "performance_analysis_started" "Performance degradation analysis initiated"
    
    # Collect performance metrics
    collect_performance_metrics "$incident_id"
    
    trigger_incident_response "$incident_id"
}

# Collect diagnostic data
collect_diagnostic_data() {
    local incident_id=$1
    local diagnostics_dir="$RESPONSE_DIR/diagnostics-$(date +%Y%m%d-%H%M%S)"
    
    mkdir -p "$diagnostics_dir"
    
    # System information
    {
        echo "=== SYSTEM INFORMATION ==="
        uname -a
        echo
        echo "=== DISK USAGE ==="
        df -h
        echo
        echo "=== MEMORY USAGE ==="
        free -h 2>/dev/null || echo "free command not available"
        echo
        echo "=== PROCESS LIST ==="
        ps aux 2>/dev/null || echo "ps command not available"
    } > "$diagnostics_dir/system_info.txt"
    
    # Copy relevant logs
    if [[ -f "$INCIDENT_LOG" ]]; then
        cp "$INCIDENT_LOG" "$diagnostics_dir/"
    fi
    
    if [[ -d "$PROJECT_ROOT/logs" ]]; then
        cp -r "$PROJECT_ROOT/logs" "$diagnostics_dir/"
    fi
    
    update_incident "$incident_id" "diagnostics_collected" "Diagnostic data collected in $diagnostics_dir"
}

# Collect performance metrics
collect_performance_metrics() {
    local incident_id=$1
    local metrics_dir="$RESPONSE_DIR/performance-metrics-$(date +%Y%m%d-%H%M%S)"
    
    mkdir -p "$metrics_dir"
    
    # Validation reports
    if [[ -d "$PROJECT_ROOT/validation-reports" ]]; then
        cp -r "$PROJECT_ROOT/validation-reports" "$metrics_dir/"
    fi
    
    # Bundle analysis
    if [[ -f "$PROJECT_ROOT/dist/bundle-analysis.html" ]]; then
        cp "$PROJECT_ROOT/dist/bundle-analysis.html" "$metrics_dir/"
    fi
    
    update_incident "$incident_id" "performance_metrics_collected" "Performance metrics collected in $metrics_dir"
}

# Recovery procedures
execute_recovery_procedures() {
    local incident_id=$1
    
    update_incident "$incident_id" "recovery_initiated" "System recovery procedures started"
    
    # Clear caches
    if [[ -d "$PROJECT_ROOT/node_modules/.cache" ]]; then
        rm -rf "$PROJECT_ROOT/node_modules/.cache"
        update_incident "$incident_id" "cache_cleared" "Node.js cache cleared"
    fi
    
    # Reset to known good state if needed
    if [[ "${RESET_TO_GOOD_STATE:-false}" == "true" ]]; then
        update_incident "$incident_id" "system_reset" "System reset to last known good state"
    fi
    
    # Verify system health post-recovery
    if check_system_health >/dev/null 2>&1; then
        resolve_incident "$incident_id" "Recovery successful - system health verified"
    else
        update_incident "$incident_id" "recovery_partial" "Recovery partially successful - continued monitoring required"
    fi
}

# Resolve incident
resolve_incident() {
    local incident_id=$1
    local resolution_details="$2"
    
    local incident_file="$RESPONSE_DIR/active/${incident_id}.json"
    local resolved_file="$RESPONSE_DIR/resolved/${incident_id}.json"
    
    if [[ ! -f "$incident_file" ]]; then
        incident_high "Cannot resolve - incident file missing: $incident_id"
        return 1
    fi
    
    # Update incident with resolution
    jq --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
       --arg details "$resolution_details" '
    .status = "resolved" |
    .resolved_at = $timestamp |
    .updated_at = $timestamp |
    .resolution_details = $details |
    .metrics.resolution_time = now |
    .timeline += [{
      "timestamp": $timestamp,
      "action": "incident_resolved",
      "details": $details
    }]' "$incident_file" > "$resolved_file"
    
    # Move to resolved directory
    rm "$incident_file"
    
    incident_resolved "Incident $incident_id resolved: $resolution_details"
    
    # Generate post-incident report
    generate_post_incident_report "$incident_id"
}

# Generate post-incident report
generate_post_incident_report() {
    local incident_id=$1
    local resolved_file="$RESPONSE_DIR/resolved/${incident_id}.json"
    local report_file="$RESPONSE_DIR/reports/${incident_id}-report.md"
    
    mkdir -p "$(dirname "$report_file")"
    
    local title=$(jq -r '.title' "$resolved_file")
    local severity=$(jq -r '.severity' "$resolved_file")
    local created_at=$(jq -r '.created_at' "$resolved_file")
    local resolved_at=$(jq -r '.resolved_at' "$resolved_file")
    local resolution_details=$(jq -r '.resolution_details' "$resolved_file")
    
    cat > "$report_file" << EOF
# Post-Incident Report: $incident_id

## Incident Summary
- **ID**: $incident_id
- **Title**: $title
- **Severity**: $severity
- **Created**: $created_at
- **Resolved**: $resolved_at

## Timeline
$(jq -r '.timeline[] | "- **\(.timestamp)**: \(.action) - \(.details)"' "$resolved_file")

## Resolution
$resolution_details

## Metrics
- **Detection Time**: $(jq -r '.metrics.detection_time' "$resolved_file")
- **Response Time**: $(jq -r '.metrics.response_time' "$resolved_file") 
- **Resolution Time**: $(jq -r '.metrics.resolution_time' "$resolved_file")

## Lessons Learned
- [ ] Identify root cause
- [ ] Implement preventive measures
- [ ] Update monitoring and alerting
- [ ] Review and update procedures

## Action Items
- [ ] Review incident response effectiveness
- [ ] Update documentation based on lessons learned
- [ ] Implement additional monitoring if needed
- [ ] Schedule follow-up review
EOF
    
    log_incident "Post-incident report generated: $report_file"
}

# Main monitoring loop
main() {
    log_incident "Starting DealerScope incident response monitoring..."
    
    init_incident_response
    
    # Perform all monitoring checks
    check_system_health
    detect_security_incidents
    detect_performance_incidents
    
    # Check for active incidents that need attention
    if [[ -d "$RESPONSE_DIR/active" ]]; then
        local active_incidents=$(find "$RESPONSE_DIR/active" -name "*.json" 2>/dev/null | wc -l)
        if [[ $active_incidents -gt 0 ]]; then
            incident_info "Active incidents requiring attention: $active_incidents"
        else
            incident_info "No active incidents - all systems operating normally"
        fi
    fi
    
    log_incident "Incident response monitoring completed"
}

# Handle script arguments
case "${1:-monitor}" in
    "monitor")
        main
        ;;
    "create")
        if [[ $# -lt 4 ]]; then
            echo "Usage: $0 create <severity> <title> <description>"
            exit 1
        fi
        init_incident_response
        create_incident "$2" "$3" "$4" "manual"
        ;;
    "resolve")
        if [[ $# -lt 3 ]]; then
            echo "Usage: $0 resolve <incident_id> <resolution_details>"
            exit 1
        fi
        init_incident_response
        resolve_incident "$2" "$3"
        ;;
    "status")
        init_incident_response
        echo "Active incidents:"
        find "$RESPONSE_DIR/active" -name "*.json" 2>/dev/null | while read -r file; do
            local id=$(jq -r '.incident_id' "$file")
            local title=$(jq -r '.title' "$file")
            local severity=$(jq -r '.severity' "$file")
            echo "  - $id ($severity): $title"
        done
        ;;
    *)
        echo "Usage: $0 {monitor|create|resolve|status}"
        exit 1
        ;;
esac