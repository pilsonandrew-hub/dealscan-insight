import { describe, it, expect } from 'vitest';

type AnalyticsSummary = {
  total_opportunities: number;
  total_outcomes: number;
  avg_gross_margin: number | null;
  avg_roi_pct: number | null;
  wins_by_source: { source: string; count: number }[];
  top_makes: { make: string; avg_gross_margin: number; count: number }[];
  alerts_sent_last_30d: number;
  total_bids: number;
  total_wins: number;
  win_rate: number | null;
  avg_purchase_price: number | null;
  avg_max_bid: number | null;
  pipeline?: {
    status: 'healthy' | 'degraded' | 'empty';
    scope: 'system';
    updated_at: string | null;
    active_opportunities: number;
    fresh_opportunities_24h: number;
    fresh_opportunities_7d: number;
    hot_deals_count: number;
    good_plus_deals_count: number;
    avg_dos_score: number | null;
    unique_sources: number;
    unique_states: number;
  };
  execution?: {
    status: 'healthy' | 'degraded' | 'empty';
    scope: 'user_execution';
    updated_at: string | null;
    workflow_counts?: {
      wins: number;
      losses: number | null;
      passes: number | null;
      pending: number | null;
    };
    bid_metrics?: {
      bids_placed: number;
      win_rate: number | null;
      avg_max_bid: number | null;
      avg_purchase_price: number | null;
      ceiling_compliance: number | null;
    };
  };
  outcomes?: {
    status: 'healthy' | 'degraded' | 'empty';
    scope: 'user_outcomes';
    updated_at: string | null;
    recorded_outcomes: number;
    total_gross_margin: number | null;
    avg_gross_margin: number | null;
    avg_roi: number | null;
    wins_by_source: { source: string; count: number }[];
    top_makes_by_realized_performance: { make: string; avg_gross_margin: number; count: number }[];
  };
  trust?: {
    status: 'healthy' | 'degraded' | 'empty';
    scope: 'trust';
    updated_at: string | null;
    summary_refreshed_at: string | null;
    completeness_score: number | null;
    degraded_sections: string[];
    freshness_age: number | null;
    notes: string[];
  };
  freshness?: {
    pipeline: {
      updated_at: string | null;
      age_seconds: number | null;
      status: 'fresh' | 'stale' | 'empty' | 'unknown';
    };
    source_health: {
      updated_at: string | null;
      age_seconds: number | null;
      status: 'fresh' | 'stale' | 'empty' | 'unknown';
    };
    execution: {
      updated_at: string | null;
      age_seconds: number | null;
      status: 'fresh' | 'stale' | 'empty' | 'unknown';
    };
    outcomes: {
      updated_at: string | null;
      age_seconds: number | null;
      status: 'fresh' | 'stale' | 'empty' | 'unknown';
    };
  };
};

const normalizeSummary = (summary: AnalyticsSummary) => ({
  pipeline: {
    status: summary.pipeline?.status ?? 'empty',
    scope: summary.pipeline?.scope ?? 'system',
    active_opportunities: summary.pipeline?.active_opportunities ?? summary.total_opportunities ?? 0,
  },
  execution: {
    status: summary.execution?.status ?? 'empty',
    scope: summary.execution?.scope ?? 'user_execution',
    bids_placed: summary.execution?.bid_metrics?.bids_placed ?? summary.total_bids ?? 0,
    wins: summary.execution?.workflow_counts?.wins ?? summary.total_wins ?? 0,
    losses: summary.execution?.workflow_counts?.losses ?? null,
    passes: summary.execution?.workflow_counts?.passes ?? null,
    pending: summary.execution?.workflow_counts?.pending ?? null,
    win_rate: summary.execution?.bid_metrics?.win_rate ?? summary.win_rate ?? null,
  },
  outcomes: {
    status: summary.outcomes?.status ?? 'empty',
    scope: summary.outcomes?.scope ?? 'user_outcomes',
    recorded_outcomes: summary.outcomes?.recorded_outcomes ?? summary.total_outcomes ?? 0,
    wins_by_source: summary.outcomes?.wins_by_source ?? summary.wins_by_source ?? [],
  },
  trust: {
    status: summary.trust?.status ?? 'healthy',
    scope: summary.trust?.scope ?? 'trust',
    degraded_sections: summary.trust?.degraded_sections ?? [],
  },
  freshness: {
    pipeline: summary.freshness?.pipeline ?? { updated_at: null, age_seconds: null, status: 'unknown' as const },
    source_health: summary.freshness?.source_health ?? { updated_at: null, age_seconds: null, status: 'unknown' as const },
    execution: summary.freshness?.execution ?? { updated_at: null, age_seconds: null, status: 'unknown' as const },
    outcomes: summary.freshness?.outcomes ?? { updated_at: null, age_seconds: null, status: 'unknown' as const },
  },
});

