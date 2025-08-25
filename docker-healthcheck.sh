#!/bin/sh
# Production Health Check Script for Docker
# Comprehensive health validation for containerized deployment

set -e

# Health check configuration
HEALTH_URL="http://localhost:8080/healthz"
TIMEOUT=5
MAX_ATTEMPTS=3

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

check_nginx() {
    log "Checking Nginx process..."
    if ! pgrep nginx > /dev/null; then
        log "${RED}ERROR: Nginx process not running${NC}"
        return 1
    fi
    log "${GREEN}✓ Nginx process is running${NC}"
    return 0
}

check_files() {
    log "Checking application files..."
    if [ ! -f "/usr/share/nginx/html/index.html" ]; then
        log "${RED}ERROR: Application files not found${NC}"
        return 1
    fi
    log "${GREEN}✓ Application files exist${NC}"
    return 0
}

check_http_response() {
    log "Checking HTTP response..."
    local attempt=1
    
    while [ $attempt -le $MAX_ATTEMPTS ]; do
        if curl -f -s --connect-timeout $TIMEOUT "$HEALTH_URL" > /dev/null; then
            log "${GREEN}✓ HTTP health check passed${NC}"
            return 0
        fi
        
        log "${YELLOW}⚠ HTTP health check attempt $attempt failed${NC}"
        attempt=$((attempt + 1))
        sleep 1
    done
    
    log "${RED}ERROR: HTTP health check failed after $MAX_ATTEMPTS attempts${NC}"
    return 1
}

check_memory_usage() {
    log "Checking memory usage..."
    local mem_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    local mem_usage_int=$(echo "$mem_usage" | cut -d'.' -f1)
    
    if [ "$mem_usage_int" -gt 90 ]; then
        log "${RED}ERROR: High memory usage: ${mem_usage}%${NC}"
        return 1
    elif [ "$mem_usage_int" -gt 80 ]; then
        log "${YELLOW}⚠ Warning: Memory usage: ${mem_usage}%${NC}"
    else
        log "${GREEN}✓ Memory usage: ${mem_usage}%${NC}"
    fi
    return 0
}

check_disk_space() {
    log "Checking disk space..."
    local disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [ "$disk_usage" -gt 90 ]; then
        log "${RED}ERROR: High disk usage: ${disk_usage}%${NC}"
        return 1
    elif [ "$disk_usage" -gt 80 ]; then
        log "${YELLOW}⚠ Warning: Disk usage: ${disk_usage}%${NC}"
    else
        log "${GREEN}✓ Disk usage: ${disk_usage}%${NC}"
    fi
    return 0
}

# Main health check execution
main() {
    log "Starting comprehensive health check..."
    
    local exit_code=0
    
    # Run all health checks
    check_nginx || exit_code=1
    check_files || exit_code=1
    check_http_response || exit_code=1
    check_memory_usage || exit_code=1
    check_disk_space || exit_code=1
    
    if [ $exit_code -eq 0 ]; then
        log "${GREEN}✅ All health checks passed${NC}"
    else
        log "${RED}❌ Health check failed${NC}"
    fi
    
    exit $exit_code
}

# Execute main function
main "$@"