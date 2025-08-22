
import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Opportunity } from '@/types/dealerscope';

interface ProfitDistributionChartProps {
  opportunities: Opportunity[];
}

interface ProfitRange {
  range: string;
  count: number;
  percentage: number;
  color: string;
  minProfit: number;
  maxProfit: number;
}

const PROFIT_RANGES = [
  { min: 0, max: 1000, label: '$0-1K', color: '#ef4444' },
  { min: 1000, max: 2500, label: '$1K-2.5K', color: '#f97316' },
  { min: 2500, max: 5000, label: '$2.5K-5K', color: '#eab308' },
  { min: 5000, max: 10000, label: '$5K-10K', color: '#22c55e' },
  { min: 10000, max: 25000, label: '$10K-25K', color: '#06b6d4' },
  { min: 25000, max: Infinity, label: '$25K+', color: '#8b5cf6' }
];

export function ProfitDistributionChart({ opportunities }: ProfitDistributionChartProps) {
  const distributionData: ProfitRange[] = React.useMemo(() => {
    const total = opportunities.length;
    
    return PROFIT_RANGES.map(range => {
      const count = opportunities.filter(op => 
        op.potential_profit >= range.min && op.potential_profit < range.max
      ).length;
      
      return {
        range: range.label,
        count,
        percentage: total > 0 ? Math.round((count / total) * 100) : 0,
        color: range.color,
        minProfit: range.min,
        maxProfit: range.max === Infinity ? 999999 : range.max
      };
    });
  }, [opportunities]);

  const formatTooltip = (value: number, name: string, props: any) => {
    const data = props.payload;
    return [
      `${value} opportunities (${data.percentage}%)`,
      `Profit Range: ${data.range}`
    ];
  };

  const formatYAxisTick = (value: number) => {
    return value.toString();
  };

  const formatXAxisTick = (value: string) => {
    return value;
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg font-semibold">Profit Distribution</CardTitle>
        <CardDescription>
          Distribution of {opportunities.length} opportunities by profit range
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-80 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={distributionData}
              margin={{ top: 20, right: 30, left: 40, bottom: 60 }}
              barCategoryGap="15%"
            >
              <CartesianGrid 
                strokeDasharray="3 3" 
                stroke="hsl(var(--muted-foreground))" 
                opacity={0.3}
              />
              <XAxis
                dataKey="range"
                tick={{ 
                  fontSize: 12, 
                  fill: 'hsl(var(--foreground))',
                  fontWeight: 500
                }}
                tickFormatter={formatXAxisTick}
                axisLine={{ stroke: 'hsl(var(--border))' }}
                tickLine={{ stroke: 'hsl(var(--border))' }}
                angle={-45}
                textAnchor="end"
                height={80}
              />
              <YAxis
                tick={{ 
                  fontSize: 12, 
                  fill: 'hsl(var(--foreground))',
                  fontWeight: 500
                }}
                tickFormatter={formatYAxisTick}
                axisLine={{ stroke: 'hsl(var(--border))' }}
                tickLine={{ stroke: 'hsl(var(--border))' }}
                label={{ 
                  value: 'Number of Opportunities', 
                  angle: -90, 
                  position: 'insideLeft',
                  style: { textAnchor: 'middle', fill: 'hsl(var(--foreground))' }
                }}
              />
              <Tooltip
                formatter={formatTooltip}
                contentStyle={{
                  backgroundColor: 'hsl(var(--popover))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: '6px',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: 'hsl(var(--popover-foreground))'
                }}
                labelStyle={{
                  color: 'hsl(var(--popover-foreground))',
                  fontWeight: '600'
                }}
              />
              <Bar 
                dataKey="count" 
                radius={[4, 4, 0, 0]}
                stroke="hsl(var(--border))"
                strokeWidth={1}
              >
                {distributionData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        
        {/* Summary Statistics */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mt-6 pt-4 border-t">
          {distributionData.map((range, index) => (
            <div key={index} className="flex items-center space-x-2">
              <div 
                className="w-3 h-3 rounded-sm flex-shrink-0"
                style={{ backgroundColor: range.color }}
              />
              <div className="text-sm">
                <div className="font-semibold">{range.range}</div>
                <div className="text-muted-foreground">
                  {range.count} ({range.percentage}%)
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
