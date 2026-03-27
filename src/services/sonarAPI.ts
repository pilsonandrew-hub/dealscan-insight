// Sonar API — real Apify backend via /api/sonar/*

const API_BASE = import.meta.env.VITE_API_URL || "https://dealscan-insight-production.up.railway.app";

export interface SonarResult {
  id: string;
  photoUrl: string;
  year: number;
  make: string;
  model: string;
  trim: string;
  currentBid: number;
  timeRemaining: string;
  endsAt: string;
  location: string;
  condition: string;
  sourceName: string;
  sourceUrl: string;
  mileage: number | null | string;
  auctionSource: string;
  issuingAgency: string;
  titleStatus: string;
  isAsIs: boolean;
}

export interface SonarSearchParams {
  query: string;
  minPrice: number;
  maxPrice: number;
}

// Sources we scan, in order
export const SONAR_SOURCES = ['GovDeals', 'PublicSurplus', 'HiBid'] as const;
export type SonarSource = (typeof SONAR_SOURCES)[number];

export interface SonarBatch {
  source: SonarSource;
  results: SonarResult[];
  done: boolean;
}

// ─── Quality filter — exclude salvage/flood/damage/mechanical problems ──────

const BAD_TITLE_STATUSES = /^(salvage|rebuilt|flood|parts only|lemon law|certificate of origin only|bill of sale only)$/i;

const BAD_CONDITION_KEYWORDS = /frame damage|wont start|won't start|engine|transmission|flood|fire damage|hail|does not run|as-is mechanical|inoperable|no start|seized|blown/i;

export interface QualityFilterResult {
  clean: SonarResult[];
  excluded: number;
  excludedResults: SonarResult[];
}

export function filterQuality(results: SonarResult[]): QualityFilterResult {
  const clean: SonarResult[] = [];
  const excludedResults: SonarResult[] = [];
  let excluded = 0;
  for (const r of results) {
    if (BAD_TITLE_STATUSES.test(r.titleStatus) || BAD_CONDITION_KEYWORDS.test(r.condition)) {
      excluded++;
      excludedResults.push(r);
    } else {
      clean.push(r);
    }
  }
  return { clean, excluded, excludedResults };
}

// ─── Real API adapter ────────────────────────────────────────────────────────

const POLL_INTERVAL_MS = 3_000;
const MAX_POLL_MS = 90_000;

interface StatusResponse {
  status: 'running' | 'complete';
  results: SonarResult[];
  sources: Record<string, string>;
  timed_out?: boolean;
}

export function sonarSearchStreaming(
  params: SonarSearchParams,
  onBatch: (batch: SonarBatch) => void,
): Promise<void> {
  return new Promise(async (resolve, reject) => {
    try {
      // 1. Start search
      const startResp = await fetch(`${API_BASE}/api/sonar/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: params.query,
          min_price: params.minPrice,
          max_price: params.maxPrice,
        }),
      });

      if (!startResp.ok) {
        throw new Error(`Search start failed: ${startResp.status}`);
      }

      const { job_id } = await startResp.json();
      const seenIds = new Set<string>();
      const startTime = Date.now();

      // 2. Poll for results
      const poll = async () => {
        if (Date.now() - startTime > MAX_POLL_MS) {
          // Timeout — deliver whatever we have
          for (const source of SONAR_SOURCES) {
            onBatch({ source, results: [], done: true });
          }
          resolve();
          return;
        }

        try {
          const statusResp = await fetch(`${API_BASE}/api/sonar/status/${job_id}`);
          if (!statusResp.ok) {
            throw new Error(`Status poll failed: ${statusResp.status}`);
          }

          const data: StatusResponse = await statusResp.json();

          // Deliver new results grouped by source
          for (const source of SONAR_SOURCES) {
            const sourceStatus = data.sources[source] || 'scanning';
            const sourceResults = data.results.filter(
              (r) => r.sourceName === source || r.auctionSource === source,
            );
            const newResults = sourceResults.filter((r) => !seenIds.has(r.id));
            for (const r of newResults) seenIds.add(r.id);

            if (newResults.length > 0 || sourceStatus === 'done' || sourceStatus === 'error') {
              onBatch({
                source: source as SonarSource,
                results: newResults,
                done: sourceStatus === 'done' || sourceStatus === 'error',
              });
            }
          }

          if (data.status === 'complete') {
            resolve();
            return;
          }
        } catch (err) {
          // Swallow poll errors, keep trying
          console.warn('[Sonar] Poll error:', err);
        }

        setTimeout(poll, POLL_INTERVAL_MS);
      };

      // Start polling after initial delay
      setTimeout(poll, POLL_INTERVAL_MS);
    } catch (err) {
      reject(err);
    }
  });
}

// Keep legacy function for backwards compat
export async function sonarSearch(params: SonarSearchParams): Promise<SonarResult[]> {
  const all: SonarResult[] = [];
  await sonarSearchStreaming(params, (batch) => {
    all.push(...batch.results);
  });
  return all;
}
