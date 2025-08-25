import { supabase } from '@/integrations/supabase/client';
import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('CostController');

export interface StrategyBudget {
  dailyHttpRequests: number;
  dailyHeadlessMinutes: number;
  dailyLLMTokens: number;
  dailyCaptchaSolves: number;
  monthlyTotalCost: number;
}

export interface SiteBudget {
  siteName: string;
  strategy: 'http' | 'headless' | 'hybrid';
  dailyBudget: StrategyBudget;
  currentUsage: StrategyBudget;
  utilizationPercent: number;
  status: 'under_budget' | 'near_limit' | 'over_budget' | 'blocked';
}

export interface CostMetrics {
  httpRequestCost: number; // Per request
  headlessMinuteCost: number; // Per minute
  llmTokenCost: number; // Per 1k tokens
  captchaSolveCost: number; // Per solve
}

/**
 * Cost control and strategy budget management system
 * Implements per-site daily caps and automatic strategy downgrading
 */
export class CostController {
  private static readonly DEFAULT_COSTS: CostMetrics = {
    httpRequestCost: 0.001, // $0.001 per request
    headlessMinuteCost: 0.05, // $0.05 per minute
    llmTokenCost: 0.002, // $0.002 per 1k tokens
    captchaSolveCost: 0.10 // $0.10 per CAPTCHA solve
  };

  private static readonly DEFAULT_DAILY_BUDGETS: Record<string, StrategyBudget> = {
    'high_value': {
      dailyHttpRequests: 10000,
      dailyHeadlessMinutes: 120,
      dailyLLMTokens: 100000,
      dailyCaptchaSolves: 50,
      monthlyTotalCost: 500
    },
    'medium_value': {
      dailyHttpRequests: 5000,
      dailyHeadlessMinutes: 60,
      dailyLLMTokens: 50000,
      dailyCaptchaSolves: 25,
      monthlyTotalCost: 250
    },
    'low_value': {
      dailyHttpRequests: 2000,
      dailyHeadlessMinutes: 30,
      dailyLLMTokens: 20000,
      dailyCaptchaSolves: 10,
      monthlyTotalCost: 100
    }
  };

  private costs: CostMetrics;
  private siteBudgets: Map<string, SiteBudget> = new Map();

  constructor(customCosts?: Partial<CostMetrics>) {
    this.costs = { ...CostController.DEFAULT_COSTS, ...customCosts };
  }

  /**
   * Initialize site budgets from database configuration
   */
  async initializeSiteBudgets(): Promise<void> {
    try {
      const { data: sites, error } = await supabase
        .from('scraper_sites')
        .select('name, priority, category');

      if (error) throw error;

      for (const site of sites || []) {
        const budgetTier = this.getBudgetTier(site.priority);
        const dailyBudget = CostController.DEFAULT_DAILY_BUDGETS[budgetTier];
        
        this.siteBudgets.set(site.name, {
          siteName: site.name,
          strategy: 'http', // Start with cheapest strategy
          dailyBudget,
          currentUsage: this.createEmptyUsage(),
          utilizationPercent: 0,
          status: 'under_budget'
        });
      }

      // Load today's usage from database
      await this.loadTodaysUsage();
    } catch (error) {
      console.error('Failed to initialize site budgets:', error);
    }
  }

  /**
   * Check if operation is within budget and record usage
   */
  async checkAndRecordUsage(
    siteName: string,
    operation: {
      type: 'http' | 'headless' | 'llm' | 'captcha';
      amount: number; // requests, minutes, tokens, or solves
    }
  ): Promise<{
    allowed: boolean;
    reason?: string;
    suggestedStrategy?: 'http' | 'headless' | 'hybrid';
    remainingBudget?: Partial<StrategyBudget>;
  }> {
    const siteBudget = this.siteBudgets.get(siteName);
    if (!siteBudget) {
      return { allowed: false, reason: `No budget configured for site: ${siteName}` };
    }

    // Check if operation would exceed budget
    const wouldExceed = this.wouldExceedBudget(siteBudget, operation);
    if (wouldExceed.exceeded) {
      // Suggest strategy downgrade if possible
      const suggestion = this.suggestStrategyDowngrade(siteBudget, operation);
      return {
        allowed: false,
        reason: wouldExceed.reason,
        suggestedStrategy: suggestion,
        remainingBudget: this.calculateRemainingBudget(siteBudget)
      };
    }

    // Record the usage
    await this.recordUsage(siteName, operation);
    
    // Update utilization and status
    this.updateSiteBudgetStatus(siteBudget);

    return {
      allowed: true,
      remainingBudget: this.calculateRemainingBudget(siteBudget)
    };
  }

