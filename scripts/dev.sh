#!/bin/bash
set -euo pipefail

# DealerScope v4.9 Development Script
# Single-command setup and development environment with enhanced configuration

# Configurable settings - can be overridden via environment variables
DEFAULT_PORT=${VITE_PORT:-5173}
DEV_PORT=${DEV_PORT:-$DEFAULT_PORT}
STARTUP_TIMEOUT=${STARTUP_TIMEOUT:-60}
HEALTH_CHECK_INTERVAL=${HEALTH_CHECK_INTERVAL:-2}
LOG_LEVEL=${LOG_LEVEL:-INFO}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Enhanced logging functions with timestamps and levels
log_info() { 
    [[ "$LOG_LEVEL" =~ ^(DEBUG|INFO)$ ]] && echo -e "${BLUE}[INFO $(date +'%H:%M:%S')]${NC} $1" 
}
log_debug() { 
    [[ "$LOG_LEVEL" == "DEBUG" ]] && echo -e "${CYAN}[DEBUG $(date +'%H:%M:%S')]${NC} $1" 
}
log_success() { echo -e "${GREEN}[SUCCESS $(date +'%H:%M:%S')]${NC} $1" ; }
log_warning() { echo -e "${YELLOW}[WARNING $(date +'%H:%M:%S')]${NC} $1" ; }
log_error() { echo -e "${RED}[ERROR $(date +'%H:%M:%S')]${NC} $1" ; }

# Utility functions
is_port_available() {
    local port=$1
    ! nc -z localhost "$port" 2>/dev/null
}

wait_for_service() {
    local url=$1
    local timeout=${2:-$STARTUP_TIMEOUT}
    local interval=${3:-$HEALTH_CHECK_INTERVAL}
    local attempts=0
    local max_attempts=$((timeout / interval))
    
    log_info "Waiting for service at $url (timeout: ${timeout}s)"
    
    while [ $attempts -lt $max_attempts ]; do
        if curl -fsS --connect-timeout 5 --max-time 10 "$url" >/dev/null 2>&1; then
            log_success "Service is ready at $url"
            return 0
        fi
        
        attempts=$((attempts + 1))
        log_debug "Attempt $attempts/$max_attempts failed, retrying in ${interval}s..."
        sleep "$interval"
    done
    
    log_error "Service at $url failed to start within ${timeout}s"
    return 1
}

# Check if we're in the right directory
if [[ ! -f "package.json" ]]; then
    log_error "Please run this script from the project root directory"
    exit 1
fi

log_info "Starting DealerScope v4.9 development environment..."

# Check Node.js version
if ! command -v node &> /dev/null; then
    log_error "Node.js is required but not installed"
    exit 1
fi

NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [[ "$NODE_VERSION" -lt 18 ]]; then
    log_warning "Node.js 18+ recommended, found v$(node --version)"
fi

# Install dependencies if node_modules doesn't exist
if [[ ! -d "node_modules" ]]; then
    log_info "Installing dependencies..."
    npm install
    log_success "Dependencies installed"
else
    log_info "Dependencies already installed"
fi

# Check if .env exists
if [[ ! -f ".env" ]]; then
    log_warning "No .env file found. Creating from .env.example..."
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
        log_info "Please update .env with your actual values"
    else
        log_warning "No .env.example found. You may need to create .env manually"
    fi
fi

# Check if Supabase is configured
if [[ -f ".env" ]]; then
    if grep -q "VITE_SUPABASE_URL=" .env && grep -q "VITE_SUPABASE_ANON_KEY=" .env; then
        log_success "Supabase configuration found"
    else
        log_warning "Supabase configuration incomplete in .env"
        log_info "Please set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY"
    fi
fi

