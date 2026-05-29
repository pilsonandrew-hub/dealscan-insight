import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(__dirname, '../../..');

function readRepoFile(path: string) {
  return readFileSync(resolve(root, path), 'utf8');
}

describe('frontend/backend route contract', () => {
  it('uses canonical /api/outcomes routes from the frontend service', () => {
    const apiSource = readRepoFile('src/services/api.ts');

    expect(apiSource).toContain('`${API_BASE}/api/outcomes/summary`');
    expect(apiSource).toContain('`${API_BASE}/api/outcomes/${payload.opportunity_id}`');
    expect(apiSource).toContain('`${API_BASE}/api/outcomes`');
    expect(apiSource).toContain('`${API_BASE}/api/outcomes/bid`');
    expect(apiSource).toContain('`${API_BASE}/api/analytics/scraper-status`');
    expect(apiSource).not.toContain('`${API_BASE}/outcomes/summary`');
  });

  it('keeps Vercel rewrites aligned with product API surfaces', () => {
    const vercel = JSON.parse(readRepoFile('vercel.json'));
    const rewrites = vercel.rewrites.map((rewrite: { source: string; destination: string }) => rewrite);

    expect(rewrites).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ source: '/api/outcomes', destination: expect.stringMatching(/\/api\/outcomes|\/outcomes$/) }),
        expect.objectContaining({ source: '/api/outcomes/(.*)', destination: expect.stringMatching(/\/api\/outcomes\/\$1|\/outcomes\/\$1$/) }),
        expect.objectContaining({ source: '/api/analytics/(.*)', destination: expect.stringContaining('/api/analytics/$1') }),
        expect.objectContaining({ source: '/api/sniper/(.*)', destination: expect.stringContaining('/api/sniper/$1') }),
        expect.objectContaining({ source: '/api/saved-searches/(.*)', destination: expect.stringContaining('/api/saved-searches/$1') }),
        expect.objectContaining({ source: '/api/recon/(.*)', destination: expect.stringContaining('/api/recon/$1') }),
        expect.objectContaining({ source: '/api/sonar/(.*)', destination: expect.stringContaining('/api/sonar/$1') }),
      ])
    );
  });

  it('does not expose Rover debug as public OpenAPI or unauthenticated product surface', () => {
    const roverSource = readRepoFile('webapp/routers/rover.py');
    const roverEdgeDebug = readRepoFile('api/rover/debug.js');

    expect(roverSource).not.toContain('detail=f"DEBUG:');
    expect(roverSource).toContain('@router.get("/debug", tags=["rover"], include_in_schema=False)');
    expect(roverSource).toContain('X-Internal-Secret');
    expect(roverSource).toContain('raise HTTPException(status_code=404, detail="Not found")');
    expect(roverEdgeDebug).toContain("status(404)");
  });

  it('provides an edge adapter for scraper status while backend deploys are unavailable', () => {
    const scraperStatusEdge = readRepoFile('api/analytics/scraper-status.js');

    expect(scraperStatusEdge).toContain('/api/analytics/source-health');
    expect(scraperStatusEdge).toContain('Authentication required');
    expect(scraperStatusEdge).toContain('normalizeSourceHealth');
  });

  it('forces production browser API calls through same-origin rewrites', () => {
    const settingsSource = readRepoFile('src/config/settings.ts');

    expect(settingsSource).toContain("resolvedEnvironment !== 'production'");
    expect(settingsSource).toContain("baseUrl: shouldUseExplicitApiBase ? configuredApiBase : ''");
    expect(settingsSource).not.toContain("baseUrl: import.meta.env.VITE_API_URL || '/api'");
  });

});