  /**
   * Get budget status for all sites
   */
  getAllSiteBudgets(): SiteBudget[] {
    return Array.from(this.siteBudgets.values());
  }

  /**
   * Get budget status for specific site
   */
  getSiteBudget(siteName: string): SiteBudget | null {
    return this.siteBudgets.get(siteName) || null;
  }

  /**
   * Force strategy downgrade for a site
   */
  async downgradeSiteStrategy(siteName: string, newStrategy: 'http' | 'headless' | 'hybrid'): Promise<void> {
    const siteBudget = this.siteBudgets.get(siteName);
    if (siteBudget) {
      const oldStrategy = siteBudget.strategy;
      siteBudget.strategy = newStrategy;
      
      // Log the downgrade
      logger.info('Strategy downgraded due to budget constraints', { 
        siteName, 
        oldStrategy, 
        newStrategy 
      });
      
      // Create alert for strategy change
      await this.createBudgetAlert(siteName, 'strategy_downgrade', {
        oldStrategy: siteBudget.strategy,
        newStrategy,
        reason: 'Budget limit reached'
      });
    }
  }

  /**
   * Reset daily usage counters (called by scheduler)
   */
  async resetDailyUsage(): Promise<void> {
    for (const [siteName, budget] of this.siteBudgets) {
      budget.currentUsage = this.createEmptyUsage();
      budget.utilizationPercent = 0;
      budget.status = 'under_budget';
      budget.strategy = 'http'; // Reset to cheapest strategy
    }

    logger.info('Daily usage counters reset for all sites');
  }

  /**
   * Get cost analysis for the current month
   */
  async getMonthlyCostAnalysis(): Promise<{
    totalSpent: number;
    budgetUtilization: number;
    topSpendingSites: Array<{ site: string; cost: number; percentage: number }>;
    projectedMonthlySpend: number;
  }> {
    try {
      // Get usage data from the current month
      const startOfMonth = new Date();
      startOfMonth.setDate(1);
      startOfMonth.setHours(0, 0, 0, 0);

      const { data: usage, error } = await supabase
        .from('pipeline_metrics')
        .select('*')
        .eq('metric_name', 'cost_tracking')
        .gte('created_at', startOfMonth.toISOString());

      if (error) throw error;

      let totalSpent = 0;
      const siteSpending: Record<string, number> = {};

      // Calculate costs from usage metrics
      for (const metric of usage || []) {
        const tags = (metric.tags as any) || {};
        const siteName = tags.site_name || 'unknown';
        const operationType = tags.operation_type || 'http';
        const amount = metric.metric_value || 0;

        let cost = 0;
        switch (operationType) {
          case 'http':
            cost = amount * this.costs.httpRequestCost;
            break;
          case 'headless':
            cost = amount * this.costs.headlessMinuteCost;
            break;
          case 'llm':
            cost = amount * this.costs.llmTokenCost / 1000;
            break;
          case 'captcha':
            cost = amount * this.costs.captchaSolveCost;
            break;
        }

        totalSpent += cost;
        siteSpending[siteName] = (siteSpending[siteName] || 0) + cost;
      }

      // Calculate total monthly budget
      const totalMonthlyBudget = Array.from(this.siteBudgets.values())
        .reduce((sum, budget) => sum + budget.dailyBudget.monthlyTotalCost, 0);

      // Top spending sites
      const topSpendingSites = Object.entries(siteSpending)
        .map(([site, cost]) => ({
          site,
          cost,
          percentage: (cost / totalSpent) * 100
        }))
        .sort((a, b) => b.cost - a.cost)
        .slice(0, 5);

      // Project monthly spend based on current daily average
      const daysElapsed = new Date().getDate();
      const projectedMonthlySpend = daysElapsed > 0 ? (totalSpent / daysElapsed) * 30 : 0;

      return {
        totalSpent,
        budgetUtilization: (totalSpent / totalMonthlyBudget) * 100,
        topSpendingSites,
        projectedMonthlySpend
      };
    } catch (error) {
      console.error('Failed to get monthly cost analysis:', error);
      return {
        totalSpent: 0,
        budgetUtilization: 0,
        topSpendingSites: [],
        projectedMonthlySpend: 0
      };
    }
  }

