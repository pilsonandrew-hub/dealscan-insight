/**
 * Strategy Budget Enforcer - Cost bands with hard caps
 * Prevents API cost overruns by enforcing daily limits per site/strategy
 */

import { logger } from '@/lib/logger';
import type { CostBand, BudgetUsage } from '@/types/provenance';

interface BudgetCaps {
  daily: number;
  used: number;
  last_reset: string;
}

type SiteBudgets = Record<CostBand, BudgetCaps>;

class BudgetEnforcer {
  private budgetsBySite = new Map<string, SiteBudgets>();
  private readonly DEFAULT_CAPS: Record<CostBand, number> = {
    http: 1000,      // Free tier
    headless: 500,   // Medium cost
    llm: 100,        // High cost
    captcha: 50      // Highest cost
  };

  /**
   * Initialize budget caps for a site
   */
  private initializeSite(siteId: string, customCaps?: Partial<Record<CostBand, number>>): void {
    if (this.budgetsBySite.has(siteId)) return;

    const caps: SiteBudgets = {} as SiteBudgets;
    const bands: CostBand[] = ['http', 'headless', 'llm', 'captcha'];
    
    for (const band of bands) {
      caps[band] = {
        daily: customCaps?.[band] ?? this.DEFAULT_CAPS[band],
        used: 0,
        last_reset: this.getTodayString()
      };
    }

    this.budgetsBySite.set(siteId, caps);
    logger.info('Initialized budget caps for site', { siteId, caps });
  }

  /**
   * Check if spending is allowed for a given site/band
   */
  canSpend(siteId: string, band: CostBand, units = 1): boolean {
    this.initializeSite(siteId);
    this.resetIfNewDay(siteId);

    const caps = this.budgetsBySite.get(siteId)!;
    const bandCap = caps[band];
    
    const canAfford = (bandCap.used + units) <= bandCap.daily;
    
    if (!canAfford) {
      logger.warn('Budget cap would be exceeded', {
        siteId,
        band,
        requested: units,
        used: bandCap.used,
        daily: bandCap.daily,
        remaining: bandCap.daily - bandCap.used
      });
    }

    return canAfford;
  }

  /**
   * Record spending for a site/band
   */
  spend(siteId: string, band: CostBand, units = 1): void {
    this.initializeSite(siteId);
    this.resetIfNewDay(siteId);

    const caps = this.budgetsBySite.get(siteId)!;
    caps[band].used += units;

    logger.debug('Budget spent', {
      siteId,
      band,
      units,
      totalUsed: caps[band].used,
      dailyLimit: caps[band].daily,
      percentageUsed: (caps[band].used / caps[band].daily * 100).toFixed(1)
    });

    // Alert when approaching limit
    const percentageUsed = caps[band].used / caps[band].daily;
    if (percentageUsed >= 0.8) {
      logger.warn('Budget usage approaching limit', {
        siteId,
        band,
        percentageUsed: (percentageUsed * 100).toFixed(1),
        remaining: caps[band].daily - caps[band].used
      });
    }
  }

  /**
   * Strategy guard - wraps execution with budget checking
   */
  async strategyGuard<T>(
    siteId: string,
    band: CostBand,
    operation: () => Promise<T>,
    units = 1
  ): Promise<T> {
    if (!this.canSpend(siteId, band, units)) {
      throw new Error(`Budget cap exceeded for ${band} on ${siteId}. Daily limit reached.`);
    }

    try {
      const result = await operation();
      this.spend(siteId, band, units);
      return result;
    } catch (error) {
      // Still count failed attempts to prevent retry abuse
      this.spend(siteId, band, units);
      throw error;
    }
  }

  /**
   * Get current budget usage for a site
   */
  getBudgetUsage(siteId: string): Record<CostBand, BudgetUsage> {
    this.initializeSite(siteId);
    this.resetIfNewDay(siteId);

    const caps = this.budgetsBySite.get(siteId)!;
    const usage: Record<CostBand, BudgetUsage> = {} as Record<CostBand, BudgetUsage>;

    for (const [band, cap] of Object.entries(caps) as [CostBand, BudgetCaps][]) {
      usage[band] = {
        site_id: siteId,
        cost_band: band,
        daily_limit: cap.daily,
        current_usage: cap.used,
        percentage_used: (cap.used / cap.daily) * 100,
        last_reset: cap.last_reset,
        projected_daily_usage: this.projectDailyUsage(cap),
        budget_exhausted: cap.used >= cap.daily
      };
    }

    return usage;
  }

  /**
   * Set custom budget limits for a site
   */
  setBudgetLimits(siteId: string, limits: Partial<Record<CostBand, number>>): void {
    this.initializeSite(siteId, limits);
    
    const caps = this.budgetsBySite.get(siteId)!;
    for (const [band, limit] of Object.entries(limits) as [CostBand, number][]) {
      if (caps[band]) {
        caps[band].daily = limit;
        logger.info('Updated budget limit', { siteId, band, newLimit: limit });
      }
    }
  }

  /**
   * Get sites approaching budget limits
   */
  getSitesApproachingLimits(threshold = 0.8): Array<{ siteId: string; band: CostBand; usage: BudgetUsage }> {
    const approaching: Array<{ siteId: string; band: CostBand; usage: BudgetUsage }> = [];

    for (const [siteId] of this.budgetsBySite) {
      const usage = this.getBudgetUsage(siteId);
      
      for (const [band, bandUsage] of Object.entries(usage) as [CostBand, BudgetUsage][]) {
        if (bandUsage.percentage_used >= threshold * 100) {
          approaching.push({ siteId, band, usage: bandUsage });
        }
      }
    }

    return approaching;
  }

  /**
   * Reset budgets if it's a new day
   */
  private resetIfNewDay(siteId: string): void {
    const caps = this.budgetsBySite.get(siteId);
    if (!caps) return;

    const today = this.getTodayString();
    
    for (const [band, cap] of Object.entries(caps) as [CostBand, BudgetCaps][]) {
      if (cap.last_reset !== today) {
        cap.used = 0;
        cap.last_reset = today;
        logger.info('Budget reset for new day', { siteId, band, today });
      }
    }
  }

  /**
   * Project daily usage based on current time and usage
   */
  private projectDailyUsage(cap: BudgetCaps): number {
    const now = new Date();
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    
    const hoursElapsed = (now.getTime() - startOfDay.getTime()) / (1000 * 60 * 60);
    const hoursInDay = 24;
    
    if (hoursElapsed === 0) return cap.used;
    
    return Math.round((cap.used / hoursElapsed) * hoursInDay);
  }

  /**
   * Get today's date string for budget tracking
   */
  private getTodayString(): string {
    return new Date().toISOString().split('T')[0];
  }

  /**
   * Clear all budgets (for testing)
   */
  clearBudgets(): void {
    this.budgetsBySite.clear();
    logger.info('All budgets cleared');
  }
}

// Singleton instance
export const budgetEnforcer = new BudgetEnforcer();

// Export for testing
export { BudgetEnforcer };