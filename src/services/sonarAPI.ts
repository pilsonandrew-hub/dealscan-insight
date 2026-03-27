// Sonar API — adapter pattern for future backend swap

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
  mileage: number;
  auctionSource: string;
  issuingAgency: string;
  titleStatus: 'Clean' | 'Salvage' | 'Rebuilt';
  isAsIs: boolean;
}

export interface SonarSearchParams {
  query: string;
  minPrice: number;
  maxPrice: number;
}

// Sources we scan, in order
export const SONAR_SOURCES = ['GovDeals', 'PublicSurplus', 'GSA Auctions', 'HiBid', 'Treasury Dept'] as const;
export type SonarSource = (typeof SONAR_SOURCES)[number];

export interface SonarBatch {
  source: SonarSource;
  results: SonarResult[];
  done: boolean;
}

const MOCK_RESULTS: SonarResult[] = [
  {
    id: 'snr-001',
    photoUrl: 'https://images.unsplash.com/photo-1560958089-b8a1929cea89?w=400&h=260&fit=crop',
    year: 2021, make: 'Tesla', model: 'Model 3', trim: 'Long Range',
    currentBid: 24_800, timeRemaining: '2h 14m', endsAt: new Date(Date.now() + 2 * 3600_000 + 14 * 60_000).toISOString(),
    location: 'Sacramento, CA', condition: 'Minor wear on driver seat, all electronics functional',
    sourceName: 'GovDeals', sourceUrl: '#', mileage: 38_200,
    auctionSource: 'GovDeals', issuingAgency: 'CA Dept. of General Services', titleStatus: 'Clean', isAsIs: true,
  },
  {
    id: 'snr-002',
    photoUrl: 'https://images.unsplash.com/photo-1606611013016-969c19ba27a4?w=400&h=260&fit=crop',
    year: 2020, make: 'Toyota', model: 'Camry', trim: 'SE',
    currentBid: 16_500, timeRemaining: '5h 45m', endsAt: new Date(Date.now() + 5 * 3600_000 + 45 * 60_000).toISOString(),
    location: 'Phoenix, AZ', condition: 'One owner, no accidents reported',
    sourceName: 'PublicSurplus', sourceUrl: '#', mileage: 42_100,
    auctionSource: 'PublicSurplus', issuingAgency: 'City of Phoenix Fleet Mgmt', titleStatus: 'Clean', isAsIs: true,
  },
  {
    id: 'snr-003',
    photoUrl: 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=400&h=260&fit=crop',
    year: 2019, make: 'Honda', model: 'Civic', trim: 'EX',
    currentBid: 13_200, timeRemaining: '1d 3h', endsAt: new Date(Date.now() + 27 * 3600_000).toISOString(),
    location: 'Dallas, TX', condition: 'Fleet vehicle, well maintained, minor scratches',
    sourceName: 'GSA Auctions', sourceUrl: '#', mileage: 55_800,
    auctionSource: 'GSA Auctions', issuingAgency: 'U.S. General Services Administration', titleStatus: 'Clean', isAsIs: true,
  },
  {
    id: 'snr-004',
    photoUrl: 'https://images.unsplash.com/photo-1609521263047-f8f205293f24?w=400&h=260&fit=crop',
    year: 2022, make: 'Ford', model: 'F-150', trim: 'XLT',
    currentBid: 31_400, timeRemaining: '8h 20m', endsAt: new Date(Date.now() + 8 * 3600_000 + 20 * 60_000).toISOString(),
    location: 'Atlanta, GA', condition: 'Bed liner installed, tow package, minor hail damage on hood',
    sourceName: 'GovDeals', sourceUrl: '#', mileage: 29_400,
    auctionSource: 'GovDeals', issuingAgency: 'GA Dept. of Administrative Services', titleStatus: 'Clean', isAsIs: true,
  },
  {
    id: 'snr-005',
    photoUrl: 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=400&h=260&fit=crop',
    year: 2020, make: 'BMW', model: '3 Series', trim: '330i',
    currentBid: 27_900, timeRemaining: '3h 10m', endsAt: new Date(Date.now() + 3 * 3600_000 + 10 * 60_000).toISOString(),
    location: 'Miami, FL', condition: 'Lease return, cosmetic wear on bumper',
    sourceName: 'HiBid', sourceUrl: '#', mileage: 34_600,
    auctionSource: 'HiBid', issuingAgency: 'U.S. Treasury Dept. — Seized Assets', titleStatus: 'Rebuilt', isAsIs: true,
  },
  {
    id: 'snr-006',
    photoUrl: 'https://images.unsplash.com/photo-1617814076367-b759c7d7e738?w=400&h=260&fit=crop',
    year: 2021, make: 'Chevrolet', model: 'Equinox', trim: 'LT',
    currentBid: 18_200, timeRemaining: '12h 5m', endsAt: new Date(Date.now() + 12 * 3600_000 + 5 * 60_000).toISOString(),
    location: 'Denver, CO', condition: 'Government fleet, regular maintenance records',
    sourceName: 'PublicSurplus', sourceUrl: '#', mileage: 47_300,
    auctionSource: 'PublicSurplus', issuingAgency: 'CO Dept. of Personnel & Admin', titleStatus: 'Clean', isAsIs: true,
  },
  {
    id: 'snr-007',
    photoUrl: 'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=400&h=260&fit=crop',
    year: 2018, make: 'Mazda', model: 'CX-5', trim: 'Touring',
    currentBid: 15_700, timeRemaining: '6h 30m', endsAt: new Date(Date.now() + 6 * 3600_000 + 30 * 60_000).toISOString(),
    location: 'Portland, OR', condition: 'All-wheel drive, new tires, rear bumper repainted',
    sourceName: 'GSA Auctions', sourceUrl: '#', mileage: 61_200,
    auctionSource: 'GSA Auctions', issuingAgency: 'U.S. General Services Administration', titleStatus: 'Salvage', isAsIs: true,
  },
];

