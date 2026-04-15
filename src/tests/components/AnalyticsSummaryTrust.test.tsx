import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AnalyticsSummarySection from '@/components/AnalyticsSummarySection';

const StatCard = ({ label, value, sub }: { label: string; value: string | number; sub?: string; accent?: boolean }) => (
  <div>
    <p>{label}</p>
    <p>{value}</p>
    {sub ? <p>{sub}</p> : null}
  </div>
);

const AnalyticsOpenTrustCasesPanel = () => <div>Trust cases</div>;

describe('Analytics trust banner', () => {
  it('renders degraded state explicitly', () => {
    render(
      <AnalyticsSummarySection
        summaryLoading={false}
        safeSummary={{
          pipeline: { active_opportunities: 42, fresh_opportunities_7d: 11 },
          execution: { bids_placed: 4, wins: 1, win_rate: 25, avg_purchase_price: 14500, avg_max_bid: 15000 },
          outcomes: { recorded_outcomes: 0, avg_gross_margin: null, avg_roi: null, wins_by_source: [], top_makes_by_realized_performance: [] },
          trust: {
            status: 'degraded',
            severity: 'medium',
            degraded_sections: ['execution', 'outcomes', 'trust'],
            notes: ['Analytics trust is mixed: some system signals are current, but execution/outcomes freshness is stale or empty.'],
            rule_ids: ['healthy_source_health_with_stale_summary'],
            completeness_score: 0.25,
            summary_refreshed_at: '2026-04-13T18:28:17.109326+00:00',
          },
          freshness: {
            pipeline: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            source_health: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            execution: { updated_at: '2026-04-13T17:00:00+00:00', age_seconds: 172800, status: 'stale' },
            outcomes: { updated_at: null, age_seconds: null, status: 'empty' },
          },
        }}
        recentTrustEventsLoading={false}
        recentTrustEvents={[]}
        recentOpenTrustEvents={[]}
        recentNeedsActionCount={0}
        fmt$={(n) => (n == null ? '—' : `$${n}`)}
        fmtPct={(n) => (n == null ? '—' : `${n}%`)}
        StatCard={StatCard}
        AnalyticsOpenTrustCasesPanel={AnalyticsOpenTrustCasesPanel}
      />
    );

    expect(screen.getByText('Analytics partially degraded')).toBeInTheDocument();
    expect(screen.getByText('Analytics trust is mixed: system ingest is fresh, source health is fresh, execution is stale, outcomes is empty.')).toBeInTheDocument();
    expect(screen.getByText('Freshness snapshot')).toBeInTheDocument();
    expect(screen.getByText('System ingest')).toBeInTheDocument();
    expect(screen.getByText('Source health')).toBeInTheDocument();
    expect(screen.getByText('Execution')).toBeInTheDocument();
    expect(screen.getByText('Outcomes')).toBeInTheDocument();
    expect(screen.getByText('Trust cases')).toBeInTheDocument();
  });

  it('renders suspicious business-truth warning when suspicious notes are present', () => {
    render(
      <AnalyticsSummarySection
        summaryLoading={false}
        safeSummary={{
          pipeline: { active_opportunities: 42, fresh_opportunities_7d: 11 },
          execution: { bids_placed: 4, wins: 1, win_rate: 25, avg_purchase_price: 14500, avg_max_bid: 15000 },
          outcomes: { recorded_outcomes: 0, avg_gross_margin: null, avg_roi: null, wins_by_source: [], top_makes_by_realized_performance: [] },
          trust: {
            status: 'degraded',
            severity: 'high',
            degraded_sections: ['trust', 'execution'],
            notes: ['Source health appears healthy while execution/outcomes freshness is stale or empty.'],
            rule_ids: ['healthy_source_health_with_stale_summary'],
            completeness_score: 0.6,
            summary_refreshed_at: '2026-04-13T18:28:17.109326+00:00',
          },
          freshness: {
            pipeline: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            source_health: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            execution: { updated_at: '2026-04-13T17:00:00+00:00', age_seconds: 172800, status: 'stale' },
            outcomes: { updated_at: null, age_seconds: null, status: 'empty' },
          },
        }}
        recentTrustEventsLoading={false}
        recentTrustEvents={[]}
        recentOpenTrustEvents={[]}
        recentNeedsActionCount={0}
        fmt$={(n) => (n == null ? '—' : `$${n}`)}
        fmtPct={(n) => (n == null ? '—' : `${n}%`)}
        StatCard={StatCard}
        AnalyticsOpenTrustCasesPanel={AnalyticsOpenTrustCasesPanel}
      />
    );

    expect(screen.getByText('Analytics high-risk contradiction detected')).toBeInTheDocument();
    expect(screen.getByText('Analytics trust is mixed: system ingest is fresh, source health is fresh, execution is stale, outcomes is empty.')).toBeInTheDocument();
  });

  it('treats stale-freshness/source-health contradictions as suspicious', () => {
    render(
      <AnalyticsSummarySection
        summaryLoading={false}
        safeSummary={{
          pipeline: { active_opportunities: 42, fresh_opportunities_7d: 11 },
          execution: { bids_placed: 4, wins: 1, win_rate: 25, avg_purchase_price: 14500, avg_max_bid: 15000 },
          outcomes: { recorded_outcomes: 0, avg_gross_margin: null, avg_roi: null, wins_by_source: [], top_makes_by_realized_performance: [] },
          trust: {
            status: 'degraded',
            severity: 'medium',
            degraded_sections: ['trust', 'source_health'],
            notes: ['Source health appears healthy while execution/outcomes freshness is stale or empty.'],
            rule_ids: ['healthy_source_health_with_stale_summary'],
            completeness_score: 0.4,
            summary_refreshed_at: '2026-04-13T18:28:17.109326+00:00',
          },
          freshness: {
            pipeline: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            source_health: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            execution: { updated_at: '2026-04-13T17:00:00+00:00', age_seconds: 172800, status: 'stale' },
            outcomes: { updated_at: null, age_seconds: null, status: 'empty' },
          },
        }}
        recentTrustEventsLoading={false}
        recentTrustEvents={[]}
        recentOpenTrustEvents={[]}
        recentNeedsActionCount={0}
        fmt$={(n) => (n == null ? '—' : `$${n}`)}
        fmtPct={(n) => (n == null ? '—' : `${n}%`)}
        StatCard={StatCard}
        AnalyticsOpenTrustCasesPanel={AnalyticsOpenTrustCasesPanel}
      />
    );

    expect(screen.getByText('Analytics trust is mixed: system ingest is fresh, source health is fresh, execution is stale, outcomes is empty.')).toBeInTheDocument();
  });

  it('does not render when trust is healthy', () => {
    render(
      <AnalyticsSummarySection
        summaryLoading={false}
        safeSummary={{
          pipeline: { active_opportunities: 42, fresh_opportunities_7d: 11 },
          execution: { bids_placed: 4, wins: 1, win_rate: 25, avg_purchase_price: 14500, avg_max_bid: 15000 },
          outcomes: { recorded_outcomes: 0, avg_gross_margin: null, avg_roi: null, wins_by_source: [], top_makes_by_realized_performance: [] },
          trust: {
            status: 'healthy',
            severity: 'low',
            degraded_sections: [],
            notes: [],
            rule_ids: [],
            completeness_score: 1,
            summary_refreshed_at: null,
          },
          freshness: {
            pipeline: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            source_health: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            execution: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
            outcomes: { updated_at: '2026-04-15T17:00:00+00:00', age_seconds: 3600, status: 'fresh' },
          },
        }}
        recentTrustEventsLoading={false}
        recentTrustEvents={[]}
        recentOpenTrustEvents={[]}
        recentNeedsActionCount={0}
        fmt$={(n) => (n == null ? '—' : `$${n}`)}
        fmtPct={(n) => (n == null ? '—' : `${n}%`)}
        StatCard={StatCard}
        AnalyticsOpenTrustCasesPanel={AnalyticsOpenTrustCasesPanel}
      />
    );

    expect(screen.queryByText('Analytics partially degraded')).not.toBeInTheDocument();
    expect(screen.getByText('Freshness snapshot')).toBeInTheDocument();
  });
});
