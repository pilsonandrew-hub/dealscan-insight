# Webhook Ingress Plan

## Current Routing (ACTIVE)

```
Apify Actor → Railway directly
POST https://dealscan-insight-production.up.railway.app/api/ingest/apify
```

Webhook secret: `sbEC0dNgb7Ohg3rDV` (validated in ingest.py)

This works. Every actor run pushes data directly to Railway on completion.

---

## Planned Routing (FUTURE)

```
Apify Actor → OpenClaw Gateway → Railway
POST http://<mac-ip>:18789/webhook/apify → forwards to Railway
```

**Why route through OpenClaw first?**
- Ja'various can inspect every payload before it hits the DB
- Log raw payloads for debugging scraper issues
- Apply pre-filter logic (block junk, flag anomalies) before ingest
- Trigger Telegram/Slack alerts from OpenClaw side rather than Railway side
- OpenClaw becomes the single alert control plane

---

## What Needs to Happen to Switch

1. **Configure OpenClaw webhook receiver**
   - Add webhook ingress config to `openclaw.json`
   - Point to a known path e.g. `/webhook/apify`
   - Set up forwarding rule to `https://dealscan-insight-production.up.railway.app/api/ingest/apify`

2. **Test with a live payload**
   - Trigger one Apify actor manually
   - Confirm OpenClaw receives + forwards correctly
   - Confirm Railway receives the forwarded payload

3. **Update Apify webhook URL**
   - Change all 7 actor webhooks from Railway URL → OpenClaw URL
   - parseforge task webhook ID: `PgG3HFoKmjPD1GZMf`

4. **Set Railway as fallback**
   - If OpenClaw is down (Mac offline), Apify can't reach Railway
   - Consider keeping Railway as a secondary direct webhook until OpenClaw routing is proven stable

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Mac goes offline | HIGH | Keep Railway direct URL as Apify fallback |
| OpenClaw misconfigured | MEDIUM | Test with single actor before switching all |
| Double-ingest if both URLs active | LOW | Dedup system handles it (canonical_id) |

---

## Current Status

**DO NOT SWITCH YET.** Direct Apify → Railway is working. 
Switch only after:
- [ ] OpenClaw webhook ingress config validated
- [ ] At least one successful end-to-end test
- [ ] Railway fallback confirmed
