# Seller Recovery Audit Design

## Purpose

DealerScope now has live-confirmed run observability, lifecycle memory, and alert truth. The next product-truth step is to turn those surfaces into a seller-side operating view: which auction sources and listing patterns appear to leak value because the listing is incomplete, rejected by economic gates, or unsupported by enough structured evidence.

This is not a municipality SaaS build. It is the smallest internal proof surface that can support a future municipality/fleet-manager pilot without inventing facts.

## Scope

Build a read-only internal audit that returns sanitized aggregate diagnostics:

- Source-level daily run health from `source_health_daily`.
- Recent delivery and parse-event rejection/status counts.
- Recent active opportunity quality counts from stored opportunity rows.
- A short candidate list of listings that look recoverable because DealerScope can see a value gap and a concrete listing-quality deficiency.
- Explicit `unavailable` diagnostics for dimensions DealerScope cannot prove yet, such as photo-count quality or bidder-depth quality when those fields are absent.

Do not expose raw VINs, full listing URLs, descriptions, raw payloads, or seller-private details. The endpoint may expose internal opportunity ids and source names because this is an internal governed surface.

## API

Add an internal endpoint:

`GET /api/internal/seller-recovery-audit`

It uses the existing `X-Internal-Secret` guard from `webapp/routers/internal.py`.

The response shape is:

```json
{
  "generated_at": "2026-06-13T00:00:00+00:00",
  "status": "ok",
  "scope": "internal_seller_recovery_audit",
  "summary": {
    "source_count": 2,
    "candidate_count": 2,
    "unavailable_dimensions": ["bidder_depth", "photo_count"]
  },
  "source_health": [...],
  "listing_quality": {...},
  "value_leak_candidates": [...],
  "unsupported_dimensions": {...}
}
```

## Candidate Rules

A value-leak candidate must be evidence-backed:

- It is active.
- It has positive gross margin or positive bid headroom.
- It has at least one concrete deficiency:
  - missing VIN,
  - missing mileage,
  - missing auction end,
  - missing or unknown condition grade,
  - proxy pricing,
  - stored `risk_flags` includes `missing_photos`.

Candidate reasons must be deterministic strings. If a dimension is unavailable because no trustworthy field exists, the audit must say so rather than infer.

## Data Flow

`build_seller_recovery_audit()` reads:

- `source_health_daily` for source run aggregates.
- `ingest_delivery_log` for recent save/skip statuses.
- `parse_events` for recent parse/save/skip statuses.
- `opportunities` for active candidate rows.

The builder returns aggregate-only evidence and sanitized candidates. The API route only authenticates and calls the builder.

## Error Handling

The builder should degrade per section instead of failing the whole audit:

- If `source_health_daily` is missing or unreadable, set that section to `status="unavailable"` with a sanitized reason.
- If `parse_events` is missing or unreadable, keep opportunity-level candidates available.
- If `opportunities` is unreadable, the audit status becomes `degraded` because candidates cannot be computed.

## Verification

Test-first verification must prove:

- Missing internal secret is rejected.
- The audit returns source-health and candidate diagnostics from fake Supabase rows.
- Sensitive fields are not serialized.
- Unsupported dimensions are explicitly marked unavailable.
- Section read failures degrade honestly.
- The live inspection script can prove the endpoint with aggregate counts after deploy.

Completion requires local tests, full suite, PR/CI, deployment, and a live internal endpoint call or live inspection proof against production. Local tests alone are not enough.
