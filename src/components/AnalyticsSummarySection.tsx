import { Suspense } from 'react';
import type { AnalyticsFreshness, AnalyticsFreshnessStatus } from '@/services/api';

interface TrustData {
  status: string;
  severity: 'low' | 'medium' | 'high';
  degraded_sections: string[];
  notes: string[];
  rule_ids: string[];
  completeness_score: number | null;
  summary_refreshed_at: string | null;
}

interface FreshnessEntry {
  updated_at: string | null;
  age_seconds: number | null;
  status: AnalyticsFreshnessStatus;
}

interface SafeSummary {
  pipeline: {
    active_opportunities: number;
    fresh_opportunities_7d: number;
  };
  execution: {
    bids_placed: number;
    wins: number;
    win_rate: number | null;
    avg_purchase_price: number | null;
    avg_max_bid: number | null;
  };
  outcomes: {
    recorded_outcomes: number;
    avg_gross_margin: number | null;
    avg_roi: number | null;
    wins_by_source: { source: string; count: number }[];
    top_makes_by_realized_performance: { make: string; avg_gross_margin: number; count: number }[];
  };
  trust: TrustData;
  freshness: AnalyticsFreshness;
}

interface AnalyticsSummarySectionProps {
  summaryLoading: boolean;
  safeSummary: SafeSummary | null;
  recentTrustEventsLoading: boolean;
  recentTrustEvents: any[];
  recentOpenTrustEvents: any[];
  recentNeedsActionCount: number;
  fmt$: (n: number | null | undefined) => string;
  fmtPct: (n: number | null | undefined) => string;
  StatCard: React.ComponentType<{
    label: string;
    value: string | number;
    sub?: string;
    accent?: boolean;
  }>;
  AnalyticsOpenTrustCasesPanel: React.ComponentType<any>;
}

function freshnessLabel(status: AnalyticsFreshnessStatus): string {
  switch (status) {
    case 'fresh':
      return 'fresh';
    case 'stale':
      return 'stale';
    case 'empty':
      return 'empty';
    default:
      return 'unknown';
  }
}

function freshnessMeta(entry: FreshnessEntry): string {
  if (entry.status === 'empty') return 'No underlying records';
  if (entry.status === 'unknown') return 'Freshness could not be computed';
  if (entry.age_seconds == null) return 'Age unavailable';

  const hours = Math.floor(entry.age_seconds / 3600);
  if (hours >= 24) return `${Math.floor(hours / 24)}d old`;
  if (hours >= 1) return `${hours}h old`;
  const minutes = Math.max(1, Math.floor(entry.age_seconds / 60));
  return `${minutes}m old`;
}

function freshnessTone(status: AnalyticsFreshnessStatus): string {
  if (status === 'fresh') return 'text-emerald-300 border-emerald-500/30 bg-emerald-500/10';
  if (status === 'stale') return 'text-amber-300 border-amber-500/30 bg-amber-500/10';
  if (status === 'empty') return 'text-slate-300 border-slate-500/30 bg-slate-500/10';
  return 'text-slate-200 border-slate-500/30 bg-slate-500/10';
}

