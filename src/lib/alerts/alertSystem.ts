/**
 * Production-Grade In-House Alert System
 * Investor-recommended implementation with DB persistence and sound gating
 */

import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';

// ---- Types -------------------------------------------------
export type AlertType = 'hot_deal' | 'price_drop' | 'ending_soon' | 'new_opportunity';
export type AlertPriority = 'critical' | 'high' | 'medium' | 'low';

export interface Opportunity {
  id: string;
  year?: number;
  make?: string;
  model?: string;
  profit?: number;
  roi?: number;
  risk_score?: number;
  confidence?: number;
  state?: string;
  [k: string]: any;
}

export interface InHouseAlert {
  id: string;
  userId: string;
  opportunityId: string;
  type: AlertType;
  title: string;
  message: string;
  opportunity: Opportunity;
  timestamp: string;           // ISO
  dismissed: boolean;
  viewed: boolean;
  priority: AlertPriority;
}

export interface AlertCriteria {
  minProfit: number;
  minROI: number;
  maxRiskScore: number;
  minConfidenceScore: number;
  includeStates?: string[];
  excludeStates?: string[];
  makes?: string[];
}

export interface InHouseAlertConfiguration {
  userId: string;
  enabled: boolean;
  criteria: AlertCriteria;
  frequency: 'immediate' | 'digest';
  soundEnabled: boolean;
  notificationDuration: number; // ms
}

// ---- Implementation ----------------------------------------
export class InHouseAlertSystem {
  private alerts: Map<string, InHouseAlert[]> = new Map();
  private rateLimitAt: Map<string, number> = new Map();
  private audioContext: AudioContext | null = null;
  private soundEnabledGate = false; // enable after first user gesture
  private readonly MAX_ALERTS_PER_USER = 50; // Reduced from 100
  private readonly MAX_RATE_LIMIT_ENTRIES = 100;

  constructor() {
    // Lazy init audio on first user gesture to satisfy autoplay policies
    window.addEventListener('pointerdown', () => {
      if (!this.audioContext) {
        try {
          this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
          this.soundEnabledGate = true;
        } catch {
          this.audioContext = null;
          this.soundEnabledGate = false;
        }
      } else {
        this.soundEnabledGate = true;
      }
    }, { once: true });

    // Setup memory cleanup
    this.setupMemoryCleanup();
  }

  private setupMemoryCleanup(): void {
    // Cleanup old alerts every 5 minutes
    setInterval(() => {
      this.cleanupOldAlerts();
    }, 5 * 60 * 1000);

    // Cleanup rate limit entries every 10 minutes
    setInterval(() => {
      this.cleanupRateLimitEntries();
    }, 10 * 60 * 1000);
  }

  private cleanupOldAlerts(): void {
    const cutoffTime = Date.now() - (24 * 60 * 60 * 1000); // 24 hours ago
    
    for (const [userId, alerts] of this.alerts.entries()) {
      const filteredAlerts = alerts.filter(alert => 
        new Date(alert.timestamp).getTime() > cutoffTime
      );
      
      if (filteredAlerts.length !== alerts.length) {
        this.alerts.set(userId, filteredAlerts);
        console.log(`Cleaned up ${alerts.length - filteredAlerts.length} old alerts for user ${userId}`);
      }
      
      // Also enforce per-user limit
      if (filteredAlerts.length > this.MAX_ALERTS_PER_USER) {
        const trimmedAlerts = filteredAlerts.slice(-this.MAX_ALERTS_PER_USER);
        this.alerts.set(userId, trimmedAlerts);
      }
    }
  }

  private cleanupRateLimitEntries(): void {
    const cutoffTime = Date.now() - (60 * 60 * 1000); // 1 hour ago
    
    for (const [key, timestamp] of this.rateLimitAt.entries()) {
      if (timestamp < cutoffTime) {
        this.rateLimitAt.delete(key);
      }
    }
    
    // Enforce max entries
    if (this.rateLimitAt.size > this.MAX_RATE_LIMIT_ENTRIES) {
      const entries = Array.from(this.rateLimitAt.entries());
      entries.sort(([, a], [, b]) => b - a); // Sort by timestamp desc
      this.rateLimitAt.clear();
      entries.slice(0, this.MAX_RATE_LIMIT_ENTRIES).forEach(([key, timestamp]) => {
        this.rateLimitAt.set(key, timestamp);
      });
    }
  }

