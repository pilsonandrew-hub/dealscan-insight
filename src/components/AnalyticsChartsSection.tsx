import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip as ReTooltip, ResponsiveContainer, Cell,
} from 'recharts';

interface SourceHealthRowLike {
  source_site: string;
  health: string;
  latest_webhook_at?: string | null;
  fresh_opportunities_7d: number;
  latest_fetched_items?: number | null;
  latest_saved_items?: number | null;
  latest_skipped_items_estimate?: number | null;
  active_opportunities: number;
  latest_opportunity_age_hours?: number | null;
  latest_top_skip_reason?: string | null;
  latest_skip_reasons: Record<string, number>;
}

interface AnalyticsChartsSectionProps {
  dosHist: { range: string; count: number }[];
  stateData: { state: string; count: number }[];
  sourceHealthLoading: boolean;
  sourceHealthChartData: {
    name: string;
    value: number;
    health: string;
    fetched: number;
    saved: number;
    skipped: number;
    latestAgeHours: number | null;
  }[];
  normalizedSourceHealth: SourceHealthRowLike[];
  marginData: { day: string; avg_margin: number | null }[];
  fmt$: (n: number | null | undefined) => string;
  timeAgo: (iso: string | null | undefined) => string;
}

export default function AnalyticsChartsSection({
  dosHist,
  stateData,
  sourceHealthLoading,
  sourceHealthChartData,
  normalizedSourceHealth,
  marginData,
  fmt$,
  timeAgo,
}: AnalyticsChartsSectionProps) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">DOS Score Distribution</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={dosHist}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="range" tick={{ fill: '#9ca3af', fontSize: 12 }} />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
            <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} />
            <Bar dataKey="count" fill="#10b981" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Deals by State (Top 10)</h3>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={stateData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis type="number" tick={{ fill: '#9ca3af', fontSize: 12 }} />
            <YAxis type="category" dataKey="state" tick={{ fill: '#9ca3af', fontSize: 12 }} width={30} />
            <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} />
            <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <div className="flex items-start justify-between mb-4 gap-3">
          <div>
            <h3 className="text-sm font-semibold text-gray-300">Source Health (Fresh Opps 7d)</h3>
            <p className="text-xs text-gray-500">Operational truth: fresh contribution + latest run funnel, not historical portfolio mix.</p>
          </div>
        </div>
        {sourceHealthLoading ? (
          <div className="h-[260px] animate-pulse rounded-lg bg-gray-800/50" />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={sourceHealthChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <ReTooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }}
                  formatter={(value: number, _name, props: any) => {
                    const payload = props?.payload;
                    return [
                      <div className="space-y-1">
                        <div>Fresh opps 7d: {value}</div>
                        <div>Fetched: {payload?.fetched ?? 0}</div>
                        <div>Saved: {payload?.saved ?? 0}</div>
                        <div>Skipped: {payload?.skipped ?? 0}</div>
                        <div>Latest age: {payload?.latestAgeHours == null ? '—' : `${payload.latestAgeHours}h`}</div>
                      </div>,
                      payload?.name || 'Source',
                    ];
                  }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {sourceHealthChartData.map((entry, i) => (
                    <Cell
                      key={`${entry.name}-${i}`}
                      fill={entry.health === 'green' ? '#10b981' : entry.health === 'yellow' ? '#f59e0b' : '#ef4444'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            <div className="mt-4 space-y-2">
              {normalizedSourceHealth.map((row) => (
                <div key={row.source_site} className="rounded-lg border border-gray-800 bg-gray-950/40 px-3 py-2 flex flex-col gap-1">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className={`inline-block h-2.5 w-2.5 rounded-full ${row.health === 'green' ? 'bg-emerald-500' : row.health === 'yellow' ? 'bg-amber-400' : 'bg-red-500'}`} />
                      <span className="text-sm font-medium text-white">{row.source_site}</span>
                    </div>
                    <span className="text-xs text-gray-400">latest webhook: {timeAgo(row.latest_webhook_at)}</span>
                  </div>
                  <div className="text-xs text-gray-400 flex flex-wrap gap-x-4 gap-y-1">
                    <span>fresh 7d: <span className="text-white">{row.fresh_opportunities_7d}</span></span>
                    <span>fetched: <span className="text-white">{row.latest_fetched_items ?? 0}</span></span>
                    <span>saved: <span className="text-white">{row.latest_saved_items ?? 0}</span></span>
                    <span>skipped: <span className="text-white">{row.latest_skipped_items_estimate ?? 0}</span></span>
                    <span>active opps: <span className="text-white">{row.active_opportunities}</span></span>
                    <span>latest opp age: <span className="text-white">{row.latest_opportunity_age_hours == null ? '—' : `${row.latest_opportunity_age_hours}h`}</span></span>
                    <span>top reject: <span className="text-white">{row.latest_top_skip_reason ?? '—'}</span></span>
                  </div>
                  {Object.keys(row.latest_skip_reasons).length > 0 && (
                    <div className="mt-2 text-[11px] text-gray-500 flex flex-wrap gap-2">
                      {Object.entries(row.latest_skip_reasons)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 3)
                        .map(([reason, count]) => (
                          <span key={reason} className="rounded-full border border-gray-800 bg-gray-900/70 px-2 py-0.5">
                            {reason}: <span className="text-gray-300">{count}</span>
                          </span>
                        ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-4">Avg Margin, Last 14 Days</h3>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={marginData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis dataKey="day" tick={{ fill: '#9ca3af', fontSize: 10 }} />
            <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} tickFormatter={(value: number) => fmt$(value)} />
            <ReTooltip contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#fff' }} formatter={(value: number) => [fmt$(value), 'Avg Margin']} />
            <Line type="monotone" dataKey="avg_margin" stroke="#10b981" strokeWidth={2} dot={false} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
