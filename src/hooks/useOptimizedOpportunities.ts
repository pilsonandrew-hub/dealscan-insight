/**
 * Optimized opportunities hook with advanced filtering, sorting, and performance optimizations
 */

import { useMemo, useCallback, useState, useEffect } from 'react';
import { Opportunity } from '@/types/dealerscope';

interface FilterCriteria {
  minProfit?: number;
  maxRisk?: number;
  states?: string[];
  makes?: string[];
  minROI?: number;
  maxMileage?: number;
  status?: string[];
}

interface SortCriteria {
  field: 'profit' | 'roi' | 'confidence' | 'score';
  direction: 'asc' | 'desc';
}

interface UseOptimizedOpportunitiesResult {
  filteredOpportunities: Opportunity[];
  topOpportunities: Opportunity[];
  highRiskOpportunities: Opportunity[];
  stats: {
    totalOpportunities: number;
    totalProfit: number;
    averageROI: number;
    averageConfidence: number;
  };
  filters: FilterCriteria;
  setFilters: (filters: FilterCriteria) => void;
  sorting: SortCriteria;
  setSorting: (sorting: SortCriteria) => void;
}

export function useOptimizedOpportunities(
  opportunities: Opportunity[]
): UseOptimizedOpportunitiesResult {
  const [filters, setFilters] = useState<FilterCriteria>({});
  const [sorting, setSorting] = useState<SortCriteria>({
    field: 'profit',
    direction: 'desc'
  });

  // Memoized filtering logic
  const filteredOpportunities = useMemo(() => {
    return opportunities
      .filter(opportunity => {
        if (filters.minProfit && opportunity.profit < filters.minProfit) return false;
        if (filters.maxRisk && opportunity.confidence < (100 - filters.maxRisk)) return false;
        if (filters.states?.length && !filters.states.includes(opportunity.state || '')) return false;
        if (filters.makes?.length && !filters.makes.includes(opportunity.vehicle.make)) return false;
        if (filters.minROI && opportunity.roi < filters.minROI) return false;
        if (filters.maxMileage && opportunity.vehicle.mileage > filters.maxMileage) return false;
        if (filters.status?.length && !filters.status.includes(opportunity.status || '')) return false;
        return true;
      })
      .sort((a, b) => {
        const aVal = a[sorting.field] || 0;
        const bVal = b[sorting.field] || 0;
        return sorting.direction === 'asc' ? aVal - bVal : bVal - aVal;
      });
  }, [opportunities, filters, sorting]);

  // Top opportunities (high profit, high confidence)
  const topOpportunities = useMemo(() => {
    return filteredOpportunities
      .filter(op => op.profit > 3000 && op.confidence > 75)
      .slice(0, 10);
  }, [filteredOpportunities]);

  // High risk opportunities (low confidence but high profit)
  const highRiskOpportunities = useMemo(() => {
    return filteredOpportunities
      .filter(op => op.profit > 5000 && op.confidence < 60)
      .slice(0, 5);
  }, [filteredOpportunities]);

  // Statistics
  const stats = useMemo(() => {
    const total = filteredOpportunities.length;
    const totalProfit = filteredOpportunities.reduce((sum, op) => sum + op.profit, 0);
    const averageROI = total > 0 ? filteredOpportunities.reduce((sum, op) => sum + op.roi, 0) / total : 0;
    const averageConfidence = total > 0 ? filteredOpportunities.reduce((sum, op) => sum + op.confidence, 0) / total : 0;

    return {
      totalOpportunities: total,
      totalProfit,
      averageROI,
      averageConfidence
    };
  }, [filteredOpportunities]);

  return {
    filteredOpportunities,
    topOpportunities,
    highRiskOpportunities,
    stats,
    filters,
    setFilters,
    sorting,
    setSorting
  };
}