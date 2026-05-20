const BACKEND_BASE_URL = 'https://dealscan-insight-production.up.railway.app';

function normalizeSourceHealth(sourceHealth) {
  const sources = Array.isArray(sourceHealth?.sources) ? sourceHealth.sources : [];
  return sources.map((row) => ({
    source: row.source_site || row.actor_name || row.name || 'unknown',
    name: row.source_site || row.actor_name || row.name || 'unknown',
    last_run: row.latest_webhook_at || row.latest_opportunity_at || null,
    finished_at: row.latest_webhook_at || row.latest_opportunity_at || null,
    succeeded: row.health === 'green' || row.health === 'yellow',
    status: row.health === 'red' ? 'FAILED' : 'SUCCEEDED',
    count: row.latest_saved_items ?? row.fresh_opportunities_7d ?? row.total_opportunities ?? 0,
  })).filter((row) => row.source && row.last_run);
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    res.setHeader('Allow', 'GET');
    return res.status(405).json({ detail: 'Method Not Allowed' });
  }

  const authorization = req.headers.authorization || '';
  if (!authorization.startsWith('Bearer ')) {
    return res.status(401).json({ detail: 'Authentication required' });
  }

  const upstream = await fetch(`${BACKEND_BASE_URL}/api/analytics/source-health`, {
    headers: { Authorization: authorization },
  });

  const body = await upstream.json().catch(() => null);
  if (!upstream.ok) {
    return res.status(upstream.status).json(body || { detail: 'Source health fetch failed' });
  }

  const items = normalizeSourceHealth(body);
  return res.status(200).json({
    generated_at: body?.generated_at || new Date().toISOString(),
    items,
    data: items,
    notes: {
      purpose: 'Vercel edge compatibility adapter for scraper green-dot status while Railway backend deploy is paused',
      upstream: '/api/analytics/source-health',
    },
  });
}
