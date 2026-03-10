/**
 * Enhanced deal scoring with Five-Layer Filter, CPO eligibility, and scarcity index
 */

import { useState, useCallback } from 'react';
import { supabase } from '@/integrations/supabase/client';
import {
  Opportunity,
  AgeMileageGate,
  MDSGate,
  ScarcityGate,
  CostToMarketGate,
  HoldingCostGate,
  FiveLayerFilterResult,
  CPOEligibility,
} from '@/types/dealerscope';
import { createLogger } from '@/utils/productionLogger';

const logger = createLogger('EnhancedDealScoring');

// ─── Constants ────────────────────────────────────────────────────────────────
const MDS_THRESHOLD = 35;
const MAX_AGE_YEARS = 4;
const MAX_MILEAGE = 50000;
const SUB_FLOOR_PRICE = 20000;
const PREMIUM_PRICE = 40000;
const COST_TO_MARKET_MAX = 0.88;
const MAX_HOLDING_DAYS = 45;
const CPO_MIN_AGE = 1;
const CPO_MAX_AGE = 3;
const DAILY_HOLDING_COST = 35;

// ─── Gate Functions ───────────────────────────────────────────────────────────

export function runGate1AgeMileage(
  age_years: number,
  mileage: number,
  price: number
): AgeMileageGate {
  const passes = age_years >= 1 && age_years <= MAX_AGE_YEARS && mileage < MAX_MILEAGE;
  const price_tier =
    price >= PREMIUM_PRICE ? "premium" : price < SUB_FLOOR_PRICE ? "sub_floor" : "mid";

  return { age_years, mileage, passes, price_tier };
}

export function runGate2MDS(market_days_supply: number): MDSGate {
  const passes = market_days_supply <= MDS_THRESHOLD;
  const days_below_threshold = passes ? MDS_THRESHOLD - market_days_supply : 0;

  return {
    market_days_supply,
    threshold: 35,
    passes,
    days_below_threshold,
  };
}

export function runGate3Scarcity(
  demand_score: number,
  local_supply_count: number,
  discovery_type: "targeted" | "off_list" = "targeted"
): ScarcityGate {
  const scarcity_ratio = local_supply_count > 0 ? demand_score / local_supply_count : 0;
  const passes = scarcity_ratio >= 4;

  return { demand_score, local_supply_count, scarcity_ratio, passes, discovery_type };
}

export function runGate4CostToMarket(
  total_all_in_cost: number,
  wholesale_benchmark: number
): CostToMarketGate {
  const cost_to_market_ratio =
    wholesale_benchmark > 0 ? total_all_in_cost / wholesale_benchmark : Infinity;
  const passes = cost_to_market_ratio <= COST_TO_MARKET_MAX;

  return { total_all_in_cost, wholesale_benchmark, cost_to_market_ratio, passes };
}

export function runGate5HoldingClock(market_days_supply: number): HoldingCostGate {
  const projected_days_to_sale = market_days_supply * 0.7 + 8;
  const daily_holding_cost = DAILY_HOLDING_COST;
  const total_holding_cost = projected_days_to_sale * daily_holding_cost;
  const passes = projected_days_to_sale <= MAX_HOLDING_DAYS;

  return { projected_days_to_sale, daily_holding_cost, total_holding_cost, passes };
}

