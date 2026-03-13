# Browser Recon Skills

## Skills Added

### browser-recon
**Path:** `~/.openclaw/skills/browser-recon/SKILL.md`

Use OpenClaw browser to capture network requests from GovDeals and GSAauctions SPAs.

- Target: https://www.govdeals.com/en/all-terrain-vehicles
- Backend API: maestro.lqdt1.com
- Key finding: API returns 401 (auth required), token is per-session
- Goal: intercept JWT/Bearer token, capture search endpoint URL

### firecrawl
**Path:** `~/.openclaw/skills/firecrawl/SKILL.md`

Anti-bot JS-heavy page extraction layer via Firecrawl.

- Use for: Manheim spec pages, auction detail pages blocked by Cloudflare
- API endpoint: https://api.firecrawl.dev/v1/scrape
- Requires: `FIRECRAWL_API_KEY` env var (free key at firecrawl.dev)
- Add to Railway env vars when ready

## Recon Script

**Path:** `~/.openclaw/workspace/scripts/browser-recon-govdeals.sh`

Guides manual browser recon workflow for GovDeals reverse engineering.

## Browser Profile

Added `dealerscope-recon` profile to `~/.openclaw/openclaw.json` under `tools.browser.profiles`:
- headless: true, captureNetwork: true
- filterHosts: maestro.lqdt1.com, gsaauctions.gov
- waitAfterLoad: 5000ms

## Output Target

Findings should be saved to: `apify/actors/ds-govdeals/REVERSE_ENGINEER.md`
