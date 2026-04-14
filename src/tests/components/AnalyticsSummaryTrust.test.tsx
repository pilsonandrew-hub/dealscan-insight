import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

function TrustBanner({
  status,
  severity,
  degradedSections,
  ruleIds,
  notes,
  completenessScore,
  summaryRefreshedAt,
}: {
  status: 'healthy' | 'degraded' | 'empty';
  severity?: 'low' | 'medium' | 'high';
  degradedSections: string[];
  ruleIds?: string[];
  notes: string[];
  completenessScore: number | null;
  summaryRefreshedAt: string | null;
}) {
  if (status !== 'degraded') return null;

  const suspiciousNotes = notes.filter((note) =>
    note.includes('wins but no recorded outcomes') ||
    note.includes('Bid metrics are incomplete despite recorded bid activity') ||
    note.includes('Winning bid records exist without purchase-price support') ||
    note.includes('Recorded outcomes exist without outcome-source distribution') ||
    note.includes('Source health appears healthy while summary freshness is stale')
  );

  return (
    <div>
      <p>{severity === 'high' ? 'Analytics high-risk contradiction detected' : 'Analytics partially degraded'}</p>
      <p>
        {degradedSections.length > 0
          ? `Affected: ${degradedSections.join(', ')}`
          : 'Some analytics sections are currently partial.'}
      </p>
      {notes.length > 0 && (
        <div>
          {notes.slice(0, 2).map((note, index) => (
            <p key={`${note}-${index}`}>{ruleIds?.[index] ? `[${ruleIds[index]}] ` : ''}{note}</p>
          ))}
        </div>
      )}
      {suspiciousNotes.length > 0 && <p>Suspicious business-truth combinations detected</p>}
      <div>
        <span>Completeness: {completenessScore != null ? `${Math.round(completenessScore * 100)}%` : '—'}</span>
        <span>
          Refreshed: {summaryRefreshedAt ? new Date(summaryRefreshedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '—'}
        </span>
      </div>
    </div>
  );
}

describe('Analytics trust banner', () => {
  it('renders degraded state explicitly', () => {
    render(
      <TrustBanner
        status="degraded"
        severity="medium"
        degradedSections={['execution', 'outcomes', 'trust']}
        ruleIds={[]}
        notes={['Execution counts come from dealer_sales outcome states', 'Bid pricing metrics come from bid records']}
        completenessScore={0.25}
        summaryRefreshedAt="2026-04-13T18:28:17.109326+00:00"
      />
    );

    expect(screen.getByText('Analytics partially degraded')).toBeInTheDocument();
    expect(screen.getByText('Affected: execution, outcomes, trust')).toBeInTheDocument();
    expect(screen.getByText('Execution counts come from dealer_sales outcome states')).toBeInTheDocument();
    expect(screen.getByText('Bid pricing metrics come from bid records')).toBeInTheDocument();
    expect(screen.queryByText('Suspicious business-truth combinations detected')).not.toBeInTheDocument();
    expect(screen.getByText('Completeness: 25%')).toBeInTheDocument();
  });

  it('renders suspicious business-truth warning when suspicious notes are present', () => {
    render(
      <TrustBanner
        status="degraded"
        severity="high"
        degradedSections={['trust', 'execution']}
        ruleIds={['wins_without_recorded_outcomes']}
        notes={['Workflow counts show wins but no recorded outcomes exist']}
        completenessScore={0.6}
        summaryRefreshedAt="2026-04-13T18:28:17.109326+00:00"
      />
    );

    expect(screen.getByText('Analytics high-risk contradiction detected')).toBeInTheDocument();
    expect(screen.getByText('Suspicious business-truth combinations detected')).toBeInTheDocument();
    expect(screen.getByText('[wins_without_recorded_outcomes] Workflow counts show wins but no recorded outcomes exist')).toBeInTheDocument();
  });

  it('treats stale-freshness/source-health contradictions as suspicious', () => {
    render(
      <TrustBanner
        status="degraded"
        severity="medium"
        degradedSections={['trust', 'source_health']}
        ruleIds={['healthy_source_health_with_stale_summary']}
        notes={['Source health appears healthy while summary freshness is stale']}
        completenessScore={0.4}
        summaryRefreshedAt="2026-04-13T18:28:17.109326+00:00"
      />
    );

    expect(screen.getByText('Suspicious business-truth combinations detected')).toBeInTheDocument();
    expect(screen.getByText('[healthy_source_health_with_stale_summary] Source health appears healthy while summary freshness is stale')).toBeInTheDocument();
  });

  it('does not render when trust is healthy', () => {
    const { container } = render(
      <TrustBanner
        status="healthy"
        severity="low"
        degradedSections={[]}
        ruleIds={[]}
        notes={[]}
        completenessScore={1}
        summaryRefreshedAt={null}
      />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