export function runFiveLayerFilter(opportunity: Opportunity): FiveLayerFilterResult {
  const currentYear = new Date().getFullYear();
  const age_years = currentYear - opportunity.year;
  const mileage = opportunity.mileage ?? 0;
  const price = opportunity.estimated_sale_price ?? opportunity.current_bid ?? 0;

  // Proxy MDS from confidence if not available
  const mds = opportunity.market_days_supply ?? (100 - opportunity.confidence) * 0.5;

  // Proxy scarcity from confidence and risk
  const demand_score = opportunity.confidence;
  const local_supply_count = Math.max(1, Math.round((100 - opportunity.confidence) / 10));
  const discovery_type: "targeted" | "off_list" =
    opportunity.confidence > 75 ? "targeted" : "off_list";

  const wholesale_benchmark =
    opportunity.market_price?.avg_price ??
    opportunity.estimated_sale_price * 0.82;

  const gate1 = runGate1AgeMileage(age_years, mileage, price);
  const gate2 = runGate2MDS(mds);
  const gate3 = runGate3Scarcity(demand_score, local_supply_count, discovery_type);
  const gate4 = runGate4CostToMarket(opportunity.total_cost, wholesale_benchmark);
  const gate5 = runGate5HoldingClock(mds);

  const gates = [gate1, gate2, gate3, gate4, gate5] as const;
  const gateKeys = ["gate1", "gate2", "gate3", "gate4", "gate5"] as const;
  const firstFailedIndex = gates.findIndex((g) => !g.passes);
  const first_failed_gate =
    firstFailedIndex >= 0 ? gateKeys[firstFailedIndex] : null;

  return {
    gate1_age_mileage: gate1,
    gate2_mds: gate2,
    gate3_scarcity: gate3,
    gate4_cost_to_market: gate4,
    gate5_holding_clock: gate5,
    all_gates_passed: first_failed_gate === null,
    first_failed_gate,
  };
}

export function evaluateCPOEligibility(
  opportunity: Opportunity,
  midpointPrice: number
): CPOEligibility {
  const currentYear = new Date().getFullYear();
  const age_years = currentYear - opportunity.year;

  const age_qualifies = age_years >= CPO_MIN_AGE && age_years <= CPO_MAX_AGE;
  const oem_warranty_remaining = age_years <= 3;
  const franchise_certifiable =
    opportunity.vehicle?.title_status === "clean" ||
    opportunity.vehicle?.title_status === undefined;
  const cpo_eligible = age_qualifies && oem_warranty_remaining && franchise_certifiable;

  const estimated_premium = cpo_eligible ? midpointPrice * 0.125 : 0;
  const cpo_adjusted_retail = midpointPrice + estimated_premium;

  return {
    age_qualifies,
    oem_warranty_remaining,
    franchise_certifiable,
    cpo_eligible,
    estimated_premium,
    cpo_adjusted_retail,
  };
}

// ─── Rationale Builder ────────────────────────────────────────────────────────

function buildDealRationale(
  opportunity: Opportunity,
  filter: FiveLayerFilterResult,
  cpo: CPOEligibility
): string {
  if (filter.all_gates_passed) {
    const parts: string[] = ["All 5 gates passed."];
    if (filter.gate1_age_mileage.price_tier === "premium") parts.push("Premium price tier.");
    if (filter.gate2_mds.days_below_threshold > 10) parts.push("Well below MDS threshold.");
    if (filter.gate3_scarcity.scarcity_ratio >= 6) parts.push("High scarcity ratio.");
    if (cpo.cpo_eligible) parts.push(`CPO eligible (+$${Math.round(cpo.estimated_premium).toLocaleString()} premium).`);
    return parts.join(" ");
  }

  const failedGate = filter.first_failed_gate;
  switch (failedGate) {
    case "gate1":
      return `Failed Gate 1: age ${filter.gate1_age_mileage.age_years}yr / ${filter.gate1_age_mileage.mileage.toLocaleString()}mi exceeds thresholds.`;
    case "gate2":
      return `Failed Gate 2: MDS ${filter.gate2_mds.market_days_supply.toFixed(0)} days exceeds ${MDS_THRESHOLD}-day threshold.`;
    case "gate3":
      return `Failed Gate 3: Scarcity ratio ${filter.gate3_scarcity.scarcity_ratio.toFixed(1)} below minimum of 4.`;
    case "gate4":
      return `Failed Gate 4: Cost-to-market ${(filter.gate4_cost_to_market.cost_to_market_ratio * 100).toFixed(0)}% exceeds ${COST_TO_MARKET_MAX * 100}% cap.`;
    case "gate5":
      return `Failed Gate 5: Projected ${filter.gate5_holding_clock.projected_days_to_sale.toFixed(0)} days to sale exceeds ${MAX_HOLDING_DAYS}-day holding limit.`;
    default:
      return "Standard market opportunity.";
  }
}

// ─── Scoring Progress ─────────────────────────────────────────────────────────

