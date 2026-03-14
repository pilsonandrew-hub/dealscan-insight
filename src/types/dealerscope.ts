/**
 * TypeScript interfaces based on DealerScope backend models
 * Matches the Python FastAPI models for consistency
 */

// ─── Gate 1: Age & Mileage ───────────────────────────────────────────────────
export interface AgeMileageGate {
  age_years: number;
  mileage: number;
  passes: boolean;
  price_tier: "premium" | "mid" | "sub_floor";
}

// ─── Gate 2: Market Days Supply (MDS) ────────────────────────────────────────
export interface MDSGate {
  market_days_supply: number;
  threshold: 35;
  passes: boolean;
  days_below_threshold: number;
}

// ─── Gate 3: Scarcity Index ───────────────────────────────────────────────────
export interface ScarcityGate {
  demand_score: number;
  local_supply_count: number;
  scarcity_ratio: number;
  passes: boolean;
  discovery_type: "targeted" | "off_list";
}

// ─── Gate 4: Cost-to-Market Ratio ─────────────────────────────────────────────
export interface CostToMarketGate {
  total_all_in_cost: number;
  wholesale_benchmark: number;
  cost_to_market_ratio: number;
  passes: boolean;
}

// ─── Gate 5: Holding Cost Clock ───────────────────────────────────────────────
export interface HoldingCostGate {
  projected_days_to_sale: number;
  daily_holding_cost: number;
  total_holding_cost: number;
  passes: boolean;
}

// ─── Five-Layer Filter Result ──────────────────────────────────────────────────
export interface FiveLayerFilterResult {
  gate1_age_mileage: AgeMileageGate;
  gate2_mds: MDSGate;
  gate3_scarcity: ScarcityGate;
  gate4_cost_to_market: CostToMarketGate;
  gate5_holding_clock: HoldingCostGate;
  all_gates_passed: boolean;
  first_failed_gate: "gate1" | "gate2" | "gate3" | "gate4" | "gate5" | null;
}

// ─── CPO Eligibility ──────────────────────────────────────────────────────────
export interface CPOEligibility {
  age_qualifies: boolean;
  oem_warranty_remaining: boolean;
  franchise_certifiable: boolean;
  cpo_eligible: boolean;
  estimated_premium: number;
  cpo_adjusted_retail: number;
}

export interface Vehicle {
  id?: string;
  vin: string;
  make: string;
  model: string;
  year: number;
  mileage: number;
  trim?: string;
  title_status?: "clean" | "salvage" | "rebuilt" | "flood" | "lemon";
  photo_url?: string;
  description?: string;
}

export interface DealerSale {
  id?: string;
  vehicle: Vehicle;
  auction: string;
  sale_price: number;
  date: string;
}

export interface MarketPrice {
  make: string;
  model: string;
  year: number;
  trim: string;
  avg_price: number;
  low_price: number;
  high_price: number;
  sample_size: number;
  last_updated: string;
}

export interface Opportunity {
  id?: string;
  vehicle: Vehicle;
  expected_price: number;
  acquisition_cost: number;
  profit: number;
  roi: number;
  confidence: number;
  location?: string;
  state?: string;
  auction_end?: string;
  status?: "hot" | "good" | "moderate" | "new" | "read" | "flagged" | "dismissed";
  score?: number;
  market_price?: MarketPrice;
  total_cost: number;
  risk_score: number;
  transportation_cost: number;
  fees_cost: number;
  estimated_sale_price: number;
  profit_margin: number;
  source_site: string;
  current_bid: number;
  buyer_premium?: number;
  recon_reserve?: number;
  vin?: string;
  make: string;
  model: string;
  year: number;
  mileage?: number;
  investment_grade?: "Platinum" | "Gold" | "Silver" | "Bronze";
  pricing_source?: string;
  pricing_updated_at?: string;
  manheim_mmr_mid?: number;
  manheim_mmr_low?: number;
  manheim_mmr_high?: number;
  manheim_range_width_pct?: number;
  manheim_confidence?: number;
  manheim_source_status?: "live" | "fallback" | "unavailable";
  manheim_updated_at?: string;
  retail_asking_price_estimate?: number;
  retail_comp_price_estimate?: number;
  retail_comp_low?: number;
  retail_comp_high?: number;
  retail_comp_count?: number;
  retail_comp_confidence?: number;
  retail_proxy_multiplier?: number;
  wholesale_ctm_pct?: number;
  retail_ctm_pct?: number;
  estimated_days_to_sale?: number;
  roi_per_day?: number;
  mmr_lookup_basis?: string;
  mmr_confidence_proxy?: number;
  bid_ceiling_pct?: number;
  max_bid?: number;
  bid_headroom?: number;
  ceiling_reason?: string;
  score_version?: string;
  legacy_dos_score?: number;
  // Enhanced ML predictions
  predicted_prices?: {
    p10: number;
    p50: number;
    p90: number;
  };
  days_to_sell?: number;
  deal_rationale?: string;
  user_sentiment?: "interested" | "ignored" | "saved";
  bid_cap?: number;
  market_position?: "below" | "market" | "above";
  last_updated?: string;
  // Five-Layer Filter
  five_layer_filter?: FiveLayerFilterResult;
  cpo_eligibility?: CPOEligibility;
  scarcity?: ScarcityGate;
  market_days_supply?: number;
}

export interface PipelineStatus {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  stage: string;
  progress: number;
  created_at: string;
  completed_at?: string;
  error_message?: string;
  results?: {
    scraped_count: number;
    analyzed_count: number;
    opportunities_found: number;
  };
}

export interface UploadResult {
  status: "success" | "error";
  rows_processed: number;
  errors?: string[];
  opportunities_generated?: number;
}

export interface ApiResponse<T> {
  data: T;
  status: "success" | "error";
  message?: string;
}
