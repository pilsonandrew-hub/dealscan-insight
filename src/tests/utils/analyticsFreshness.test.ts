import { describe, it, expect } from 'vitest';
import { deriveNoRecordAwareFreshnessEntry } from '@/utils/analyticsFreshness';

describe('analytics freshness helpers', () => {
  it('treats no-record execution and outcomes states as empty even when status is degraded', () => {
    const updatedAt = '2026-04-15T18:00:00+00:00';

    const execution = deriveNoRecordAwareFreshnessEntry({
      status: 'degraded',
      updatedAt,
      hasRecords: false,
      trustAgeSeconds: null,
    });
    const outcomes = deriveNoRecordAwareFreshnessEntry({
      status: 'degraded',
      updatedAt,
      hasRecords: false,
      trustAgeSeconds: null,
    });

    expect(execution).toEqual({
      updated_at: updatedAt,
      age_seconds: null,
      status: 'empty',
    });
    expect(outcomes).toEqual({
      updated_at: updatedAt,
      age_seconds: null,
      status: 'empty',
    });
  });
});
