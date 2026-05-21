# DealerScope Clean Baseline — 2026-05-20

Status: clean operating checkpoint, not a broad enterprise/V1 claim.

## Commit

- HEAD: `2dd8f5b ci: remove stale codespaces prebuild config`

## Verified Gates

- Git status: clean
- ESLint: 0 errors, 0 warnings
- Build: passed
- Targeted Vitest: passed (`ApiRouteContract`, `utils`)
- Targeted backend pytest: passed (`test_gates`, `test_fallback_score`, `test_route_contract_aliases`)
- Paperclip routing tests: previously passed on this cleanup path
- GitHub current HEAD checks:
  - Cursor Code Review: success
  - Deploy GOLD Validation Reports: success
  - Current-head non-success checks: none
- Railway latest deployment:
  - `211657ef-0d4b-4e85-8b47-ff2538d141d3` SUCCESS for `2dd8f5b`
- Live OpenAPI route contract:
  - `/api/outcomes/summary` present
  - `/api/outcomes` present
  - `/api/outcomes/{opportunity_id}` present
  - `/api/outcomes/bid` present
  - `/api/analytics/scraper-status` present
  - `/api/saved-searches` present
  - `/api/saved-searches/{search_id}` present
  - `/api/rover/debug` absent

## Noise Closed

- Removed stale `.devcontainer/devcontainer.json` Codespaces prebuild config.
- Cancelled stale in-progress/pending devcontainer runs from superseded commits.
- Historical cancelled runs remain historical only, not current product-gate blockers.

## Boundary

This checkpoint means the current DealerScope repo/deploy/control-plane surface is clean enough to move from cleanup into live product/data truth validation. It does not claim V1, full enterprise readiness, or complete market/pricing correctness.