  async createAlert(
    opportunity: Opportunity,
    userId: string,
    alertType: AlertType,
  ): Promise<string | 'alerts_disabled' | 'criteria_not_met' | 'rate_limited'> {
    const config = await this.getUserAlertConfig(userId);
    if (!config?.enabled) return 'alerts_disabled';
    if (!this.meetsCriteria(opportunity, config.criteria)) return 'criteria_not_met';
    if (!this.checkRateLimit(userId, alertType)) return 'rate_limited';

    const alert = this.generateAlert(opportunity, userId, alertType);
    await this.storeAlert(alert);
    this.showToast(alert, config);
    if (config.soundEnabled) this.playSound(alert.priority);

    return alert.id;
  }

  private generateAlert(op: Opportunity, userId: string, type: AlertType): InHouseAlert {
    const templates: Record<AlertType, { title: string; message: string; priority: AlertPriority }> = {
      hot_deal: {
        title: '🔥 Hot Deal',
        message: `High profit opportunity: ${op.year ?? ''} ${op.make ?? ''} ${op.model ?? ''}`.trim(),
        priority: 'critical',
      },
      price_drop: {
        title: '💰 Price Drop',
        message: `Bid dropped: ${op.year ?? ''} ${op.make ?? ''} ${op.model ?? ''}`.trim(),
        priority: 'high',
      },
      ending_soon: {
        title: '⏰ Ending Soon',
        message: `Auction ending soon: ${op.year ?? ''} ${op.make ?? ''} ${op.model ?? ''}`.trim(),
        priority: 'medium',
      },
      new_opportunity: {
        title: '🚗 New Opportunity',
        message: `New deal: ${op.year ?? ''} ${op.make ?? ''} ${op.model ?? ''}`.trim(),
        priority: 'low',
      },
    };

    const t = templates[type];

    return {
      id: `alert_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`,
      userId,
      opportunityId: op.id,
      type,
      title: t.title,
      message: t.message,
      opportunity: op,
      timestamp: new Date().toISOString(),
      dismissed: false,
      viewed: false,
      priority: t.priority,
    };
  }

  private async storeAlert(alert: InHouseAlert): Promise<void> {
    // memory (fast UI) - with bounds
    const list = this.alerts.get(alert.userId) ?? [];
    list.unshift(alert);
    
    // Enforce per-user limit immediately
    if (list.length > this.MAX_ALERTS_PER_USER) {
      list.length = this.MAX_ALERTS_PER_USER;
    }
    
    this.alerts.set(alert.userId, list);

    // db (persistence)
    const { error } = await supabase.from('user_alerts').insert({
      id: alert.id,
      user_id: alert.userId,
      opportunity_id: alert.opportunityId,
      type: alert.type,
      title: alert.title,
      message: alert.message,
      priority: alert.priority,
      dismissed: alert.dismissed,
      viewed: alert.viewed,
      created_at: alert.timestamp,
      opportunity_data: alert.opportunity,
    });
    if (error) console.error('storeAlert failed:', error);
  }

  private showToast(alert: InHouseAlert, config: InHouseAlertConfiguration) {
    const opp = alert.opportunity;
    const profit = opp.profit ? `+$${opp.profit.toLocaleString()}` : '';
    const roi = typeof opp.roi === 'number' ? ` • ${opp.roi.toFixed(1)}% ROI` : '';
    toast(`${alert.title}`, {
      description: `${alert.message}${profit || roi ? ` — ${profit}${roi}` : ''}`,
      duration: config.notificationDuration ?? 10000,
      action: {
        label: 'View',
        onClick: () => this.markAlertViewed(alert.id),
      },
    });
  }

  private playSound(priority: AlertPriority): void {
    if (!this.audioContext || !this.soundEnabledGate) return;
    try {
      const osc = this.audioContext.createOscillator();
      const gain = this.audioContext.createGain();
      osc.connect(gain); gain.connect(this.audioContext.destination);

      const table = {
        critical: { f1: 1000, f2: 800, dur: 0.45, vol: 0.35 },
        high:     { f1: 820,  f2: 650, dur: 0.30, vol: 0.30 },
        medium:   { f1: 600,  f2: 520, dur: 0.22, vol: 0.22 },
        low:      { f1: 520,  f2: 420, dur: 0.16, vol: 0.18 },
      }[priority];

      const t0 = this.audioContext.currentTime;
      osc.frequency.setValueAtTime(table.f1, t0);
      osc.frequency.linearRampToValueAtTime(table.f2, t0 + 0.12);
      gain.gain.setValueAtTime(table.vol, t0);
      gain.gain.exponentialRampToValueAtTime(0.001, t0 + table.dur);
      osc.start(t0); osc.stop(t0 + table.dur);
    } catch (e) {
      console.warn('sound failed', e);
    }
  }