interface ScoringProgress {
  total: number;
  processed: number;
  currentStage: string;
  estimatedTimeRemaining: number;
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useEnhancedDealScoring() {
  const [isScoring, setIsScoring] = useState(false);
  const [progress, setProgress] = useState<ScoringProgress | null>(null);

  const scoreOpportunityWithML = useCallback(async (opportunity: Opportunity): Promise<Opportunity> => {
    const filter = runFiveLayerFilter(opportunity);
    const scarcity = filter.gate3_scarcity;

    // Build price predictions from existing data
    const basePrice = opportunity.estimated_sale_price ?? opportunity.current_bid ?? 0;
    const variance = basePrice * 0.15;
    const predicted_prices = {
      p10: basePrice - variance,
      p50: basePrice,
      p90: basePrice + variance,
    };

    const cpo = evaluateCPOEligibility(opportunity, predicted_prices.p50);
    const deal_rationale = buildDealRationale(opportunity, filter, cpo);

    // bid_cap = p10 * 0.88
    const bid_cap = predicted_prices.p10 * 0.88;

    // MDS-based days to sell
    const mds = opportunity.market_days_supply ?? (100 - opportunity.confidence) * 0.5;
    const days_to_sell = Math.round(mds * 0.7 + 8);

    // Market position
    const market_position: "below" | "market" | "above" =
      opportunity.total_cost < predicted_prices.p50 * 0.88
        ? "below"
        : opportunity.total_cost > predicted_prices.p50 * 1.05
        ? "above"
        : "market";

    // Recalculate ROI from p50
    const enhancedProfit = predicted_prices.p50 - opportunity.total_cost;
    const enhancedROI = opportunity.total_cost > 0 ? (enhancedProfit / opportunity.total_cost) * 100 : 0;

    // Status based on gates + ROI
    let status: Opportunity["status"];
    if (filter.all_gates_passed && enhancedROI > 20) {
      status = "hot";
    } else if (filter.all_gates_passed && enhancedROI > 12) {
      status = "good";
    } else {
      status = "moderate";
    }

    return {
      ...opportunity,
      predicted_prices,
      days_to_sell,
      deal_rationale,
      bid_cap,
      market_position,
      profit: enhancedProfit,
      roi: enhancedROI,
      status,
      five_layer_filter: filter,
      cpo_eligibility: cpo,
      scarcity,
      last_updated: new Date().toISOString(),
    };
  }, []);

  const batchScoreOpportunities = useCallback(async (opportunities: Opportunity[]): Promise<Opportunity[]> => {
    setIsScoring(true);
    setProgress({
      total: opportunities.length,
      processed: 0,
      currentStage: "Initializing Five-Layer Filter...",
      estimatedTimeRemaining: opportunities.length * 2,
    });

    const scoredOpportunities: Opportunity[] = [];

    for (let i = 0; i < opportunities.length; i++) {
      setProgress({
        total: opportunities.length,
        processed: i,
        currentStage: `Scoring ${opportunities[i].make} ${opportunities[i].model}...`,
        estimatedTimeRemaining: (opportunities.length - i) * 2,
      });

      const scored = await scoreOpportunityWithML(opportunities[i]);
      scoredOpportunities.push(scored);

      await new Promise(resolve => setTimeout(resolve, 100));
    }

    setProgress({
      total: opportunities.length,
      processed: opportunities.length,
      currentStage: "Complete",
      estimatedTimeRemaining: 0,
    });

    setIsScoring(false);
    return scoredOpportunities;
  }, [scoreOpportunityWithML]);

  const recordUserFeedback = useCallback(async (
    opportunityId: string,
    action: "saved" | "ignored" | "viewed"
  ) => {
    try {
      const { error } = await supabase
        .from('opportunities')
        .update({
          user_sentiment: action === "saved" ? "interested" : "ignored",
          status: action === "saved" ? "flagged" : "read",
        })
        .eq('id', opportunityId);

      if (error) throw error;
      logger.info('User feedback recorded', { action, opportunityId });
    } catch (error) {
      console.error('Error recording user feedback:', error);
    }
  }, []);

  return {
    isScoring,
    progress,
    scoreOpportunityWithML,
    batchScoreOpportunities,
    recordUserFeedback,
  };
}
