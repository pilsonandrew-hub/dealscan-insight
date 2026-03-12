#!/bin/bash
echo "=== DealerScope Bootstrap ==="
echo "--- Last 5 commits ---"
cd /Users/andrewpilson/.openclaw/workspace/projects/dealerscope && git log --oneline -5
echo ""
echo "--- Active Incidents ---"
cat /Users/andrewpilson/.openclaw/workspace/memory/dealerscope-incidents.md
echo ""
echo "--- Current Handoff ---"
cat /Users/andrewpilson/.openclaw/workspace/memory/dealerscope-handoffs.md
echo ""
echo "--- Railway Health ---"
curl -s https://dealscan-insight-production.up.railway.app/health
