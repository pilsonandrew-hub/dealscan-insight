# Runtime Config Field Overlap — 2026-04-20

## Reconciled surviving files in this surface
- `src/config/settings.ts`
- `src/integrations/supabase/client.ts`
- `src/middleware/securityHeaders.ts`
- `src/utils/runtimeEnvironment.ts`

## Corrected evidence summary
The earlier wrapper-overlap problem was real, but those wrapper layers were later removed.
This report now reflects the post-cleanup state rather than the intermediate narrowing phase.

| Category | settings.ts | supabase/client.ts | middleware/securityHeaders.ts | runtimeEnvironment.ts |
|---|---|---|---|---|
| environment detection/state | partial consumer/owner | no | may derive behavior from env-fed inputs | yes, resolution only |
| API config | yes | no | no | no |
| database / Supabase config | partial | yes | derives allowed origins from Supabase URL when present | no |
| feature flags | yes | no | no | no |
| security config | partial | no | yes | no |
| performance / monitoring config | partial | no | no | no |
| deployment metadata | env-derived only if present | no | no | no |

---

## Field-level judgment

### Environment detection/state
**Owner for resolution only:** `src/utils/runtimeEnvironment.ts`

**Hard judgment:**
- this file resolves environment and stops there
- it is not a config authority

### API base URL / request behavior
**Canonical owner:** `src/config/settings.ts`

### Database / Supabase frontend config
**Current direct-code split:**
- `src/config/settings.ts`
- `src/integrations/supabase/client.ts`
- `src/middleware/securityHeaders.ts` for env-derived allowed origins/connect sources

**Hard judgment:**
- still somewhat messy
- now honest direct-code seams, not fake wrapper overlap

### Feature flags
**Canonical owner:** `src/config/settings.ts`

### Security config
**Current real split:**
- `src/config/settings.ts`
- actual enforcement surface `src/middleware/securityHeaders.ts`

### Performance / monitoring config
**Hard judgment:**
- wrapper-level performance ownership is gone
- this is no longer a fake wrapper-overlap problem

### Deployment metadata
**Best owner if needed:** env-sourced values in `src/config/settings.ts`

## Current ranking after reconciliation
1. `src/config/settings.ts` — primary product/runtime authority
2. `src/utils/runtimeEnvironment.ts` — tiny utility only

## Hard conclusion
The earlier version of this report lagged behind later cleanup waves and therefore overstated what still overlapped.

The wrapper/config-sprawl problem is gone.
What remains is direct-code seam management, not fake config authority overlap.
