# Webhook Ingress Plan

## Current Routing (ACTIVE)

```
Apify Actor -> Railway directly
POST https://dealscan-insight-production.up.railway.app/api/ingest/apify
```

This remains the production webhook path. The Apify webhook URL does not change.

## Rejected Approach

### OpenClaw Gateway Routing: REJECTED

```
Apify Actor -> OpenClaw Gateway -> Railway
POST http://<mac-ip>:18789/webhook/apify
```

Reason:
- OpenClaw runs on Andrew's Mac, which can be offline, asleep, or rebooting.
- Apify requires a public internet endpoint; `127.0.0.1` and local-only ingress are not reachable from Apify.
- Routing production ingestion through a laptop creates a hard single point of failure.
- Railway already hosts the production webhook, so extra forwarding adds operational risk without adding durable observability.

## Implemented Approach

### Railway + Supabase `webhook_log`: IMPLEMENTED

The existing `/api/ingest/apify` handler now writes every raw webhook payload into Supabase at the top of the request flow, immediately after webhook secret validation succeeds.

Captured fields:
- `source`
- `actor_id`
- `run_id`
- `item_count`
- `raw_payload`
- `processing_status`
- `error_message`

Behavior:
- Raw payload is stored in `webhook_log` before dataset processing starts.
- Logging is non-fatal; webhook ingestion continues even if the audit insert fails.
- `processing_status` starts as `pending` and is finalized to `processed` or `error`.
- This provides payload inspection, run-level observability, and anomaly review without any new routing layer.

## Decision

OpenClaw ingress is not needed — Railway + Supabase provides full observability.
