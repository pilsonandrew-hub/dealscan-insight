#!/bin/bash
set -euo pipefail

# DealerScope v4.9 Development Script
# Single-command setup and development environment

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1" ; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1" ; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1" ; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" ; }

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

# Function to start the development server
start_dev_server() {
    log_info "Starting development server..."
    npm run dev &
    DEV_SERVER_PID=$!
    
    # Wait for server to start
    sleep 3
    
    # Try to open browser
    if command -v open &> /dev/null; then
        open http://localhost:5173
    elif command -v xdg-open &> /dev/null; then
        xdg-open http://localhost:5173
    else
        log_info "Please open http://localhost:5173 in your browser"
    fi
    
    log_success "Development server started! Press Ctrl+C to stop."
    
    # Wait for the dev server process
    wait $DEV_SERVER_PID
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