describe('Analytics summary contract transition', () => {
  it('preserves grouped sections when present', () => {
    const normalized = normalizeSummary({
      total_opportunities: 5,
      total_outcomes: 1,
      avg_gross_margin: null,
      avg_roi_pct: null,
      wins_by_source: [],
      top_makes: [],
      alerts_sent_last_30d: 0,
      total_bids: 1,
      total_wins: 0,
      win_rate: null,
      avg_purchase_price: null,
      avg_max_bid: null,
      pipeline: {
        status: 'healthy',
        scope: 'system',
        updated_at: null,
        active_opportunities: 100,
        fresh_opportunities_24h: 4,
        fresh_opportunities_7d: 12,
        hot_deals_count: 20,
        good_plus_deals_count: 50,
        avg_dos_score: 77,
        unique_sources: 7,
        unique_states: 5,
      },
      execution: {
        status: 'degraded',
        scope: 'user_execution',
        updated_at: null,
        workflow_counts: {
          wins: 0,
          losses: 0,
          passes: 0,
          pending: null,
        },
        bid_metrics: {
          bids_placed: 0,
          win_rate: null,
          avg_max_bid: null,
          avg_purchase_price: null,
          ceiling_compliance: null,
        },
      },
      outcomes: {
        status: 'empty',
        scope: 'user_outcomes',
        updated_at: null,
        recorded_outcomes: 0,
        total_gross_margin: null,
        avg_gross_margin: null,
        avg_roi: null,
        wins_by_source: [],
        top_makes_by_realized_performance: [],
      },
      trust: {
        status: 'degraded',
        scope: 'trust',
        updated_at: null,
        summary_refreshed_at: null,
        completeness_score: 0.25,
        degraded_sections: ['execution', 'outcomes'],
        freshness_age: null,
        notes: ['partial'],
      },
      freshness: {
        pipeline: {
          updated_at: '2026-04-15T17:00:00+00:00',
          age_seconds: 3600,
          status: 'fresh',
        },
        source_health: {
          updated_at: '2026-04-15T17:00:00+00:00',
          age_seconds: 3600,
          status: 'fresh',
        },
        execution: {
          updated_at: '2026-04-13T17:00:00+00:00',
          age_seconds: 172800,
          status: 'stale',
        },
        outcomes: {
          updated_at: null,
          age_seconds: null,
          status: 'empty',
        },
      },
    });

    expect(normalized.pipeline.active_opportunities).toBe(100);
    expect(normalized.execution.scope).toBe('user_execution');
    expect(normalized.execution.wins).toBe(0);
    expect(normalized.execution.losses).toBe(0);
    expect(normalized.execution.passes).toBe(0);
    expect(normalized.execution.pending).toBeNull();
    expect(normalized.outcomes.scope).toBe('user_outcomes');
    expect(normalized.trust.status).toBe('degraded');
    expect(normalized.freshness.pipeline.status).toBe('fresh');
    expect(normalized.freshness.execution.status).toBe('stale');
    expect(normalized.freshness.outcomes.status).toBe('empty');
  });

  it('falls back to legacy flat fields during transition', () => {
    const normalized = normalizeSummary({
      total_opportunities: 500,
      total_outcomes: 0,
      avg_gross_margin: null,
      avg_roi_pct: null,
      wins_by_source: [{ source: 'govdeals', count: 2 }],
      top_makes: [],
      alerts_sent_last_30d: 0,
      total_bids: 3,
      total_wins: 1,
      win_rate: 33.3,
      avg_purchase_price: null,
      avg_max_bid: null,
    });

    expect(normalized.pipeline.active_opportunities).toBe(500);
    expect(normalized.execution.bids_placed).toBe(3);
    expect(normalized.execution.wins).toBe(1);
    expect(normalized.execution.losses).toBeNull();
    expect(normalized.execution.passes).toBeNull();
    expect(normalized.execution.pending).toBeNull();
    expect(normalized.execution.win_rate).toBe(33.3);
    expect(normalized.outcomes.recorded_outcomes).toBe(0);
    expect(normalized.outcomes.wins_by_source).toEqual([{ source: 'govdeals', count: 2 }]);
    expect(normalized.trust.status).toBe('healthy');
    expect(normalized.freshness.pipeline.status).toBe('unknown');
    expect(normalized.freshness.execution.status).toBe('unknown');
  });
});
