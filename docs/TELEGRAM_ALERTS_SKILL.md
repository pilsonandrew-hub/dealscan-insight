# Telegram Alerts Skill + Alert Routing Decision

Created: 2026-03-12

## Artifacts

### `/Users/andrewpilson/.openclaw/skills/telegram-alerts/SKILL.md`
New skill covering:
- Bot token + chat ID
- Alert thresholds (DOS >= 80, max 5/run, 1/vehicle/6hrs)
- Kill switch: `ALERTS_ENABLED` env var in Railway
- Manual test alert curl command
- Inline keyboard buttons (Buy / Watch / Pass)
- Alert receipt model (`alert_log.telegram_message_id`)
- Delivery troubleshooting table

### `/Users/andrewpilson/.openclaw/skills/alert-verifier/SKILL.md`
Updated to include routing decision at the top.

### `/Users/andrewpilson/.openclaw/skills/firecrawl/SKILL.md`
Added `summarize` CLI note (v0.12.0, verified 2026-03-12) as lightweight alternative for URL content extraction.

### `/Users/andrewpilson/.openclaw/workspace/memory/dealerscope-decisions.md`
Appended alert routing decision.

## Alert Routing Decision

**FastAPI = sole deal alert control plane.**
OpenClaw Telegram = Andrew/Ja'various chat only.
Never route deal alerts through OpenClaw.

## Summarize CLI

`summarize --version` → `0.12.0` ✓

Useful for Manheim auction reports, industry PDFs, URL content extraction for research.
