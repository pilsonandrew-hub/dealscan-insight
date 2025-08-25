/**
 * Advanced Alert System for High-Profit Deals
 * Implements email/SMS alerts based on investor requirements
 */

import { supabase } from '@/integrations/supabase/client';
import { Opportunity } from '@/types/dealerscope';

export interface AlertConfiguration {
  userId: string;
  enabled: boolean;
  channels: ('email' | 'sms' | 'push' | 'webhook')[];
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
  quietHours?: {
    enabled: boolean;
    startTime: string; // HH:MM
    endTime: string;   // HH:MM
    timezone: string;
  };
}

export interface AlertTemplate {
  id: string;
  name: string;
  type: 'high_profit' | 'breaking_news' | 'price_drop' | 'ending_soon' | 'new_listing';
  subject: string;
  emailTemplate: string;
  smsTemplate: string;
  pushTemplate: string;
}

export interface AlertDelivery {
  id: string;
  userId: string;
  opportunityId: string;
  channel: string;
  status: 'pending' | 'sent' | 'failed' | 'opened' | 'clicked';
  sentAt?: string;
  openedAt?: string;
  clickedAt?: string;
  errorMessage?: string;
}

export class AlertSystem {
  private templates: Map<string, AlertTemplate> = new Map();
  private deliveryQueue: AlertDelivery[] = [];
  private rateLimits: Map<string, number> = new Map();
  private isProcessing = false;

  constructor() {
    this.initializeTemplates();
    this.startDeliveryProcessor();
  }

  private initializeTemplates(): void {
    const templates: AlertTemplate[] = [
      {
        id: 'high_profit',
        name: 'High Profit Opportunity',
        type: 'high_profit',
        subject: '🚨 HIGH PROFIT ALERT: {{make}} {{model}} - ${{profit}} profit potential',
        emailTemplate: 
          '<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">' +
            '<div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; text-align: center;">' +
              '<h1>🚨 HIGH PROFIT OPPORTUNITY 🚨</h1>' +
              '<h2>{{year}} {{make}} {{model}}</h2>' +
            '</div>' +
            '<div style="padding: 20px; background: #f8f9fa;">' +
              '<div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">' +
                '<h3 style="color: #28a745; margin-top: 0;">💰 Profit Estimate: ${{profit}}</h3>' +
                '<div style="display: flex; justify-content: space-between; margin: 15px 0;">' +
                  '<div>' +
                    '<strong>ROI:</strong> {{roi}}%<br>' +
                    '<strong>Current Bid:</strong> ${{currentBid}}<br>' +
                    '<strong>Estimated Sale:</strong> ${{estimatedSale}}' +
                  '</div>' +
                  '<div>' +
                    '<strong>Risk Score:</strong> {{riskScore}}/100<br>' +
                    '<strong>Confidence:</strong> {{confidence}}%<br>' +
                    '<strong>Location:</strong> {{location}}' +
                  '</div>' +
                '</div>' +
                '<div style="background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 15px 0;">' +
                  '<h4 style="margin-top: 0;">📊 Deal Details</h4>' +
                  '<p><strong>Year:</strong> {{year}}</p>' +
                  '<p><strong>Mileage:</strong> {{mileage}} miles</p>' +
                  '<p><strong>Auction Ends:</strong> {{auctionEnd}}</p>' +
                  '<p><strong>Source:</strong> {{sourceSite}}</p>' +
                '</div>' +
                '<div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 15px 0;">' +
                  '<h4 style="margin-top: 0;">🎯 Why This is a Good Deal</h4>' +
                  '<p>{{dealRationale}}</p>' +
                '</div>' +
                '<div style="text-align: center; margin: 25px 0;">' +
                  '<a href="{{listingUrl}}" style="background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold;">VIEW LISTING</a>' +
                '</div>' +
                '<div style="font-size: 12px; color: #6c757d; text-align: center; border-top: 1px solid #dee2e6; padding-top: 15px; margin-top: 20px;">' +
                  'This alert was sent because this opportunity meets your criteria: Min Profit ${{minProfit}}, Min ROI {{minROI}}%' +
                  '<br><a href="{{unsubscribeUrl}}">Unsubscribe</a> | <a href="{{settingsUrl}}">Alert Settings</a>' +
                '</div>' +
              '</div>' +
            '</div>' +
          '</div>',
        smsTemplate: '🚨 HIGH PROFIT: {{year}} {{make}} {{model}} - ${{profit}} profit ({{roi}}% ROI) in {{location}}. Ends {{auctionEnd}}. View: {{shortUrl}}',
        pushTemplate: '{{year}} {{make}} {{model}} - ${{profit}} profit potential ({{roi}}% ROI)'
      },
      {
        id: 'ending_soon',
        name: 'Auction Ending Soon',
        type: 'ending_soon',
        subject: '⏰ ENDING SOON: {{make}} {{model}} auction ends in {{timeLeft}}',
        emailTemplate: `Template for ending soon alerts`,
        smsTemplate: '⏰ {{make}} {{model}} auction ends in {{timeLeft}}! Current bid: ${{currentBid}}. Max bid: ${{maxBid}}.',
        pushTemplate: 'Auction ending in {{timeLeft}}: {{year}} {{make}} {{model}}'
      },
      {
        id: 'price_drop',
        name: 'Significant Price Drop',
        type: 'price_drop',
        subject: '📉 PRICE DROP: {{make}} {{model}} bid dropped {{dropAmount}}',
        emailTemplate: `Template for price drop alerts`,
        smsTemplate: '📉 {{make}} {{model}} bid dropped {{dropAmount}}! New bid: ${{currentBid}}. New profit: ${{newProfit}}.',
        pushTemplate: 'Bid dropped {{dropAmount}} on {{year}} {{make}} {{model}}'
      }
    ];

    templates.forEach(template => this.templates.set(template.id, template));
  }

