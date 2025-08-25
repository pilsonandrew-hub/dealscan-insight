/**
 * In-House Alert System for High-Profit Deals
 * Uses only in-app notifications with red bubble inbox system
 */

import { supabase } from '@/integrations/supabase/client';
import { toast } from 'sonner';
import { Opportunity } from '@/types/dealerscope';

export interface InHouseAlertConfiguration {
  userId: string;
  enabled: boolean;
  criteria: {
    minProfit: number;
    minROI: number;
    maxRiskScore: number;
    minConfidenceScore: number;
    includeStates?: string[];
    excludeStates?: string[];
    makes?: string[];
    categories?: string[];
  };
  frequency: 'immediate' | 'hourly' | 'daily';
  soundEnabled: boolean;
  notificationDuration: number;
}

export interface InHouseAlert {
  id: string;
  userId: string;
  opportunityId: string;
  type: 'hot_deal' | 'price_drop' | 'ending_soon' | 'new_opportunity';
  message: string;
  title: string;
  opportunity: Opportunity;
  timestamp: Date;
  dismissed: boolean;
  viewed: boolean;
  priority: 'low' | 'medium' | 'high' | 'critical';
}

export class InHouseAlertSystem {
  private alerts: Map<string, InHouseAlert[]> = new Map();
  private rateLimits: Map<string, number> = new Map();
  private audioContext: AudioContext | null = null;

  constructor() {
    this.initializeAudioContext();
  }

  private initializeAudioContext(): void {
    try {
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    } catch (error) {
      console.warn('Audio context not available:', error);
    }
  }

  async createInHouseAlert(
    opportunity: Opportunity,
    userId: string,
    alertType: 'hot_deal' | 'price_drop' | 'ending_soon' | 'new_opportunity',
    context: Record<string, any> = {}
  ): Promise<string> {
    // Get user alert configuration
    const config = await this.getUserAlertConfig(userId);
    if (!config || !config.enabled) {
      return 'alerts_disabled';
    }

    // Check if opportunity meets user criteria
    if (!this.meetsCriteria(opportunity, config.criteria)) {
      return 'criteria_not_met';
    }

    // Check rate limits
    if (!this.checkRateLimit(userId, alertType)) {
      return 'rate_limited';
    }

    // Generate alert
    const alert = this.generateAlert(opportunity, userId, alertType);
    
    // Store in memory and database
    await this.storeAlert(alert);
    
    // Show immediate toast notification
    this.showToastNotification(alert, config);
    
    // Play sound if enabled
    if (config.soundEnabled) {
      this.playNotificationSound(alert.priority);
    }

    return alert.id;
  }

