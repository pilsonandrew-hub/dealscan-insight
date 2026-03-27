// Sonar API — mock service (backend not yet built)

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
}

export interface SonarSearchParams {
  query: string;
  minPrice: number;
  maxPrice: number;
}

const MOCK_RESULTS: SonarResult[] = [
  {
    id: 'snr-001',
    photoUrl: 'https://images.unsplash.com/photo-1560958089-b8a1929cea89?w=400&h=260&fit=crop',
    year: 2021, make: 'Tesla', model: 'Model 3', trim: 'Long Range',
    currentBid: 24_800, timeRemaining: '2h 14m', endsAt: new Date(Date.now() + 2 * 3600_000 + 14 * 60_000).toISOString(),
    location: 'Sacramento, CA', condition: 'Clean title, minor wear on driver seat',
    sourceName: 'GovDeals', sourceUrl: '#', mileage: 38_200,
  },
  {
    id: 'snr-002',
    photoUrl: 'https://images.unsplash.com/photo-1606611013016-969c19ba27a4?w=400&h=260&fit=crop',
    year: 2020, make: 'Toyota', model: 'Camry', trim: 'SE',
    currentBid: 16_500, timeRemaining: '5h 45m', endsAt: new Date(Date.now() + 5 * 3600_000 + 45 * 60_000).toISOString(),
    location: 'Phoenix, AZ', condition: 'One owner, no accidents reported',
    sourceName: 'PublicSurplus', sourceUrl: '#', mileage: 42_100,
  },
  {
    id: 'snr-003',
    photoUrl: 'https://images.unsplash.com/photo-1619767886558-efdc259cde1a?w=400&h=260&fit=crop',
    year: 2019, make: 'Honda', model: 'Civic', trim: 'EX',
    currentBid: 13_200, timeRemaining: '1d 3h', endsAt: new Date(Date.now() + 27 * 3600_000).toISOString(),
    location: 'Dallas, TX', condition: 'Fleet vehicle, well maintained, minor scratches',
    sourceName: 'GSA Auctions', sourceUrl: '#', mileage: 55_800,
  },
  {
    id: 'snr-004',
    photoUrl: 'https://images.unsplash.com/photo-1609521263047-f8f205293f24?w=400&h=260&fit=crop',
    year: 2022, make: 'Ford', model: 'F-150', trim: 'XLT',
    currentBid: 31_400, timeRemaining: '8h 20m', endsAt: new Date(Date.now() + 8 * 3600_000 + 20 * 60_000).toISOString(),
    location: 'Atlanta, GA', condition: 'Clean title, bed liner installed, tow package',
    sourceName: 'GovDeals', sourceUrl: '#', mileage: 29_400,
  },
  {
    id: 'snr-005',
    photoUrl: 'https://images.unsplash.com/photo-1580273916550-e323be2ae537?w=400&h=260&fit=crop',
    year: 2020, make: 'BMW', model: '3 Series', trim: '330i',
    currentBid: 27_900, timeRemaining: '3h 10m', endsAt: new Date(Date.now() + 3 * 3600_000 + 10 * 60_000).toISOString(),
    location: 'Miami, FL', condition: 'Lease return, cosmetic wear on bumper',
    sourceName: 'Treasury Dept', sourceUrl: '#', mileage: 34_600,
  },
  {
    id: 'snr-006',
    photoUrl: 'https://images.unsplash.com/photo-1617814076367-b759c7d7e738?w=400&h=260&fit=crop',
    year: 2021, make: 'Chevrolet', model: 'Equinox', trim: 'LT',
    currentBid: 18_200, timeRemaining: '12h 5m', endsAt: new Date(Date.now() + 12 * 3600_000 + 5 * 60_000).toISOString(),
    location: 'Denver, CO', condition: 'Government fleet, regular maintenance records',
    sourceName: 'PublicSurplus', sourceUrl: '#', mileage: 47_300,
  },
  {
    id: 'snr-007',
    photoUrl: 'https://images.unsplash.com/photo-1552519507-da3b142c6e3d?w=400&h=260&fit=crop',
    year: 2018, make: 'Mazda', model: 'CX-5', trim: 'Touring',
    currentBid: 15_700, timeRemaining: '6h 30m', endsAt: new Date(Date.now() + 6 * 3600_000 + 30 * 60_000).toISOString(),
    location: 'Portland, OR', condition: 'Clean Carfax, all-wheel drive, new tires',
    sourceName: 'GSA Auctions', sourceUrl: '#', mileage: 61_200,
  },
];

export async function sonarSearch(params: SonarSearchParams): Promise<SonarResult[]> {
  // Simulate network delay
  await new Promise((resolve) => setTimeout(resolve, 3000));

  const q = params.query.toLowerCase();
  return MOCK_RESULTS.filter((r) => {
    const text = `${r.year} ${r.make} ${r.model} ${r.trim}`.toLowerCase();
    const matchesQuery = !q || text.includes(q) || q.split(' ').some((w) => text.includes(w));
    const matchesPrice = r.currentBid >= params.minPrice && r.currentBid <= params.maxPrice;
    return matchesQuery && matchesPrice;
  });
}