  /**
   * Check if operation would exceed budget
   */
  private wouldExceedBudget(
    siteBudget: SiteBudget,
    operation: { type: 'http' | 'headless' | 'llm' | 'captcha'; amount: number }
  ): { exceeded: boolean; reason?: string } {
    const { currentUsage, dailyBudget } = siteBudget;

    switch (operation.type) {
      case 'http':
        if (currentUsage.dailyHttpRequests + operation.amount > dailyBudget.dailyHttpRequests) {
          return {
            exceeded: true,
            reason: `HTTP requests would exceed daily limit (${dailyBudget.dailyHttpRequests})`
          };
        }
        break;
      
      case 'headless':
        if (currentUsage.dailyHeadlessMinutes + operation.amount > dailyBudget.dailyHeadlessMinutes) {
          return {
            exceeded: true,
            reason: `Headless minutes would exceed daily limit (${dailyBudget.dailyHeadlessMinutes})`
          };
        }
        break;
      
      case 'llm':
        if (currentUsage.dailyLLMTokens + operation.amount > dailyBudget.dailyLLMTokens) {
          return {
            exceeded: true,
            reason: `LLM tokens would exceed daily limit (${dailyBudget.dailyLLMTokens})`
          };
        }
        break;
      
      case 'captcha':
        if (currentUsage.dailyCaptchaSolves + operation.amount > dailyBudget.dailyCaptchaSolves) {
          return {
            exceeded: true,
            reason: `CAPTCHA solves would exceed daily limit (${dailyBudget.dailyCaptchaSolves})`
          };
        }
        break;
    }

    return { exceeded: false };
  }

  /**
   * Suggest a strategy downgrade when budget is exceeded
   */
  private suggestStrategyDowngrade(
    siteBudget: SiteBudget,
    operation: { type: 'http' | 'headless' | 'llm' | 'captcha'; amount: number }
  ): 'http' | 'headless' | 'hybrid' | undefined {
    if (siteBudget.strategy === 'headless' && operation.type === 'headless') {
      return 'hybrid'; // Use headless selectively
    }
    
    if (siteBudget.strategy === 'hybrid' && (operation.type === 'headless' || operation.type === 'llm')) {
      return 'http'; // Fall back to HTTP only
    }

    return undefined; // Already at lowest cost strategy
  }

  /**
   * Record usage in database and update local tracking
   */
  private async recordUsage(
    siteName: string,
    operation: { type: 'http' | 'headless' | 'llm' | 'captcha'; amount: number }
  ): Promise<void> {
    const siteBudget = this.siteBudgets.get(siteName)!;

    // Update local usage tracking
    switch (operation.type) {
      case 'http':
        siteBudget.currentUsage.dailyHttpRequests += operation.amount;
        break;
      case 'headless':
        siteBudget.currentUsage.dailyHeadlessMinutes += operation.amount;
        break;
      case 'llm':
        siteBudget.currentUsage.dailyLLMTokens += operation.amount;
        break;
      case 'captcha':
        siteBudget.currentUsage.dailyCaptchaSolves += operation.amount;
        break;
    }

    // Record in database for cost tracking
    try {
      await supabase.from('pipeline_metrics').insert({
        metric_name: 'cost_tracking',
        metric_value: operation.amount,
        metric_unit: operation.type,
        tags: {
          site_name: siteName,
          operation_type: operation.type,
          strategy: siteBudget.strategy
        }
      });
    } catch (error) {
      console.error('Failed to record usage metric:', error);
    }
  }

