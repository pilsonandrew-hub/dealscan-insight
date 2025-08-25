/**
 * Provenance Types - Track extraction strategy cascade (selector→ML→LLM)
 */

export type ExtractionStrategy = "selector" | "ml" | "llm";
export type RenderMode = "http" | "headless";

export interface Provenance {
  field: string;
  extraction_strategy: ExtractionStrategy;
  confidence: number; // 0..1
  provenance: string; // css/xpath or model@ver
  validator_results: {
    valid: boolean;
    errors: string[];
  };
  render_mode: RenderMode;
  cluster_id?: string;
  retries?: number;
  lineage: {
    url: string;
    ts: string;
    extractor_version: string;
  };
  cost_band?: CostBand;
  budget_used?: number;
}

export type CostBand = "http" | "headless" | "llm" | "captcha";

export interface ExtractionResult {
  value: unknown;
  provenance: Provenance;
  metadata?: Record<string, unknown>;
}

export interface StrategyConfig {
  name: ExtractionStrategy;
  confidence_threshold: number;
  fallback_strategy?: ExtractionStrategy;
  cost_band: CostBand;
  timeout_ms: number;
  retry_count: number;
}

export interface ExtractionPipeline {
  strategies: StrategyConfig[];
  budget_limits: Record<CostBand, number>;
  site_id: string;
  field_name: string;
}

export interface ValidationRule {
  field: string;
  type: "string" | "number" | "date" | "enum" | "regex";
  required: boolean;
  min_length?: number;
  max_length?: number;
  min_value?: number;
  max_value?: number;
  pattern?: string;
  enum_values?: string[];
  custom_validator?: (value: unknown) => { valid: boolean; errors: string[] };
}

export interface FieldExtraction {
  field: string;
  value: unknown;
  confidence: number;
  strategy_used: ExtractionStrategy;
  validation_passed: boolean;
  validation_errors: string[];
  provenance: Provenance;
  fallback_attempts: number;
  total_cost: number;
}

export interface ExtractionSummary {
  url: string;
  site_id: string;
  timestamp: string;
  total_fields: number;
  successful_extractions: number;
  failed_extractions: number;
  total_cost: number;
  render_mode: RenderMode;
  extraction_time_ms: number;
  fields: FieldExtraction[];
  metadata: {
    user_agent: string;
    viewport_size?: string;
    network_conditions?: string;
    errors: string[];
    warnings: string[];
  };
}

/**
 * Extraction quality metrics for monitoring
 */
export interface ExtractionMetrics {
  site_id: string;
  field_name: string;
  strategy: ExtractionStrategy;
  success_rate: number;
  avg_confidence: number;
  avg_cost: number;
  avg_extraction_time_ms: number;
  total_extractions: number;
  period_start: string;
  period_end: string;
}

/**
 * Budget tracking for cost control
 */
export interface BudgetUsage {
  site_id: string;
  cost_band: CostBand;
  daily_limit: number;
  current_usage: number;
  percentage_used: number;
  last_reset: string;
  projected_daily_usage: number;
  budget_exhausted: boolean;
}

/**
 * Active learning labels for model improvement
 */
export interface ExtractionLabel {
  id: string;
  url: string;
  field: string;
  old_value: string | null;
  new_value: string;
  css_path?: string;
  cluster_id?: string;
  extraction_strategy: ExtractionStrategy;
  confidence_before: number;
  user_id: string;
  created_at: string;
  feedback_type: "correction" | "validation" | "new_field";
  metadata?: Record<string, unknown>;
}

/**
 * Site-specific extraction configuration
 */
export interface SiteConfig {
  site_id: string;
  base_url: string;
  name: string;
  category: string;
  enabled: boolean;
  priority: number;
  rate_limit_seconds: number;
  max_pages: number;
  selectors: Record<string, string>;
  headers: Record<string, string>;
  budget_limits: Record<CostBand, number>;
  extraction_strategies: Record<string, StrategyConfig[]>;
  validation_rules: ValidationRule[];
  last_updated: string;
}