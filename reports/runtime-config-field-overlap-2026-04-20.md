# Runtime Config Field Overlap — 2026-04-20

## Files compared
- `src/config/settings.ts`
- `src/integrations/supabase/client.ts`
- `src/middleware/securityHeaders.ts`
- `src/utils/runtimeEnvironment.ts`

## Corrected evidence summary
The earlier wrapper-overlap problem was real, but that layer has now been removed.
What remains is not wrapper authority overlap. It is a smaller set of direct runtime seams.

| Category | settings.ts | supabase/client.ts | securityHeaders.ts | runtimeEnvironment.ts |
|---|---|---|---|---|
| environment detection/state | partial consumer | no | takes env as input in one path | yes, tiny utility only |
| API config | yes | no | no | no |
| database / Supabase config | partial | yes | derives allowed origins from Supabase URL when present | no |
| feature flags | yes | no | no | no |
| security config | partial | no | yes | no |
| performance / monitoring config | partial | no | no | only env helper for consumers |
| deployment metadata | env-derived values only | no | no | no |

---

## Field-level judgment

### 1. Environment detection/state
**Owner:** `src/utils/runtimeEnvironment.ts` for resolution only.

**Hard judgment:**
- this file is a utility, not a config authority
- it should resolve environment and stop there
- product/runtime ownership still belongs elsewhere

---

### 2. API base URL / request behavior
**Canonical owner:** `src/config/settings.ts`

**Why:**
- real app/services consume it directly
- no wrapper should be reintroduced here

---

### 3. Database / Supabase frontend config
**Current owner in live code:** split between `src/config/settings.ts` and `src/integrations/supabase/client.ts`

**Hard judgment:**
- this is still somewhat messy
- but it is now honest direct-code mess, not fake wrapper authority

**Action direction:**
- keep runtime truth centered on real frontend usage
- do not reintroduce wrapper ownership here

---

### 4. Feature flags
**Canonical owner:** `src/config/settings.ts`

**Reason:**
- wrapper-layer feature ownership was removed
- `runtimeEnvironment.ts` does not participate in feature ownership

---

### 5. Security config
**Canonical owner:** split between `src/config/settings.ts` and actual enforcement surfaces like `src/middleware/securityHeaders.ts`

**Reason:**
- this is enforcement logic, not wrapper ownership
- the real question here is alignment between settings and enforcement, not wrapper cleanup

---

### 6. Performance / monitoring config
**Current state:**
- broad fake wrapper ownership is gone
- some direct consumers still make small environment-based decisions

**Hard judgment:**
- this is no longer a wrapper-overlap problem
- it is normal local implementation detail unless drift starts again

---

### 7. Deployment metadata
**Best owner if needed:** env-sourced values in `src/config/settings.ts`

**Hard judgment:**
- no file should fabricate deployment truth
- env-derived only

---

## Current ranking after correction
1. `src/config/settings.ts` — primary product runtime authority
2. `src/utils/runtimeEnvironment.ts` — tiny environment-resolution utility only

## Hard conclusion
The earlier report overstated wrapper overlap because it lagged behind the live removals.
That stale analysis is now corrected.

The remaining problem is much narrower now:
- wrapper/config-sprawl was removed
- `runtimeEnvironment.ts` centralizes environment resolution only
- remaining cleanup questions are about direct runtime seams, not fake wrapper authority
