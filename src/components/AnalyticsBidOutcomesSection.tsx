interface SafeBidSummary {
  count_by_outcome?: Record<string, number>;
  total_gross_margin: number;
  avg_roi: number | null;
}

interface AnalyticsBidOutcomesSectionProps {
  bidSummaryLoading: boolean;
  safeBidSummary: SafeBidSummary | null;
  fmt$: (n: number | null | undefined) => string;
  fmtPct: (n: number | null | undefined) => string;
}

export default function AnalyticsBidOutcomesSection({
  bidSummaryLoading,
  safeBidSummary,
  fmt$,
  fmtPct,
}: AnalyticsBidOutcomesSectionProps) {
  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Bid Outcomes</p>
      {bidSummaryLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 p-4 animate-pulse">
              <div className="h-3 w-24 bg-gray-700 rounded mb-3" />
              <div className="h-7 w-16 bg-gray-700 rounded" />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">Won</div>
              <div className="text-2xl font-bold mt-2 text-white">{(safeBidSummary?.count_by_outcome?.won ?? 0).toLocaleString()}</div>
              <div className="text-sm text-gray-400 mt-1">Closed wins</div>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">Lost</div>
              <div className="text-2xl font-bold mt-2 text-white">{(safeBidSummary?.count_by_outcome?.lost ?? 0).toLocaleString()}</div>
              <div className="text-sm text-gray-400 mt-1">Lost bids</div>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">Passed</div>
              <div className="text-2xl font-bold mt-2 text-white">{(safeBidSummary?.count_by_outcome?.passed ?? 0).toLocaleString()}</div>
              <div className="text-sm text-gray-400 mt-1">Intentional passes</div>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">Pending</div>
              <div className="text-2xl font-bold mt-2 text-white">{(safeBidSummary?.count_by_outcome?.pending ?? 0).toLocaleString()}</div>
              <div className="text-sm text-gray-400 mt-1">Still open</div>
            </div>
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">Total Gross Margin</div>
              <div className="text-2xl font-bold mt-2 text-white">{safeBidSummary ? fmt$(safeBidSummary.total_gross_margin) : '—'}</div>
              <div className="text-sm text-gray-400 mt-1">From dealer_sales</div>
            </div>
            <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
              <div className="text-xs text-gray-500 font-medium uppercase tracking-wide">Avg ROI</div>
              <div className="text-2xl font-bold mt-2 text-white">{safeBidSummary?.avg_roi != null ? fmtPct(safeBidSummary.avg_roi) : '—'}</div>
              <div className="text-sm text-gray-400 mt-1">Across recorded outcomes</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