  async createAlert(
    opportunity: Opportunity,
    userId: string,
    alertType: 'high_profit' | 'ending_soon' | 'price_drop' | 'new_listing',
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

    // Check quiet hours
    if (this.isQuietHours(config.quietHours)) {
      return 'quiet_hours';
    }

    // Check rate limits
    if (!this.checkRateLimit(userId, alertType)) {
      return 'rate_limited';
    }

    // Generate alert ID
    const alertId = `alert_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Create delivery records for each enabled channel
    for (const channel of config.channels) {
      const delivery: AlertDelivery = {
        id: `delivery_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`,
        userId,
        opportunityId: opportunity.id || '',
        channel,
        status: 'pending'
      };

      this.deliveryQueue.push(delivery);
    }

    // Start processing if not already running
    if (!this.isProcessing) {
      this.processDeliveryQueue();
    }

    // Log alert creation
    await this.logAlert(alertId, userId, opportunity.id || '', alertType, context);

    return alertId;
  }

  private async getUserAlertConfig(userId: string): Promise<AlertConfiguration | null> {
    try {
      const { data, error } = await supabase
        .from('user_settings')
        .select('*')
        .eq('user_id', userId)
        .single();

      if (error || !data) {
        // Return default configuration
        return {
          userId,
          enabled: true,
          channels: ['email'],
          criteria: {
            minProfit: 2000,
            minROI: 15,
            maxRiskScore: 70,
            minConfidenceScore: 60
          },
          frequency: 'immediate'
        };
      }

      // Convert user_settings to AlertConfiguration
      return {
        userId,
        enabled: data.notifications_enabled ?? true,
        channels: data.enabled_sites?.includes('email') ? ['email'] : [],
        criteria: {
          minProfit: 2000,
          minROI: data.min_roi_percentage || 15,
          maxRiskScore: data.max_risk_score || 70,
          minConfidenceScore: 60,
          includeStates: data.preferred_states
        },
        frequency: 'immediate'
      };
    } catch (error) {
      console.error('Error fetching user alert config:', error);
      return null;
    }
  }

  private meetsCriteria(opportunity: Opportunity, criteria: AlertConfiguration['criteria']): boolean {
    // Check minimum profit
    if (opportunity.profit < criteria.minProfit) return false;

    // Check minimum ROI
    if (opportunity.roi < criteria.minROI) return false;

    // Check maximum risk score
    if (opportunity.risk_score > criteria.maxRiskScore) return false;

    // Check minimum confidence
    if (opportunity.confidence < criteria.minConfidenceScore) return false;

    // Check state inclusion/exclusion
    if (criteria.includeStates && criteria.includeStates.length > 0) {
      if (!criteria.includeStates.includes(opportunity.state || '')) return false;
    }

    if (criteria.excludeStates && criteria.excludeStates.length > 0) {
      if (criteria.excludeStates.includes(opportunity.state || '')) return false;
    }

    // Check makes
    if (criteria.makes && criteria.makes.length > 0) {
      if (!criteria.makes.includes(opportunity.make)) return false;
    }

    return true;
  }

  private isQuietHours(quietHours?: AlertConfiguration['quietHours']): boolean {
    if (!quietHours?.enabled) return false;

    const now = new Date();
    const currentTime = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;
    
    return currentTime >= quietHours.startTime && currentTime <= quietHours.endTime;
  }

  private checkRateLimit(userId: string, alertType: string): boolean {
    const key = `${userId}_${alertType}`;
    const lastSent = this.rateLimits.get(key) || 0;
    const minInterval = 10 * 60 * 1000; // 10 minutes between similar alerts
    
    if (Date.now() - lastSent < minInterval) {
      return false;
    }

    this.rateLimits.set(key, Date.now());
    return true;
  }

  private async processDeliveryQueue(): Promise<void> {
    this.isProcessing = true;

    while (this.deliveryQueue.length > 0) {
      const delivery = this.deliveryQueue.shift()!;
      
      try {
        await this.sendAlert(delivery);
        delivery.status = 'sent';
        delivery.sentAt = new Date().toISOString();
      } catch (error) {
        console.error('Failed to send alert:', error);
        delivery.status = 'failed';
        delivery.errorMessage = error.message;
      }

      // Store delivery record
      await this.storeDeliveryRecord(delivery);

      // Rate limiting between sends
      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    this.isProcessing = false;
  }

  private async sendAlert(delivery: AlertDelivery): Promise<void> {
    switch (delivery.channel) {
      case 'email':
        await this.sendEmail(delivery);
        break;
      case 'sms':
        await this.sendSMS(delivery);
        break;
      case 'push':
        await this.sendPush(delivery);
        break;
      case 'webhook':
        await this.sendWebhook(delivery);
        break;
      default:
        throw new Error(`Unsupported channel: ${delivery.channel}`);
    }
  }

  private async sendEmail(delivery: AlertDelivery): Promise<void> {
    // In production, integrate with services like SendGrid, Mailgun, or AWS SES
    console.log(`📧 Sending email alert for opportunity ${delivery.opportunityId} to user ${delivery.userId}`);
    
    // Simulate email sending
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // 5% chance of failure for simulation
    if (Math.random() < 0.05) {
      throw new Error('SMTP server temporarily unavailable');
    }
  }

  private async sendSMS(delivery: AlertDelivery): Promise<void> {
    // In production, integrate with Twilio, AWS SNS, or similar
    console.log(`📱 Sending SMS alert for opportunity ${delivery.opportunityId} to user ${delivery.userId}`);
    
    await new Promise(resolve => setTimeout(resolve, 300));
    
    if (Math.random() < 0.03) {
      throw new Error('SMS delivery failed - invalid phone number');
    }
  }

  private async sendPush(delivery: AlertDelivery): Promise<void> {
    // In production, integrate with Firebase Cloud Messaging or similar
    console.log(`🔔 Sending push notification for opportunity ${delivery.opportunityId} to user ${delivery.userId}`);
    
    await new Promise(resolve => setTimeout(resolve, 200));
  }

  private async sendWebhook(delivery: AlertDelivery): Promise<void> {
    // In production, send HTTP POST to user's webhook URL
    console.log(`🌐 Sending webhook for opportunity ${delivery.opportunityId} to user ${delivery.userId}`);
    
    await new Promise(resolve => setTimeout(resolve, 400));
  }

  private async logAlert(
    alertId: string,
    userId: string,
    opportunityId: string,
    alertType: string,
    context: Record<string, any>
  ): Promise<void> {
    try {
      await supabase
        .from('security_audit_log')
        .insert({
          user_id: userId,
          action: 'alert_created',
          resource: `opportunity:${opportunityId}`,
          status: 'info',
          details: {
            alertId,
            alertType,
            context,
            timestamp: new Date().toISOString()
          }
        });
    } catch (error) {
      console.error('Failed to log alert:', error);
    }
  }

  private async storeDeliveryRecord(delivery: AlertDelivery): Promise<void> {
    // In production, store in a dedicated alerts/notifications table
    console.log(`📊 Storing delivery record: ${delivery.id} - ${delivery.status}`);
  }

  private startDeliveryProcessor(): void {
    // Process delivery queue every 30 seconds
    setInterval(() => {
      if (!this.isProcessing && this.deliveryQueue.length > 0) {
        this.processDeliveryQueue();
      }
    }, 30000);
  }

  // Public API methods
  async updateUserAlertConfig(userId: string, config: Partial<AlertConfiguration>): Promise<void> {
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

  async getAlertHistory(userId: string, limit = 50): Promise<AlertDelivery[]> {
    // In production, query from alerts/notifications table
    return [];
  }

  async testAlert(userId: string, alertType: string): Promise<boolean> {
    // Send a test alert to verify configuration
    const testOpportunity: Opportunity = {
      id: 'test_opportunity',
      vehicle: {
        vin: 'TEST123456789',
        make: 'Toyota',
        model: 'Camry',
        year: 2020,
        mileage: 50000
      },
      make: 'Toyota',
      model: 'Camry',
      year: 2020,
      mileage: 50000,
      current_bid: 12000,
      expected_price: 18000,
      acquisition_cost: 13500,
      profit: 4500,
      roi: 33.3,
      confidence: 85,
      risk_score: 25,
      total_cost: 13500,
      transportation_cost: 800,
      fees_cost: 700,
      estimated_sale_price: 18000,
      profit_margin: 25,
      source_site: 'Test Site',
      state: 'CA'
    };

    const result = await this.createAlert(testOpportunity, userId, alertType as any, { test: true });
    return result !== 'alerts_disabled' && result !== 'criteria_not_met';
  }
}

export const alertSystem = new AlertSystem();