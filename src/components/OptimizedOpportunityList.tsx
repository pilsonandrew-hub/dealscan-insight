/**
 * Optimized opportunity list with virtualization and performance monitoring
 */

import React, { useState, useMemo, useCallback, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useOptimizedOpportunities } from '@/hooks/useOptimizedOpportunities';
import { usePerformanceOptimizer } from '@/hooks/usePerformanceOptimizer';
import { Opportunity } from '@/types/dealerscope';
import { Search, Filter, TrendingUp, DollarSign, Target, MapPin } from 'lucide-react';

interface OptimizedOpportunityListProps {
  opportunities: Opportunity[];
  onSelectOpportunity?: (opportunity: Opportunity) => void;
}

export function OptimizedOpportunityList({ 
  opportunities, 
  onSelectOpportunity 
}: OptimizedOpportunityListProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 50 });

  const {
    filteredOpportunities,
    topOpportunities,
    stats,
    filters,
    setFilters,
    sorting,
    setSorting
  } = useOptimizedOpportunities(opportunities);

  const {
    metrics,
    isOptimized,
    startRenderTimer,
    endRenderTimer,
    getVisibleItems,
    throttledUpdate
  } = usePerformanceOptimizer({
    maxRenderItems: 50,
    throttleDelay: 150,
    enableVirtualization: true
  });

  // Search filtering
  const searchFilteredOpportunities = useMemo(() => {
    if (!searchTerm) return filteredOpportunities;
    
    const term = searchTerm.toLowerCase();
    return filteredOpportunities.filter(op =>
      op.vehicle.make.toLowerCase().includes(term) ||
      op.vehicle.model.toLowerCase().includes(term) ||
      op.vehicle.vin.toLowerCase().includes(term) ||
      op.state?.toLowerCase().includes(term)
    );
  }, [filteredOpportunities, searchTerm]);

  // Virtualized opportunities for rendering
  const visibleOpportunities = useMemo(() => {
    startRenderTimer();
    const visible = getVisibleItems(searchFilteredOpportunities, visibleRange.start, visibleRange.end);
    endRenderTimer();
    return visible;
  }, [searchFilteredOpportunities, visibleRange, getVisibleItems, startRenderTimer, endRenderTimer]);

  // Handle search with throttling
  const handleSearch = useCallback((value: string) => {
    throttledUpdate(() => setSearchTerm(value));
  }, [throttledUpdate]);

  // Handle scroll for virtualization
  const handleScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const { scrollTop, clientHeight, scrollHeight } = e.currentTarget;
    const scrollPercentage = scrollTop / (scrollHeight - clientHeight);
    
    if (scrollPercentage > 0.8) {
      setVisibleRange(prev => ({
        start: prev.start,
        end: Math.min(prev.end + 25, searchFilteredOpportunities.length)
      }));
    }
  }, [searchFilteredOpportunities.length]);

  const getStatusColor = (status?: string) => {
    switch (status) {
      case 'hot': return 'destructive';
      case 'good': return 'default';
      case 'moderate': return 'secondary';
      default: return 'outline';
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  return (
    <div className="space-y-4">
      {/* Performance Metrics (only in dev mode) */}
      {process.env.NODE_ENV === 'development' && (
        <Card className="border-dashed">
          <CardContent className="pt-4">
            <div className="grid grid-cols-4 gap-4 text-sm">
              <div>Render: {metrics.renderTime.toFixed(1)}ms</div>
              <div>Memory: {(metrics.memoryUsage / 1024 / 1024).toFixed(1)}MB</div>
              <div>Updates/s: {metrics.updateFrequency.toFixed(1)}</div>
              <div>Optimized: {isOptimized ? 'Yes' : 'No'}</div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats Summary */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Target className="h-4 w-4 text-blue-500" />
              <div>
                <div className="text-2xl font-bold">{stats.totalOpportunities}</div>
                <p className="text-xs text-muted-foreground">Total Opportunities</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <DollarSign className="h-4 w-4 text-green-500" />
              <div>
                <div className="text-2xl font-bold">{formatCurrency(stats.totalProfit)}</div>
                <p className="text-xs text-muted-foreground">Total Profit</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <TrendingUp className="h-4 w-4 text-yellow-500" />
              <div>
                <div className="text-2xl font-bold">{stats.averageROI.toFixed(1)}%</div>
                <p className="text-xs text-muted-foreground">Average ROI</p>
              </div>
            </div>
          </CardContent>
        </Card>
        
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center space-x-2">
              <Target className="h-4 w-4 text-purple-500" />
              <div>
                <div className="text-2xl font-bold">{stats.averageConfidence.toFixed(1)}%</div>
                <p className="text-xs text-muted-foreground">Avg Confidence</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters and Search */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center space-x-2">
            <Filter className="h-5 w-5" />
            <span>Filters & Search</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search by make, model, VIN, or state..."
                  value={searchTerm}
                  onChange={(e) => handleSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            
            <div className="flex gap-2">
              <Select
                value={sorting.field}
                onValueChange={(value) => setSorting({ ...sorting, field: value as any })}
              >
                <SelectTrigger className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="profit">Profit</SelectItem>
                  <SelectItem value="roi">ROI</SelectItem>
                  <SelectItem value="confidence">Confidence</SelectItem>
                  <SelectItem value="score">Score</SelectItem>
                </SelectContent>
              </Select>
              
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSorting({ ...sorting, direction: sorting.direction === 'asc' ? 'desc' : 'asc' })}
              >
                {sorting.direction === 'asc' ? '↑' : '↓'}
              </Button>
            </div>
          </div>
          
          <div className="flex flex-wrap gap-2">
            <Input
              type="number"
              placeholder="Min Profit"
              value={filters.minProfit || ''}
              onChange={(e) => setFilters({ ...filters, minProfit: Number(e.target.value) || undefined })}
              className="w-32"
            />
            <Input
              type="number"
              placeholder="Min ROI %"
              value={filters.minROI || ''}
              onChange={(e) => setFilters({ ...filters, minROI: Number(e.target.value) || undefined })}
              className="w-32"
            />
            <Input
              type="number"
              placeholder="Max Mileage"
              value={filters.maxMileage || ''}
              onChange={(e) => setFilters({ ...filters, maxMileage: Number(e.target.value) || undefined })}
              className="w-32"
            />
          </div>
        </CardContent>
      </Card>

      {/* Opportunities List */}
      <Card>
        <CardHeader>
          <CardTitle>
            Opportunities ({searchFilteredOpportunities.length})
            {isOptimized && <Badge variant="secondary" className="ml-2">Optimized</Badge>}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div 
            className="space-y-3 max-h-96 overflow-y-auto"
            onScroll={handleScroll}
          >
            {visibleOpportunities.map((opportunity, index) => (
              <div
                key={opportunity.id || index}
                className="p-4 border rounded-lg hover:bg-accent/50 cursor-pointer transition-colors"
                onClick={() => onSelectOpportunity?.(opportunity)}
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-2 mb-2">
                      <h3 className="font-semibold">
                        {opportunity.vehicle.year} {opportunity.vehicle.make} {opportunity.vehicle.model}
                      </h3>
                      <Badge variant={getStatusColor(opportunity.status)}>
                        {opportunity.status || 'pending'}
                      </Badge>
                    </div>
                    
                    <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                      <span>VIN: {opportunity.vehicle.vin}</span>
                      <span>{opportunity.vehicle.mileage.toLocaleString()} miles</span>
                      {opportunity.state && (
                        <span className="flex items-center space-x-1">
                          <MapPin className="h-3 w-3" />
                          <span>{opportunity.state}</span>
                        </span>
                      )}
                    </div>
                  </div>
                  
                  <div className="text-right">
                    <div className="text-lg font-bold text-green-600">
                      {formatCurrency(opportunity.profit)}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {opportunity.roi.toFixed(1)}% ROI • {opportunity.confidence.toFixed(0)}% confidence
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Cost: {formatCurrency(opportunity.acquisition_cost)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            
            {visibleRange.end < searchFilteredOpportunities.length && (
              <div className="text-center py-4">
                <Button
                  variant="outline"
                  onClick={() => setVisibleRange(prev => ({ ...prev, end: prev.end + 25 }))}
                >
                  Load More ({searchFilteredOpportunities.length - visibleRange.end} remaining)
                </Button>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}