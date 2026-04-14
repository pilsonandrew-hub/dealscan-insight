interface TrustEvent {
  id: string | null;
  level: string | null;
  message: string | null;
  event: string | null;
  severity: 'low' | 'medium' | 'high' | null;
  rule_ids: string[];
  notes: string[];
  degraded_sections: string[];
  completeness_score: number | null;
  summary_refreshed_at: string | null;
  freshness_age: number | null;
  paperclip: {
    status: string | null;
    issue_id: string | null;
    identifier: string | null;
    title: string | null;
    issue_status: string | null;
    correlation_key: string | null;
    is_open: boolean;
  };
  timestamp: string | null;
}

interface AnalyticsOpenTrustCasesPanelProps {
  recentTrustEventsLoading: boolean;
  recentTrustEvents: TrustEvent[];
  recentOpenTrustEvents: TrustEvent[];
  recentNeedsActionCount: number;
}

const severityRank = (severity: 'low' | 'medium' | 'high' | null) => severity === 'high' ? 3 : severity === 'medium' ? 2 : 1;

export default function AnalyticsOpenTrustCasesPanel({
  recentTrustEventsLoading,
  recentTrustEvents,
  recentOpenTrustEvents,
  recentNeedsActionCount,
}: AnalyticsOpenTrustCasesPanelProps) {
  return (
    <div className="bg-gray-900 rounded-xl border border-gray-800 p-4">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-xs text-gray-500 font-medium uppercase tracking-wide">Recent Trust Events</p>
          {recentNeedsActionCount > 0 && (
            <span className="rounded border border-red-500/30 bg-red-500/10 px-2 py-0.5 text-[11px] text-red-300">
              Needs action: {recentNeedsActionCount}
            </span>
          )}
          {recentOpenTrustEvents.length > 0 && (
            <a
              href="http://localhost:3100/DEA/issues?status=backlog"
              target="_blank"
              rel="noreferrer"
              className="text-[11px] text-violet-300 underline underline-offset-2"
              title="Paperclip supports backlog and todo separately, but only backlog is a stable verified single-link filter right now."
            >
              View open trust cases
            </a>
          )}
        </div>
        <span className="text-[11px] text-gray-500">Last {recentTrustEvents.length || 0}</span>
      </div>
      {recentTrustEventsLoading ? (
        <p className="text-sm text-gray-500">Loading trust events...</p>
      ) : recentOpenTrustEvents.length === 0 ? (
        <div className="space-y-2">
          <p className="text-sm text-gray-500">No open trust cases right now</p>
          {recentTrustEvents.length > 0 && (
            <p className="text-xs text-gray-600">Closed or lower-priority trust history is still being tracked in persisted events.</p>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {[...recentOpenTrustEvents]
            .sort((a, b) => {
              const bySeverity = severityRank(b.severity) - severityRank(a.severity);
              if (bySeverity !== 0) return bySeverity;
              return new Date(b.timestamp ?? 0).getTime() - new Date(a.timestamp ?? 0).getTime();
            })
            .map((event) => (
              <div key={event.id ?? `${event.event}-${event.timestamp}`} className="rounded-lg border border-gray-800 bg-gray-950/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`text-[11px] px-2 py-0.5 rounded border ${event.severity === 'high' ? 'border-red-500/30 text-red-300 bg-red-500/10' : event.severity === 'medium' ? 'border-amber-500/30 text-amber-300 bg-amber-500/10' : 'border-sky-500/30 text-sky-300 bg-sky-500/10'}`}>
                      {(event.severity ?? 'low').toUpperCase()}
                    </span>
                    <span className="text-sm text-gray-200">{event.event ?? event.message ?? 'analytics_trust_event'}</span>
                  </div>
                  <span className="text-[11px] text-gray-500">
                    {event.timestamp ? new Date(event.timestamp).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—'}
                  </span>
                </div>
                {event.degraded_sections.length > 0 && (
                  <p className="mt-1 text-xs text-gray-400">
                    Affected: {event.degraded_sections.join(', ')}
                  </p>
                )}
                {event.notes.slice(0, 2).map((note, index) => (
                  <p key={`${event.id ?? event.event}-note-${index}`} className="mt-1 text-xs text-gray-300">
                    {event.rule_ids[index] ? `[${event.rule_ids[index]}] ` : ''}{note}
                  </p>
                ))}
                <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-gray-500">
                  <span>Completeness: {event.completeness_score != null ? `${Math.round(event.completeness_score * 100)}%` : '—'}</span>
                  <span>Freshness age: {event.freshness_age != null ? `${Math.round(event.freshness_age / 3600)}h` : '—'}</span>
                </div>
                {event.paperclip?.status && (
                  <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-gray-400">
                    <span className={`rounded border px-2 py-0.5 ${event.paperclip.status === 'issue_created' ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300' : event.paperclip.status === 'issue_updated' ? 'border-violet-500/20 bg-violet-500/10 text-violet-300' : 'border-gray-500/20 bg-gray-500/10 text-gray-300'}`}>
                      Paperclip {event.paperclip.status === 'issue_created' ? 'created' : event.paperclip.status === 'issue_updated' ? 'updated' : event.paperclip.status.replaceAll('_', ' ')}
                    </span>
                    {event.paperclip.identifier && event.paperclip.issue_id ? (
                      <a
                        href={`http://localhost:3100/DEA/issues/${event.paperclip.issue_id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-violet-300 underline underline-offset-2"
                      >
                        {event.paperclip.identifier}
                      </a>
                    ) : event.paperclip.identifier ? (
                      <span>{event.paperclip.identifier}</span>
                    ) : null}
                    {event.paperclip.issue_status && (
                      <span className={`rounded border px-2 py-0.5 ${event.paperclip.is_open ? 'border-amber-500/20 bg-amber-500/10 text-amber-300' : 'border-gray-700 text-gray-400'}`}>
                        {event.paperclip.is_open ? `open: ${event.paperclip.issue_status}` : `closed: ${event.paperclip.issue_status}`}
                      </span>
                    )}
                    {event.paperclip.title && (
                      <span className="text-gray-500 truncate max-w-full">{event.paperclip.title}</span>
                    )}
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
