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
}

export interface DealerSale {
  id?: string;
  vehicle: Vehicle;
  auction: string;
  sale_price: number;
  date: string;
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