  private generateAlert(
    opportunity: Opportunity,
    userId: string,
    type: InHouseAlert['type']
  ): InHouseAlert {
    const alertMessages = {
      hot_deal: {
        title: '🔥 Hot Deal Alert!',
        message: `High profit opportunity: ${opportunity.year} ${opportunity.make} ${opportunity.model}`,
        priority: 'critical' as const
      },
      price_drop: {
        title: '💰 Price Drop!',
        message: `Bid dropped on ${opportunity.year} ${opportunity.make} ${opportunity.model}`,
        priority: 'high' as const
      },
      ending_soon: {
        title: '⏰ Ending Soon',
        message: `Auction ending soon: ${opportunity.year} ${opportunity.make} ${opportunity.model}`,
        priority: 'medium' as const
      },
      new_opportunity: {
        title: '🚗 New Opportunity',
        message: `New deal found: ${opportunity.year} ${opportunity.make} ${opportunity.model}`,
        priority: 'low' as const
      }
    };

    const template = alertMessages[type];
    
    return {
      id: `alert_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      userId,
      opportunityId: opportunity.id || '',
      type,
      title: template.title,
      message: template.message,
      opportunity,
      timestamp: new Date(),
      dismissed: false,
      viewed: false,
      priority: template.priority
    };
  }

  private async storeAlert(alert: InHouseAlert): Promise<void> {
    // Store in memory
    const userAlerts = this.alerts.get(alert.userId) || [];
    userAlerts.unshift(alert);
    
    // Keep only last 100 alerts per user
    if (userAlerts.length > 100) {
      userAlerts.splice(100);
    }
    
    this.alerts.set(alert.userId, userAlerts);

    // Log alert storage
    console.log(`Stored alert: ${alert.id} for user ${alert.userId}`);
  }

  private showToastNotification(alert: InHouseAlert, config: InHouseAlertConfiguration): void {
    const getIcon = () => {
      switch (alert.type) {
        case 'hot_deal': return '🔥';
        case 'price_drop': return '💰';
        case 'ending_soon': return '⏰';
        case 'new_opportunity': return '🚗';
        default: return '📢';
      }
    };

    const getProfitInfo = () => {
      const opp = alert.opportunity;
      return `$${opp.profit?.toLocaleString() || 0} profit (${opp.roi?.toFixed(1) || 0}% ROI)`;
    };

    toast.success(`${getIcon()} ${alert.title}`, {
      description: `${alert.message} - ${getProfitInfo()}`,
      action: {
        label: 'View Deal',
        onClick: () => {
          this.markAlertViewed(alert.id);
          // Navigate to deal (handled by parent component)
          const element = document.getElementById(`deal-${alert.opportunityId}`);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }
      },
      duration: config.notificationDuration || 10000
    });
  }

  private playNotificationSound(priority: InHouseAlert['priority']): void {
    if (!this.audioContext) return;

    try {
      const oscillator = this.audioContext.createOscillator();
      const gainNode = this.audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(this.audioContext.destination);
      
      // Different sounds for different priorities
      const soundConfig = {
        critical: { freq1: 1000, freq2: 800, duration: 0.5, volume: 0.4 },
        high: { freq1: 800, freq2: 600, duration: 0.3, volume: 0.3 },
        medium: { freq1: 600, freq2: 500, duration: 0.2, volume: 0.25 },
        low: { freq1: 500, freq2: 400, duration: 0.15, volume: 0.2 }
      };

      const config = soundConfig[priority];
      
      oscillator.frequency.setValueAtTime(config.freq1, this.audioContext.currentTime);
      oscillator.frequency.setValueAtTime(config.freq2, this.audioContext.currentTime + 0.1);
      
      gainNode.gain.setValueAtTime(config.volume, this.audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.001, this.audioContext.currentTime + config.duration);
      
      oscillator.start(this.audioContext.currentTime);
      oscillator.stop(this.audioContext.currentTime + config.duration);
    } catch (error) {
      console.warn('Failed to play notification sound:', error);
    }
  }

  private async getUserAlertConfig(userId: string): Promise<InHouseAlertConfiguration | null> {
    try {
      const { data, error } = await supabase
        .from('user_settings')
        .select('*')
        .eq('user_id', userId)
        .single();

      if (error || !data) {
        return {
          userId,
          enabled: true,
          criteria: {
            minProfit: 2000,
            minROI: 15,
            maxRiskScore: 70,
            minConfidenceScore: 60
          },
          frequency: 'immediate',
          soundEnabled: true,
          notificationDuration: 10000
        };
      }

      return {
        userId,
        enabled: data.notifications_enabled ?? true,
        criteria: {
          minProfit: 2000,
          minROI: data.min_roi_percentage || 15,
          maxRiskScore: data.max_risk_score || 70,
          minConfidenceScore: 60,
          includeStates: data.preferred_states
        },
        frequency: 'immediate',
        soundEnabled: true,
        notificationDuration: 10000
      };
    } catch (error) {
      console.error('Error fetching user alert config:', error);
      return null;
    }
  }

  private meetsCriteria(opportunity: Opportunity, criteria: InHouseAlertConfiguration['criteria']): boolean {
    if (opportunity.profit < criteria.minProfit) return false;
    if (opportunity.roi < criteria.minROI) return false;
    if (opportunity.risk_score > criteria.maxRiskScore) return false;
    if (opportunity.confidence < criteria.minConfidenceScore) return false;

    if (criteria.includeStates && criteria.includeStates.length > 0) {
      if (!criteria.includeStates.includes(opportunity.state || '')) return false;
    }

    if (criteria.excludeStates && criteria.excludeStates.length > 0) {
      if (criteria.excludeStates.includes(opportunity.state || '')) return false;
    }

    if (criteria.makes && criteria.makes.length > 0) {
      if (!criteria.makes.includes(opportunity.make)) return false;
    }

    return true;
  }

  private checkRateLimit(userId: string, alertType: string): boolean {
    const key = `${userId}_${alertType}`;
    const lastSent = this.rateLimits.get(key) || 0;
    const minInterval = 5 * 60 * 1000; // 5 minutes between similar alerts
    
    if (Date.now() - lastSent < minInterval) {
      return false;
    }

    this.rateLimits.set(key, Date.now());
    return true;
  }

  // Public API methods
  async getUserAlerts(userId: string, includeViewed = false): Promise<InHouseAlert[]> {
    const userAlerts = this.alerts.get(userId) || [];
    return includeViewed ? userAlerts : userAlerts.filter(alert => !alert.viewed);
  }

  async getUnreadCount(userId: string): Promise<number> {
    const userAlerts = this.alerts.get(userId) || [];
    return userAlerts.filter(alert => !alert.dismissed && !alert.viewed).length;
  }

  async markAlertViewed(alertId: string): Promise<void> {
    for (const [userId, userAlerts] of this.alerts.entries()) {
      const alert = userAlerts.find(a => a.id === alertId);
      if (alert) {
        alert.viewed = true;
        
        // Log alert viewed
        console.log(`Alert ${alertId} marked as viewed`);
        break;
      }
    }
  }

  async dismissAlert(alertId: string): Promise<void> {
    for (const [userId, userAlerts] of this.alerts.entries()) {
      const alert = userAlerts.find(a => a.id === alertId);
      if (alert) {
        alert.dismissed = true;
        
        // Log alert dismissed
        console.log(`Alert ${alertId} dismissed`);
        break;
      }
    }
  }

  async clearAllAlerts(userId: string): Promise<void> {
    const userAlerts = this.alerts.get(userId) || [];
    userAlerts.forEach(alert => alert.dismissed = true);
    
    // Log alerts cleared
    console.log(`All alerts cleared for user ${userId}`);
  }

  async updateAlertConfig(userId: string, config: Partial<InHouseAlertConfiguration>): Promise<void> {
    try {
      await supabase
        .from('user_settings')
        .upsert({
          user_id: userId,
          notifications_enabled: config.enabled,
          min_roi_percentage: config.criteria?.minROI,
          max_risk_score: config.criteria?.maxRiskScore,
          preferred_states: config.criteria?.includeStates,
          updated_at: new Date().toISOString()
        });
    } catch (error) {
      console.error('Failed to update alert config:', error);
      throw error;
    }
  }
}

export const inHouseAlertSystem = new InHouseAlertSystem();
