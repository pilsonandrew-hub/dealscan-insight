/**
 * TypeScript interfaces based on DealerScope backend models
 * Matches the Python FastAPI models for consistency
 */

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
  status?: "hot" | "good" | "moderate";
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
  vin?: string;
  make: string;
  model: string;
  year: number;
  mileage?: number;
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