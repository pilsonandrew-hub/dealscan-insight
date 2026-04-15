import type { AnalyticsFreshnessEntry } from '@/services/api';

type LegacyFreshnessArgs = {
  status: string | undefined;
  updatedAt: string | null | undefined;
  hasRecords: boolean;
  trustAgeSeconds: number | null;
};

export function deriveLegacyFreshnessEntry(
  status: string | undefined,
  updatedAt: string | null | undefined,
  isEmpty: boolean,
  trustAgeSeconds: number | null
): AnalyticsFreshnessEntry {
  // Empty means the section has no underlying records.
  // Unknown means we could not compute freshness for a populated section.
  if (isEmpty) {
    return {
      updated_at: updatedAt ?? null,
      age_seconds: null,
      status: 'empty',
    };
  }

  if (status === 'healthy') {
    return {
      updated_at: updatedAt ?? null,
      age_seconds: trustAgeSeconds,
      status: trustAgeSeconds != null && trustAgeSeconds > 86400 ? 'stale' : 'fresh',
    };
  }

  if (status === 'degraded') {
    return {
      updated_at: updatedAt ?? null,
      age_seconds: trustAgeSeconds,
      status: trustAgeSeconds != null && trustAgeSeconds > 86400 ? 'stale' : 'unknown',
    };
  }

  return {
    updated_at: updatedAt ?? null,
    age_seconds: trustAgeSeconds,
    status: 'unknown',
  };
}

export function deriveNoRecordAwareFreshnessEntry({
  status,
  updatedAt,
  hasRecords,
  trustAgeSeconds,
}: LegacyFreshnessArgs): AnalyticsFreshnessEntry {
  // Preserve empty for the no-record case even if the parent summary is degraded.
  if (!hasRecords) {
    return {
      updated_at: updatedAt ?? null,
      age_seconds: null,
      status: 'empty',
    };
  }

  return deriveLegacyFreshnessEntry(status, updatedAt, false, trustAgeSeconds);
}
