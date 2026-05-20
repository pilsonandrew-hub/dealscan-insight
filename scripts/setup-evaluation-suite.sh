#!/bin/bash
set -euo pipefail

# DealerScope Evaluation Suite Setup
# Sets up the complete AI evaluation framework

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

msg() { echo "[$(date +'%F %T')] $*"; }

main() {
    msg "🚀 Setting up DealerScope AI Evaluation Suite"
    
    cd "$PROJECT_ROOT"
    
    # Make scripts executable
    msg "📝 Setting script permissions..."
    chmod +x "$SCRIPT_DIR"/*.sh 2>/dev/null || true
    chmod +x "$SCRIPT_DIR"/*.js 2>/dev/null || true
    
    # Add npm scripts
    if [ -f "$SCRIPT_DIR/package-script-helper.js" ]; then
        msg "📦 Adding evaluation scripts to package.json..."
        node "$SCRIPT_DIR/package-script-helper.js"
    fi
    
    # Install dependencies if needed
    if [ ! -d "node_modules" ] || [ ! -f "node_modules/.package-lock.json" ]; then
        msg "📦 Installing dependencies..."
        npm install
    fi
    
    # Create evaluation reports directory
    mkdir -p evaluation-reports
    
    # Verify evaluation suite files
    local files_needed=(
        "ai-evaluation-suite.js"
        "run-evaluation.sh" 
        "evaluation-config.json"
        "EVALUATION_README.md"
    )
    
    local missing_files=()
    for file in "${files_needed[@]}"; do
        if [ ! -f "$SCRIPT_DIR/$file" ]; then
            missing_files+=("$file")
        fi
    done
    
    if [ ${#missing_files[@]} -gt 0 ]; then
        msg "❌ Missing evaluation suite files:"
        printf '   %s\n' "${missing_files[@]}"
        exit 1
    fi
    
    msg "✅ Evaluation suite setup complete!"
    msg ""
    msg "🎯 Available commands:"
    msg "   npm run eval              # Run full evaluation suite"
    msg "   npm run eval:verbose      # Run with verbose output"  
    msg "   npm run eval:frontend     # Test frontend only"
    msg "   npm run eval:backend      # Test backend only"
    msg "   npm run eval:security     # Test security only"
    msg "   npm run eval:performance  # Test performance only"
    msg "   npm run eval:report       # Open latest HTML report"
    msg ""
    msg "📚 Documentation: scripts/EVALUATION_README.md"
    msg "⚙️  Configuration: scripts/evaluation-config.json"
    msg ""
    msg "🚀 Ready to evaluate! Run: npm run eval"
}

main "$@"