  private async getUserAlertConfig(userId: string): Promise<InHouseAlertConfiguration | null> {
    const { data, error } = await supabase
      .from('user_settings')
      .select('*')
      .eq('user_id', userId)
      .single();

    if (error || !data) {
      return {
        userId,
        enabled: true,
        criteria: { minProfit: 2000, minROI: 15, maxRiskScore: 70, minConfidenceScore: 60 },
        frequency: 'immediate',
        soundEnabled: true,
        notificationDuration: 10000,
      };
    }

    return {
      userId,
      enabled: data.notifications_enabled ?? true,
      criteria: {
        minProfit: 2000,
        minROI: data.min_roi_percentage ?? 15,
        maxRiskScore: data.max_risk_score ?? 70,
        minConfidenceScore: 60,
        includeStates: data.preferred_states ?? null,
      },
      frequency: 'immediate',
      soundEnabled: data.sound_enabled ?? true,
      notificationDuration: data.notification_duration ?? 10000,
    };
  }

  private meetsCriteria(op: Opportunity, c: AlertCriteria): boolean {
    if ((op.profit ?? -Infinity) < c.minProfit) return false;
    if ((op.roi ?? -Infinity) < c.minROI) return false;
    if ((op.risk_score ?? Infinity) > c.maxRiskScore) return false;
    if ((op.confidence ?? -Infinity) < c.minConfidenceScore) return false;
    if (c.includeStates?.length && op.state && !c.includeStates.includes(op.state)) return false;
    if (c.excludeStates?.length && op.state && c.excludeStates.includes(op.state)) return false;
    if (c.makes?.length && op.make && !c.makes.includes(op.make)) return false;
    return true;
  }

  private checkRateLimit(userId: string, type: string): boolean {
    const key = `${userId}:${type}`;
    const last = this.rateLimitAt.get(key) ?? 0;
    const MIN = 5 * 60 * 1000; // 5 minutes
    if (Date.now() - last < MIN) return false;
    this.rateLimitAt.set(key, Date.now());
    return true;
  }

  // ---- Public API for UI -----------------------------------
  async getUserAlerts(userId: string, includeViewed = false): Promise<InHouseAlert[]> {
    const local = this.alerts.get(userId) ?? [];
    if (local.length) return includeViewed ? local : local.filter(a => !a.viewed && !a.dismissed);

    // hydrate from DB
    const { data, error } = await supabase
      .from('user_alerts')
      .select('*')
      .eq('user_id', userId)
      .order('created_at', { ascending: false })
      .limit(100);

    if (error || !data) return [];
    const alerts = data.map(row => ({
      id: row.id,
      userId: row.user_id,
      opportunityId: row.opportunity_id,
      type: row.type,
      title: row.title,
      message: row.message,
      opportunity: row.opportunity_data,
      timestamp: row.created_at,
      dismissed: row.dismissed,
      viewed: row.viewed,
      priority: row.priority as AlertPriority,
    } as InHouseAlert));

    this.alerts.set(userId, alerts);
    return includeViewed ? alerts : alerts.filter(a => !a.viewed && !a.dismissed);
  }

  async getUnreadCount(userId: string): Promise<number> {
    const list = await this.getUserAlerts(userId, true);
    return list.filter(a => !a.viewed && !a.dismissed).length;
  }

  async markAlertViewed(alertId: string): Promise<void> {
    // local
    for (const [uid, list] of this.alerts.entries()) {
      const a = list.find(x => x.id === alertId);
      if (a) a.viewed = true;
    }
    // db
    await supabase.from('user_alerts').update({ viewed: true }).eq('id', alertId);
  }

  async dismissAlert(alertId: string): Promise<void> {
    for (const [uid, list] of this.alerts.entries()) {
      const a = list.find(x => x.id === alertId);
      if (a) a.dismissed = true;
    }
    await supabase.from('user_alerts').update({ dismissed: true }).eq('id', alertId);
  }

  async clearAllAlerts(userId: string): Promise<void> {
    const list = this.alerts.get(userId) ?? [];
    list.forEach(a => { a.dismissed = true; a.viewed = true; });
    await supabase.from('user_alerts').update({ dismissed: true, viewed: true })
      .eq('user_id', userId).eq('dismissed', false);
  }

  async updateAlertConfig(userId: string, cfg: Partial<InHouseAlertConfiguration>): Promise<void> {
    await supabase.from('user_settings').upsert({
      user_id: userId,
      notifications_enabled: cfg.enabled,
      min_roi_percentage: cfg.criteria?.minROI,
      max_risk_score: cfg.criteria?.maxRiskScore,
      preferred_states: cfg.criteria?.includeStates,
      sound_enabled: cfg.soundEnabled,
      notification_duration: cfg.notificationDuration,
      updated_at: new Date().toISOString(),
    });
  }
}

export const inHouseAlertSystem = new InHouseAlertSystem();