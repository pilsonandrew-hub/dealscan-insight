import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

function TrustBanner({
  status,
  degradedSections,
  notes,
  completenessScore,
  summaryRefreshedAt,
}: {
  status: 'healthy' | 'degraded' | 'empty';
  degradedSections: string[];
  notes: string[];
  completenessScore: number | null;
  summaryRefreshedAt: string | null;
}) {
  if (status !== 'degraded') return null;

  return (
    <div>
      <p>Analytics partially degraded</p>
      <p>
        {degradedSections.length > 0
          ? `Affected: ${degradedSections.join(', ')}`
          : 'Some analytics sections are currently partial.'}
      </p>
      {notes.length > 0 && <p>{notes[0]}</p>}
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
        degradedSections={['execution', 'outcomes', 'trust']}
        notes={['Execution and outcomes metrics degraded']}
        completenessScore={0.25}
        summaryRefreshedAt="2026-04-13T18:28:17.109326+00:00"
      />
    );

    expect(screen.getByText('Analytics partially degraded')).toBeInTheDocument();
    expect(screen.getByText('Affected: execution, outcomes, trust')).toBeInTheDocument();
    expect(screen.getByText('Execution and outcomes metrics degraded')).toBeInTheDocument();
    expect(screen.getByText('Completeness: 25%')).toBeInTheDocument();
  });

  it('does not render when trust is healthy', () => {
    const { container } = render(
      <TrustBanner
        status="healthy"
        degradedSections={[]}
        notes={[]}
        completenessScore={1}
        summaryRefreshedAt={null}
      />
    );

    expect(container).toBeEmptyDOMElement();
  });
});
