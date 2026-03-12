#!/bin/bash
# DealerScope Code Agent — Auto-failover: Claude Code → Codex
# Usage: ./code-agent.sh /path/to/project "Your task prompt"

PROJECT_DIR="${1:-$(pwd)}"
PROMPT="${2:-}"
OPENAI_API_KEY="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"

export OPENAI_API_KEY

if [ -z "$PROMPT" ]; then
  echo "Usage: $0 <project_dir> <prompt>"
  exit 1
fi

echo "[code-agent] Trying Claude Code first..."
OUTPUT=$(cd "$PROJECT_DIR" && claude --permission-mode bypassPermissions --print "$PROMPT" 2>&1)
EXIT_CODE=$?

# Check for rate limit indicators
if echo "$OUTPUT" | grep -qiE "rate.limit|limit.*reset|you've hit your limit|too many requests|429"; then
  echo "[code-agent] ⚠️  Claude Code rate limited — switching to Codex..."
  cd "$PROJECT_DIR" && ~/.local/bin/codex exec --full-auto "$PROMPT"
else
  echo "$OUTPUT"
  exit $EXIT_CODE
fi