export default function AnalyticsSummarySection({
  summaryLoading,
  safeSummary,
  recentTrustEventsLoading,
  recentTrustEvents,
  recentOpenTrustEvents,
  recentNeedsActionCount,
  fmt$,
  fmtPct,
  StatCard,
  AnalyticsOpenTrustCasesPanel,
}: AnalyticsSummarySectionProps) {
  if (summaryLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-gray-900 rounded-xl border border-gray-800 p-4 animate-pulse">
            <div className="h-3 w-24 bg-gray-700 rounded mb-3" />
            <div className="h-7 w-16 bg-gray-700 rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (!safeSummary) return null;

  const freshnessItems = [
    { key: 'pipeline', label: 'System ingest', entry: safeSummary.freshness.pipeline },
    { key: 'source_health', label: 'Source health', entry: safeSummary.freshness.source_health },
    { key: 'execution', label: 'Execution', entry: safeSummary.freshness.execution },
    { key: 'outcomes', label: 'Outcomes', entry: safeSummary.freshness.outcomes },
  ];
  const freshnessSummary = freshnessItems.map((item) => `${item.label.toLowerCase()} is ${freshnessLabel(item.entry.status)}`).join(', ');
  const freshnessNeedsAttention = freshnessItems.some((item) => item.entry.status !== 'fresh');

  return (
    <div className="space-y-4">
      {safeSummary.trust.status === 'degraded' && (
        <div className={`${safeSummary.trust.severity === 'high' ? 'bg-red-500/10 border-red-500/30' : 'bg-amber-500/10 border-amber-500/30'} border rounded-xl p-3`}>
          <p className={`text-sm font-medium ${safeSummary.trust.severity === 'high' ? 'text-red-300' : 'text-amber-300'}`}>
            {safeSummary.trust.severity === 'high' ? 'Analytics high-risk contradiction detected' : 'Analytics partially degraded'}
          </p>
          <p className="text-xs text-amber-100/80 mt-1">
            {`Analytics trust is mixed: ${freshnessSummary}.`}
          </p>
          <p className="text-xs text-amber-200/80 mt-1">
            {safeSummary.trust.degraded_sections.length > 0
              ? `Affected: ${safeSummary.trust.degraded_sections.join(', ')}`
              : 'Some analytics sections are currently partial.'}
          </p>
          {safeSummary.trust.notes.length > 0 && (
            <div className="mt-1 space-y-1">
              {safeSummary.trust.notes.slice(0, 2).map((note, index) => {
                const ruleId = safeSummary.trust.rule_ids?.[index];
                return (
                  <p key={`${note}-${index}`} className="text-xs text-amber-200/70">
                    {ruleId ? `[${ruleId}] ` : ''}{note}
                  </p>
                );
              })}
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-amber-100/70">
            <span>Completeness: {safeSummary.trust.completeness_score != null ? `${Math.round(safeSummary.trust.completeness_score * 100)}%` : '—'}</span>
            <span>Refreshed: {safeSummary.trust.summary_refreshed_at ? new Date(safeSummary.trust.summary_refreshed_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—'}</span>
          </div>
        </div>
      )}

      <div className={`${freshnessNeedsAttention ? 'border-sky-500/25 bg-sky-500/10' : 'border-gray-800 bg-gray-900'} rounded-xl border p-3`}>
        <p className="text-xs font-medium text-sky-200 uppercase tracking-wide">Freshness snapshot</p>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
          {freshnessItems.map((item) => (
            <div key={item.key} className="rounded-lg border border-white/10 bg-black/20 p-3">
              <p className="text-[10px] uppercase tracking-wide text-gray-400">{item.label}</p>
              <p className={`mt-1 text-sm font-semibold ${freshnessTone(item.entry.status)}`}>
                {freshnessLabel(item.entry.status)}
              </p>
              <p className="mt-1 text-[11px] text-gray-400">{freshnessMeta(item.entry)}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Active Opportunities"
          value={safeSummary.pipeline.active_opportunities.toLocaleString()}
          sub={`${safeSummary.pipeline.fresh_opportunities_7d.toLocaleString()} fresh in 7d, system-wide`}
        />
        <StatCard
          label="Bids Placed"
          value={safeSummary.execution.bids_placed.toLocaleString()}
          sub={safeSummary.execution.bids_placed > 0 ? 'Explicit bid outcome records only' : 'No bid records logged'}
          accent={safeSummary.execution.bids_placed > 0}
        />
        <StatCard
          label="Wins from Bid Records"
          value={safeSummary.execution.wins.toLocaleString()}
          sub={safeSummary.execution.bids_placed > 0 ? 'Won bid records only, separate from final realized outcomes' : 'No wins logged'}
          accent={safeSummary.execution.wins > 0}
        />
        <StatCard
          label="Bid Record Win Rate"
          value={safeSummary.execution.win_rate != null ? `${safeSummary.execution.win_rate}%` : '—'}
          sub={safeSummary.execution.bids_placed > 0 ? `${safeSummary.execution.wins} / ${safeSummary.execution.bids_placed} bid records` : 'No bid records logged'}
          accent={safeSummary.execution.win_rate != null && safeSummary.execution.win_rate > 0}
        />
      </div>

      <div className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-3">
        <p className="text-xs font-medium text-amber-200">Execution remains a defended subset</p>
        <p className="mt-1 text-[11px] text-amber-100/80">
          We only show bid-record metrics we can prove cleanly. Full workflow ledger semantics still live in the trust layer until execution is fully unified.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Recorded Outcomes"
          value={safeSummary.outcomes.recorded_outcomes.toLocaleString()}
          sub="User-scoped closed outcomes"
          accent
        />
        <StatCard
          label="Avg Gross Margin"
          value={safeSummary.outcomes.avg_gross_margin != null ? fmt$(safeSummary.outcomes.avg_gross_margin) : '—'}
          sub="From recorded user outcomes"
          accent={safeSummary.outcomes.avg_gross_margin != null && safeSummary.outcomes.avg_gross_margin > 0}
        />
        <StatCard
          label="Avg ROI %"
          value={safeSummary.outcomes.avg_roi != null ? fmtPct(safeSummary.outcomes.avg_roi) : '—'}
          sub="From recorded user outcomes"
          accent={safeSummary.outcomes.avg_roi != null && safeSummary.outcomes.avg_roi > 0}
        />
        <StatCard
          label="Summary Trust"
          value={safeSummary.trust.completeness_score != null ? `${Math.round(safeSummary.trust.completeness_score * 100)}%` : '—'}
          sub={safeSummary.trust.degraded_sections.length > 0
            ? `${safeSummary.trust.severity === 'high' ? 'High-risk' : 'Degraded'}: ${safeSummary.trust.degraded_sections.join(', ')}`
            : 'All sections healthy'}
          accent={safeSummary.trust.degraded_sections.length === 0}
        />
      </div>

      <Suspense fallback={<div className="bg-gray-900 rounded-xl border border-gray-800 p-4 text-sm text-gray-500">Loading trust cases...</div>}>
        <AnalyticsOpenTrustCasesPanel
          recentTrustEventsLoading={recentTrustEventsLoading}
          recentTrustEvents={recentTrustEvents}
          recentOpenTrustEvents={recentOpenTrustEvents}
          recentNeedsActionCount={recentNeedsActionCount}
        />
      </Suspense>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">Wins by Source (User Outcomes)</p>
          {safeSummary.outcomes.wins_by_source.length === 0 ? (
            <p className="text-sm text-gray-500">No recorded user outcome data yet</p>
          ) : (
            <div className="space-y-1.5">
              {safeSummary.outcomes.wins_by_source.map(({ source, count }) => (
                <div key={source} className="flex items-center justify-between text-sm">
                  <span className="text-gray-300 truncate">{source}</span>
                  <span className="text-white font-medium ml-2 shrink-0">{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">Top Makes by Realized User Outcomes</p>
          {safeSummary.outcomes.top_makes_by_realized_performance.length === 0 ? (
            <p className="text-sm text-gray-500">No realized user outcome data yet</p>
          ) : (
            <div className="space-y-1.5">
              {safeSummary.outcomes.top_makes_by_realized_performance.map(({ make, avg_gross_margin, count }) => (
                <div key={make} className="flex items-center justify-between text-sm">
                  <span className="text-gray-300">{make}</span>
                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    <span className="text-xs px-1.5 py-0.5 rounded font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                      {fmt$(avg_gross_margin)}
                    </span>
                    <span className="text-gray-500 text-xs">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