# Function to start the development server with enhanced monitoring
start_dev_server() {
    local server_url="http://localhost:$DEV_PORT"
    
    # Check if port is already in use
    if ! is_port_available "$DEV_PORT"; then
        log_warning "Port $DEV_PORT is already in use"
        read -p "Continue anyway? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Aborted by user"
            exit 0
        fi
    fi
    
    log_info "Starting development server on port $DEV_PORT..."
    
    # Start the development server
    npm run dev -- --port "$DEV_PORT" &
    DEV_SERVER_PID=$!
    
    # Enhanced cleanup function
    cleanup_dev_server() {
        if [ -n "${DEV_SERVER_PID:-}" ] && kill -0 "$DEV_SERVER_PID" 2>/dev/null; then
            log_info "Shutting down development server (PID: $DEV_SERVER_PID)..."
            kill "$DEV_SERVER_PID" 2>/dev/null || true
            
            # Give it time to shut down gracefully
            sleep 3
            
            # Force kill if still running
            if kill -0 "$DEV_SERVER_PID" 2>/dev/null; then
                log_warning "Force killing development server..."
                kill -9 "$DEV_SERVER_PID" 2>/dev/null || true
            fi
            
            log_success "Development server stopped"
        fi
    }
    
    # Set up cleanup trap
    trap cleanup_dev_server EXIT INT TERM
    
    # Wait for server to be ready with enhanced error handling
    if wait_for_service "$server_url" "$STARTUP_TIMEOUT" "$HEALTH_CHECK_INTERVAL"; then
        # Try to open browser
        if command -v open &> /dev/null; then
            log_info "Opening browser..."
            open "$server_url"
        elif command -v xdg-open &> /dev/null; then
            log_info "Opening browser..."
            xdg-open "$server_url"
        else
            log_info "Please open $server_url in your browser"
        fi
        
        log_success "Development server started successfully!"
        log_info "Server URL: $server_url"
        log_info "Press Ctrl+C to stop the server"
        
        # Monitor the server process
        while kill -0 "$DEV_SERVER_PID" 2>/dev/null; do
            sleep 5
            # Optional: Add health check here
            if ! curl -fsS --connect-timeout 2 --max-time 5 "$server_url" >/dev/null 2>&1; then
                log_warning "Development server appears unresponsive"
            fi
        done
    else
        log_error "Failed to start development server"
        cleanup_dev_server
        exit 1
    fi
}

# Function to run tests
run_tests() {
    log_info "Running test suite..."
    if [[ -f "vitest.config.ts" ]] || [[ -f "vite.config.ts" ]]; then
        npm test
    else
        log_warning "No test configuration found"
    fi
}

# Function to check health
health_check() {
    log_info "Performing health checks..."
    
    # Check TypeScript compilation
    if command -v tsc &> /dev/null; then
        log_info "Checking TypeScript compilation..."
        if tsc --noEmit; then
            log_success "TypeScript compilation passed"
        else
            log_error "TypeScript compilation failed"
            return 1
        fi
    fi
    
    # Check linting
    if [[ -f ".eslintrc.json" ]] || [[ -f "eslint.config.js" ]]; then
        log_info "Running linter..."
        if npm run lint --if-present; then
            log_success "Linting passed"
        else
            log_warning "Linting issues found"
        fi
    fi
    
    log_success "Health checks completed"
}

# Function to trigger a scraping job
trigger_scraping() {
    log_info "Triggering vehicle scraping job..."
    
    # This would call the Supabase Edge Function
    # For now, just show what would happen
    log_info "Would trigger scraping of GovDeals and PublicSurplus..."
    log_info "Check the app's scraper panel for real-time status"
    
    # In a real implementation, this would be:
    # curl -X POST "$SUPABASE_URL/functions/v1/vehicle-scraper" \
    #   -H "Authorization: Bearer $SUPABASE_ANON_KEY" \
    #   -H "Content-Type: application/json" \
    #   -d '{"action": "start_scraping", "sites": ["GovDeals", "PublicSurplus"]}'
}

# Main execution
case "${1:-dev}" in
    dev|start)
        health_check
        start_dev_server
        ;;
    test)
        run_tests
        ;;
    health)
        health_check
        ;;
    scrape)
        trigger_scraping
        ;;
    help)
        echo "DealerScope v4.9 Development Script"
        echo ""
        echo "Usage: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  dev, start    Start development server (default)"
        echo "  test          Run test suite"
        echo "  health        Run health checks"
        echo "  scrape        Trigger vehicle scraping job"
        echo "  help          Show this help"
        echo ""
        echo "Examples:"
        echo "  $0              # Start development server"
        echo "  $0 dev          # Start development server"
        echo "  $0 test         # Run tests"
        echo "  $0 health       # Check project health"
        ;;
    *)
        log_error "Unknown command: $1"
        echo "Run '$0 help' for usage information"
        exit 1
        ;;
esac