// ─── Adapter pattern ────────────────────────────────────────────────────────

interface SonarAdapter {
  search(params: SonarSearchParams, onBatch: (batch: SonarBatch) => void): Promise<void>;
}

function filterResults(results: SonarResult[], params: SonarSearchParams): SonarResult[] {
  const q = params.query.toLowerCase();
  return results.filter((r) => {
    const text = `${r.year} ${r.make} ${r.model} ${r.trim}`.toLowerCase();
    const matchesQuery = !q || text.includes(q) || q.split(' ').some((w) => text.includes(w));
    const matchesPrice = r.currentBid >= params.minPrice && r.currentBid <= params.maxPrice;
    return matchesQuery && matchesPrice;
  });
}

const mockAdapter: SonarAdapter = {
  async search(params, onBatch) {
    // Group mock data by source
    const bySource = new Map<SonarSource, SonarResult[]>();
    for (const source of SONAR_SOURCES) {
      bySource.set(source, []);
    }
    for (const r of MOCK_RESULTS) {
      const bucket = bySource.get(r.auctionSource as SonarSource);
      if (bucket) bucket.push(r);
    }

    // Deliver results in staggered batches per source
    for (const source of SONAR_SOURCES) {
      await new Promise((resolve) => setTimeout(resolve, 600 + Math.random() * 400));
      const sourceResults = bySource.get(source) ?? [];
      const filtered = filterResults(sourceResults, params);
      onBatch({ source, results: filtered, done: true });
    }
  },
};

// Future: swap in apifyAdapter here
// const apifyAdapter: SonarAdapter = { ... };

const activeAdapter: SonarAdapter = mockAdapter;

export function sonarSearchStreaming(
  params: SonarSearchParams,
  onBatch: (batch: SonarBatch) => void,
): Promise<void> {
  return activeAdapter.search(params, onBatch);
}

// Keep legacy function for backwards compat
export async function sonarSearch(params: SonarSearchParams): Promise<SonarResult[]> {
  const all: SonarResult[] = [];
  await sonarSearchStreaming(params, (batch) => {
    all.push(...batch.results);
  });
  return all;
}
