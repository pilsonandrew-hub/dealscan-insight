/**
 * Production-Grade Alert Inbox Component
 * Investor-recommended implementation with proper icons and accessibility
 */

import React, { useEffect, useState } from 'react';
import { Bell, Flame, DollarSign, Clock, Car, X, Check } from 'lucide-react';
import { inHouseAlertSystem, InHouseAlert } from '@/lib/alerts/alertSystem';
import { toast } from 'sonner';

type Props = { userId: string; onAlertClick?: (a: InHouseAlert) => void };

export function AlertInbox({ userId, onAlertClick }: Props) {
  const [alerts, setAlerts] = useState<InHouseAlert[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      const list = await inHouseAlertSystem.getUserAlerts(userId, true);
      setAlerts(list);
      const n = await inHouseAlertSystem.getUnreadCount(userId);
      setUnread(n);
      setLoading(false);
    };
    load();
    const id = setInterval(load, 30000);
    return () => clearInterval(id);
  }, [userId]);

  const refreshCounts = async () => setUnread(await inHouseAlertSystem.getUnreadCount(userId));

  const handleViewed = async (a: InHouseAlert) => {
    await inHouseAlertSystem.markAlertViewed(a.id);
    await refreshCounts();
    onAlertClick?.(a);
    setOpen(false);
  };

  const handleDismiss = async (a: InHouseAlert, e: React.MouseEvent) => {
    e.stopPropagation();
    await inHouseAlertSystem.dismissAlert(a.id);
    setAlerts(await inHouseAlertSystem.getUserAlerts(userId, true));
    await refreshCounts();
    toast.success('Alert dismissed');
  };

  const clearAll = async () => {
    await inHouseAlertSystem.clearAllAlerts(userId);
    setAlerts(await inHouseAlertSystem.getUserAlerts(userId, true));
    await refreshCounts();
    toast.success('All alerts cleared');
  };

  const iconFor = (t: InHouseAlert['type']) => {
    switch (t) {
      case 'hot_deal': return <Flame className="h-4 w-4 text-red-500" />;
      case 'price_drop': return <DollarSign className="h-4 w-4 text-emerald-600" />;
      case 'ending_soon': return <Clock className="h-4 w-4 text-yellow-600" />;
      case 'new_opportunity': return <Car className="h-4 w-4 text-sky-600" />;
      default: return <Bell className="h-4 w-4" />;
    }
  };

  const badgeFor = (p: InHouseAlert['priority']) => {
    const map = {
      critical: 'bg-red-500 text-white',
      high: 'bg-orange-500 text-white',
      medium: 'bg-yellow-500 text-white',
      low: 'bg-gray-500 text-white',
    } as const;
    return map[p] || map.low;
  };

  const since = (iso: string) => {
    const t = new Date(iso).getTime(), now = Date.now();
    const m = Math.floor((now - t) / 60000), h = Math.floor(m / 60);
    if (m < 60) return `${m}m ago`;
    if (h < 24) return `${h}h ago`;
    return new Date(iso).toLocaleDateString();
  };

  return (
    <div className="relative">
      {/* Bell + red bubble */}
      <button
        onClick={() => setOpen(!open)}
        className="relative inline-flex items-center justify-center rounded-full p-2 hover:bg-muted/50 transition-colors"
        aria-label="Open alerts"
      >
        <Bell className="h-6 w-6" />
        {unread > 0 && (
          <span className="absolute -top-1 -right-1 rounded-full bg-red-500 text-white text-[10px] px-1.5 py-0.5 animate-pulse">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 z-50 mt-2 w-[28rem] rounded-xl border bg-background shadow-lg">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div className="font-semibold">Deal Alerts {unread > 0 && <span className="ml-2 text-sm text-muted-foreground">({unread} new)</span>}</div>
            <div className="flex gap-2">
              {alerts.length > 0 && (
                <button onClick={clearAll} className="text-xs text-muted-foreground hover:text-foreground transition-colors">Clear All</button>
              )}
              <button onClick={() => setOpen(false)} aria-label="Close"><X className="h-4 w-4" /></button>
            </div>
          </div>

          <div className="max-h-[26rem] overflow-auto divide-y">
            {loading ? (
              <div className="p-6 text-sm text-muted-foreground">Loading alerts…</div>
            ) : alerts.length === 0 ? (
              <div className="p-6 text-center text-sm text-muted-foreground">
                <div className="mb-1 font-medium">No alerts yet</div>
                <div>You'll be notified of new opportunities here.</div>
              </div>
            ) : (
              alerts.map((a) => {
                const opp = a.opportunity ?? {} as any;
                const vehicle = [opp.year, opp.make, opp.model].filter(Boolean).join(' ');
                return (
                  <button key={a.id} onClick={() => handleViewed(a)} className="w-full text-left px-4 py-3 hover:bg-muted/50 transition-colors">
                    <div className="flex items-start gap-3">
                      <div className="mt-0.5">{iconFor(a.type)}</div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <div className="font-medium">{a.title}</div>
                          <span className={`rounded px-1.5 py-0.5 text-[10px] ${badgeFor(a.priority)}`}>{a.priority}</span>
                          {!a.viewed && <Check className="h-3 w-3 text-sky-600" aria-label="unread" />}
                          <div className="ml-auto text-xs text-muted-foreground">{since(a.timestamp)}</div>
                        </div>
                        <div className="text-sm text-muted-foreground">{a.message}</div>
                        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                          <span>{vehicle}</span>
                          {typeof opp.profit === 'number' && <span className="font-medium text-green-600">+${opp.profit.toLocaleString()}</span>}
                          {typeof opp.roi === 'number' && <span>{opp.roi.toFixed(1)}% ROI</span>}
                        </div>
                      </div>
                      <button
                        onClick={(e) => handleDismiss(a, e)}
                        className="ml-2 rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
                        aria-label="Dismiss"
                      >
                        <X className="h-4 w-4" />
                      </button>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}