#!/bin/bash
set -euo pipefail

# DealerScope AI Evaluation Runner
# Usage: ./scripts/run-evaluation.sh [options]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

msg() { echo "[$(date +'%F %T')] $*"; }

main() {
    msg "🚀 Starting DealerScope AI Evaluation Suite"
    
    # Check if Node.js is available
    if ! command -v node &> /dev/null; then
        echo "❌ Node.js is required but not installed."
        exit 1
    fi

    # Install dependencies if needed
    if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
        msg "📦 Installing dependencies..."
        cd "$PROJECT_ROOT"
        npm install
    fi

    # Create evaluation reports directory
    mkdir -p "$PROJECT_ROOT/evaluation-reports"

    # Run the evaluation suite
    cd "$PROJECT_ROOT"
    msg "🧪 Running evaluation suite..."
    
    if [ -f "$SCRIPT_DIR/ai-evaluation-suite.js" ]; then
        node "$SCRIPT_DIR/ai-evaluation-suite.js" "$@"
    else
        echo "❌ Evaluation suite not found at $SCRIPT_DIR/ai-evaluation-suite.js"
        exit 1
    fi

    msg "✅ Evaluation complete! Check ./evaluation-reports/ for results."
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            echo "DealerScope AI Evaluation Suite"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --help, -h     Show this help message"
            echo "  --verbose, -v  Enable verbose output"
            echo ""
            echo "This script evaluates the completeness and functionality"
            echo "of the DealerScope application across multiple dimensions."
            exit 0
            ;;
        --verbose|-v)
            set -x
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

main "$@"