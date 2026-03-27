# HEARTBEAT.md

## DealerScope Deal Alerts
If you receive a system event containing "DEALERSCOPE_ALERT_CHECK":
Run: bash /Users/andrewpilson/.openclaw/workspace/scripts/deal-alerts.sh
This checks Supabase for DOS >= 80 deals not yet alerted and sends Telegram messages.
Report results back if any alerts fired.

## DealerScope Status (updated 2026-03-25 20:51 PT)

### ✅ System State — HEALTHY
- Scrapers running on 3hr cycle, all healthy
- 8-model security audit done — all critical fixes shipped
- 2-lane tier system (Premium/Standard) fully live
- DB migration applied to Supabase prod
- Frontend: lane badges + filter toggle + velocity cap warning (7/10 yellow, 10/10 amber)
- Scoring: 80% bid ceiling for Standard (was 88%), $1500/$2500 min margins, age/mileage hard stops
- Gross margin calc all-in (buyer premium + auction fees)
- DOS model score independent from segment score
- AI hot-deal validation using correct mmr_estimated field
- Apify env vars set for ds-jjkane + ds-allsurplus
- Rover watch event wired to real Supabase UUID (Andrew = ff8425cd)

### Open Items (Andrew must act)
_(none — claude auth confirmed active, Claude Max, pilson.andrew@gmail.com)_

### Medium Priority Backlog (agent can pick up)
1. ✅ Rover service key — already correctly implemented (anon for reads, service_role for writes only)
2. ✅ dealer_sales upsert — fixed 2026-03-27: user_id added to payload + outcome enum mapped (won→sold, lost→passed)
3. ✅ Telegram BUY/WATCH/PASS — already routes through /api/rover/actions backend API (not direct DB)
4. ✅ webapp/main.py — already deleted, backend/main.py is canonical entrypoint
5. ✅ AI confidence gate — already live: Premium >= 0.70, Standard >= 0.85 (score.py:741-744)
6. ⬜ Telegram BUY button — does not persist sale intent to dealer_sales (product gap, not a bug)

## RULE: Never go more than 15 minutes without an update to Andrew

## NotebookLM Integration
Export location: `/Users/andrewpilson/.openclaw/workspace/notebooklm-export/`
Upload these 7 files to NotebookLM after any major audit or architecture change:
- 01_MEMORY_architecture.md
- 02_GEMINI_AUDIT_*.md (latest audit)
- 03_AUDIT_PROMPT_methodology.md
- 04_ROADMAP_v5_security_compliance.md
- 05_SERVICE_INTEGRATION_audit.md
- 06_SELF_IMPROVEMENT_agents.md
- 07_HEARTBEAT_current_status.md

Re-export command: `python3 /Users/andrewpilson/.openclaw/workspace/scripts/notebooklm-export.py`

### NotebookLM Suggested Queries
- "What are the highest-risk open items in DealerScope right now?"
- "Generate an executive audio briefing on system status"
- "What business rules are most at risk of being violated?"
- "Summarize all open action items for Andrew"