  /**
   * Update site budget status based on current utilization
   */
  private updateSiteBudgetStatus(siteBudget: SiteBudget): void {
    const utilizations = [
      siteBudget.currentUsage.dailyHttpRequests / siteBudget.dailyBudget.dailyHttpRequests,
      siteBudget.currentUsage.dailyHeadlessMinutes / siteBudget.dailyBudget.dailyHeadlessMinutes,
      siteBudget.currentUsage.dailyLLMTokens / siteBudget.dailyBudget.dailyLLMTokens,
      siteBudget.currentUsage.dailyCaptchaSolves / siteBudget.dailyBudget.dailyCaptchaSolves
    ];

    const maxUtilization = Math.max(...utilizations) * 100;
    siteBudget.utilizationPercent = maxUtilization;

    if (maxUtilization >= 100) {
      siteBudget.status = 'over_budget';
    } else if (maxUtilization >= 80) {
      siteBudget.status = 'near_limit';
    } else {
      siteBudget.status = 'under_budget';
    }
  }

  /**
   * Calculate remaining budget for a site
   */
  private calculateRemainingBudget(siteBudget: SiteBudget): Partial<StrategyBudget> {
    return {
      dailyHttpRequests: siteBudget.dailyBudget.dailyHttpRequests - siteBudget.currentUsage.dailyHttpRequests,
      dailyHeadlessMinutes: siteBudget.dailyBudget.dailyHeadlessMinutes - siteBudget.currentUsage.dailyHeadlessMinutes,
      dailyLLMTokens: siteBudget.dailyBudget.dailyLLMTokens - siteBudget.currentUsage.dailyLLMTokens,
      dailyCaptchaSolves: siteBudget.dailyBudget.dailyCaptchaSolves - siteBudget.currentUsage.dailyCaptchaSolves
    };
  }

  /**
   * Create empty usage tracking object
   */
  private createEmptyUsage(): StrategyBudget {
    return {
      dailyHttpRequests: 0,
      dailyHeadlessMinutes: 0,
      dailyLLMTokens: 0,
      dailyCaptchaSolves: 0,
      monthlyTotalCost: 0
    };
  }

  /**
   * Get budget tier based on site priority
   */
  private getBudgetTier(priority: number): 'high_value' | 'medium_value' | 'low_value' {
    if (priority >= 8) return 'high_value';
    if (priority >= 5) return 'medium_value';
    return 'low_value';
  }

  /**
   * Load today's usage from database
   */
  private async loadTodaysUsage(): Promise<void> {
    try {
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      const { data, error } = await supabase
        .from('pipeline_metrics')
        .select('*')
        .eq('metric_name', 'cost_tracking')
        .gte('created_at', today.toISOString());

      if (error) throw error;

      // Aggregate today's usage by site
      for (const metric of data || []) {
        const tags = (metric.tags as any) || {};
        const siteName = tags.site_name;
        const operationType = tags.operation_type;
        const amount = metric.metric_value || 0;

        const siteBudget = this.siteBudgets.get(siteName);
        if (siteBudget) {
          switch (operationType) {
            case 'http':
              siteBudget.currentUsage.dailyHttpRequests += amount;
              break;
            case 'headless':
              siteBudget.currentUsage.dailyHeadlessMinutes += amount;
              break;
            case 'llm':
              siteBudget.currentUsage.dailyLLMTokens += amount;
              break;
            case 'captcha':
              siteBudget.currentUsage.dailyCaptchaSolves += amount;
              break;
          }
          this.updateSiteBudgetStatus(siteBudget);
        }
      }
    } catch (error) {
      console.error('Failed to load today\'s usage:', error);
    }
  }

  /**
   * Create budget-related alerts
   */
  private async createBudgetAlert(
    siteName: string,
    alertType: 'near_limit' | 'over_budget' | 'strategy_downgrade',
    metadata: any
  ): Promise<void> {
    try {
      await supabase.from('user_alerts').insert({
        id: `budget-${alertType}-${Date.now()}`,
        user_id: (await supabase.auth.getUser()).data.user?.id,
        type: 'budget',
        priority: alertType === 'over_budget' ? 'high' : 'medium',
        title: `Budget Alert: ${siteName}`,
        message: `Site ${siteName} ${alertType.replace('_', ' ')}`,
        opportunity_data: {
          site_name: siteName,
          alert_type: alertType,
          ...metadata
        }
      });
    } catch (error) {
      console.error('Failed to create budget alert:', error);
    }
  }
}

export default CostController;