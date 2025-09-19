import { DealItem } from "@/services/roverAPI";

// Utility functions for Rover system

export function formatCurrency(amount: number | undefined | null): string {
  if (amount == null || !Number.isFinite(amount)) return "—";
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount);
}

export function formatMileage(miles: number | undefined | null): string {
  if (miles == null || !Number.isFinite(miles)) return "—";
  return new Intl.NumberFormat('en-US').format(miles);
}

export function formatPercentage(value: number | undefined | null): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${Math.round(value)}%`;
}

export function formatVehicleTitle(item: Partial<DealItem>): string {
  const parts = [item.year, item.make, item.model].filter(Boolean);
  return parts.join(" ") || "Unknown Vehicle";
}

export function getVehicleDisplayInfo(item: DealItem) {
  return {
    title: formatVehicleTitle(item),
    price: formatCurrency(item.price),
    mileage: item.mileage ? `${formatMileage(item.mileage)} miles` : null,
    location: item.state || null,
    source: item.source || null,
    vin: item.vin || null
  };
}

export function calculateROIColor(roi: number | undefined | null): string {
  if (roi == null || !Number.isFinite(roi)) return "text-muted-foreground";
  
  if (roi >= 20) return "text-green-600";
  if (roi >= 10) return "text-green-500";
  if (roi >= 5) return "text-yellow-600";
  if (roi > 0) return "text-yellow-500";
  return "text-red-500";
}

export function getScoreColor(score: number | undefined | null): string {
  if (score == null || !Number.isFinite(score)) return "bg-gray-100";
  
  if (score >= 0.8) return "bg-green-100 text-green-800";
  if (score >= 0.6) return "bg-blue-100 text-blue-800";
  if (score >= 0.4) return "bg-yellow-100 text-yellow-800";
  if (score >= 0.2) return "bg-orange-100 text-orange-800";
  return "bg-red-100 text-red-800";
}

export function formatScore(score: number | undefined | null): string {
  if (score == null || !Number.isFinite(score)) return "—";
  
  // If score is between 0-1, convert to percentage
  if (score <= 1) {
    return `${Math.round(score * 100)}`;
  }
  
  // If score is already a percentage (>1), cap at 100
  return `${Math.min(100, Math.round(score))}`;
}

export function timeAgo(timestamp: number | string): string {
  const now = Date.now();
  const time = typeof timestamp === 'string' ? new Date(timestamp).getTime() : timestamp;
  const diff = now - time;
  
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  
  if (seconds < 60) return `${seconds}s ago`;
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 30) return `${days}d ago`;
  
  return new Date(time).toLocaleDateString();
}

export function formatDate(date: string | Date | undefined | null): string {
  if (!date) return "—";
  
  try {
    const d = new Date(date);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString();
  } catch {
    return "—";
  }
}

export function formatDateTime(date: string | Date | undefined | null): string {
  if (!date) return "—";
  
  try {
    const d = new Date(date);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString();
  } catch {
    return "—";
  }
}

export function getConfidenceLabel(confidence: number | undefined | null): string {
  if (confidence == null || !Number.isFinite(confidence)) return "Unknown";
  
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  
  if (pct >= 90) return "Very High";
  if (pct >= 70) return "High";
  if (pct >= 50) return "Medium";
  if (pct >= 30) return "Low";
  return "Very Low";
}

export function getConfidenceColor(confidence: number | undefined | null): string {
  if (confidence == null || !Number.isFinite(confidence)) return "text-muted-foreground";
  
  const pct = confidence <= 1 ? confidence * 100 : confidence;
  
  if (pct >= 90) return "text-green-600";
  if (pct >= 70) return "text-blue-600";
  if (pct >= 50) return "text-yellow-600";
  if (pct >= 30) return "text-orange-600";
  return "text-red-600";
}

export function isHighValue(item: DealItem): boolean {
  const roi = item.roi_percentage || 0;
  const score = item._score || 0;
  
  return roi >= 15 || score >= 0.7;
}

export function prioritizeDeals(deals: DealItem[]): DealItem[] {
  return [...deals].sort((a, b) => {
    // First, sort by score (if available)
    const scoreA = a._score || 0;
    const scoreB = b._score || 0;
    if (scoreA !== scoreB) return scoreB - scoreA;
    
    // Then by ROI
    const roiA = a.roi_percentage || 0;
    const roiB = b.roi_percentage || 0;
    if (roiA !== roiB) return roiB - roiA;
    
    // Finally by potential profit
    const profitA = a.potential_profit || 0;
    const profitB = b.potential_profit || 0;
    return profitB - profitA;
  });
}

export function filterDeals(deals: DealItem[], filters: {
  minROI?: number;
  maxPrice?: number;
  makes?: string[];
  states?: string[];
  minScore?: number;
}): DealItem[] {
  return deals.filter(deal => {
    if (filters.minROI && (deal.roi_percentage || 0) < filters.minROI) return false;
    if (filters.maxPrice && deal.price > filters.maxPrice) return false;
    if (filters.makes && filters.makes.length > 0 && !filters.makes.includes(deal.make)) return false;
    if (filters.states && filters.states.length > 0 && deal.state && !filters.states.includes(deal.state)) return false;
    if (filters.minScore && (deal._score || 0) < filters.minScore) return false;
    
    return true;
  });
}

export function generateDealSummary(deals: DealItem[]): {
  totalDeals: number;
  avgROI: number;
  avgScore: number;
  totalValue: number;
  topMakes: Array<{ make: string; count: number }>;
} {
  if (deals.length === 0) {
    return {
      totalDeals: 0,
      avgROI: 0,
      avgScore: 0,
      totalValue: 0,
      topMakes: []
    };
  }
  
  const roiValues = deals.map(d => d.roi_percentage || 0).filter(roi => roi > 0);
  const scoreValues = deals.map(d => d._score || 0).filter(score => score > 0);
  const totalValue = deals.reduce((sum, d) => sum + (d.price || 0), 0);
  
  // Count makes
  const makeCount = new Map<string, number>();
  deals.forEach(deal => {
    const count = makeCount.get(deal.make) || 0;
    makeCount.set(deal.make, count + 1);
  });
  
  const topMakes = Array.from(makeCount.entries())
    .map(([make, count]) => ({ make, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);
  
  return {
    totalDeals: deals.length,
    avgROI: roiValues.length > 0 ? roiValues.reduce((sum, roi) => sum + roi, 0) / roiValues.length : 0,
    avgScore: scoreValues.length > 0 ? scoreValues.reduce((sum, score) => sum + score, 0) / scoreValues.length : 0,
    totalValue,
    topMakes
  };
}

export function validateDealData(deal: any): deal is DealItem {
  return (
    deal &&
    typeof deal.id === 'string' &&
    typeof deal.make === 'string' &&
    typeof deal.model === 'string' &&
    typeof deal.year === 'number' &&
    typeof deal.price === 'number' &&
    deal.year >= 1900 &&
    deal.year <= new Date().getFullYear() + 2 &&
    deal.price > 0
  );
}

export function sanitizeDealData(deal: any): DealItem | null {
  if (!validateDealData(deal)) return null;
  
  return {
    id: deal.id,
    make: deal.make.trim(),
    model: deal.model.trim(),
    year: Math.round(deal.year),
    price: Math.round(deal.price),
    mileage: deal.mileage ? Math.max(0, Math.round(deal.mileage)) : undefined,
    bodyType: deal.bodyType?.trim(),
    source: deal.source?.trim(),
    sellerId: deal.sellerId?.trim(),
    mmr: deal.mmr ? Math.round(deal.mmr) : undefined,
    city: deal.city?.trim(),
    state: deal.state?.trim()?.toUpperCase(),
    vin: deal.vin?.trim()?.toUpperCase(),
    _score: deal._score ? Math.max(0, Math.min(1, deal._score)) : undefined,
    arbitrage_score: deal.arbitrage_score ? Math.round(deal.arbitrage_score) : undefined,
    roi_percentage: deal.roi_percentage ? Math.round(deal.roi_percentage * 100) / 100 : undefined,
    potential_profit: deal.potential_profit ? Math.round(deal.potential_profit) : undefined
  };
}