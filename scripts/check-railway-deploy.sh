#!/bin/bash
# check-railway-deploy.sh — Poll Railway for latest deployment status
# Usage: ./scripts/check-railway-deploy.sh
# Times out after 3 minutes

RAILWAY_TOKEN="${RAILWAY_API_TOKEN:-c5bc110a-c58a-4e49-b181-bbfd6dd26992}"
SERVICE_ID="fbc5a039-4de7-468c-abb1-71dcdaf47f38"
ENVIRONMENT_ID="1a116d8c-86fd-47ed-8f50-b8b8b994d514"
TIMEOUT=180
START=$(date +%s)

echo "🚂 Checking Railway deploy status..."

while true; do
  RESULT=$(curl -s -X POST "https://backboard.railway.app/graphql/v2" \
    -H "Authorization: Bearer $RAILWAY_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"{ deployments(input: { serviceId: \\\"$SERVICE_ID\\\", environmentId: \\\"$ENVIRONMENT_ID\\\" }) { edges { node { id status createdAt } } } }\"}" \
    2>/dev/null)

  STATUS=$(echo "$RESULT" | python3 -c "
import json,sys
d=json.load(sys.stdin)
edges=d.get('data',{}).get('deployments',{}).get('edges',[])
if edges:
    node=edges[0]['node']
    print(node.get('status','UNKNOWN'), node.get('createdAt','')[:19], node.get('id','')[:8])
else:
    print('NO_DEPLOYMENTS')
" 2>/dev/null)

  DEPLOY_STATUS=$(echo "$STATUS" | awk '{print $1}')
  TIMESTAMP=$(echo "$STATUS" | awk '{print $2}')
  DEPLOY_ID=$(echo "$STATUS" | awk '{print $3}')

  case "$DEPLOY_STATUS" in
    SUCCESS)
      echo "✅ DEPLOYED — $TIMESTAMP (id: $DEPLOY_ID)"
      exit 0
      ;;
    FAILED|CRASHED|REMOVED)
      echo "❌ FAILED ($DEPLOY_STATUS) — $TIMESTAMP (id: $DEPLOY_ID)"
      exit 1
      ;;
    BUILDING|DEPLOYING|INITIALIZING|QUEUED)
      echo "⏳ $DEPLOY_STATUS — $TIMESTAMP (id: $DEPLOY_ID)"
      ;;
    *)
      echo "❓ $STATUS"
      ;;
  esac

  NOW=$(date +%s)
  ELAPSED=$((NOW - START))
  if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "⏰ Timed out after ${TIMEOUT}s — last status: $DEPLOY_STATUS"
    exit 2
  fi

  sleep 8
done
