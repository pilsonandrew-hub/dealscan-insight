import { supabase } from '@/integrations/supabase/client';

export type ExtractionStrategy = 'selector' | 'ml' | 'llm' | 'human';

export interface ExtractionThresholds {
  selectorMin: number;
  mlMin: number;
  llmMin: number;
}

export interface ExtractionContext {
  field: string;
  html: string;
  clusterId: string;
  url: string;
  siteName: string;
}

export interface ExtractionResult {
  value: any;
  confidence: number;
  strategy: ExtractionStrategy;
  provenance: string;
  retries: number;
  driftDecision: 'none' | 'switched' | 'fallback' | 'manual_override';
}

export interface ProvenanceData {
  field_name: string;
  extraction_strategy: ExtractionStrategy;
  confidence: number;
  provenance: string;
  lineage: {
    url: string;
    timestamp: string;
    extractor_version: string;
  };
  render_mode: 'http' | 'headless';
  cluster_id: string;
  retries: number;
  limits_hit: {
    timeout: boolean;
    max_body: boolean;
    rate_limit: boolean;
  };
  drift_decision: string;
  validator_results: {
    valid: boolean;
    errors: string[];
  };
}

/**
 * Multi-strategy extraction engine with fallback chain
 * Implements selector → ML → LLM → human pipeline with configurable thresholds
 */
export class ExtractionStrategyEngine {
  private static readonly DEFAULT_THRESHOLDS: ExtractionThresholds = {
    selectorMin: 0.80,
    mlMin: 0.70,
    llmMin: 0.0
  };

  private static readonly EXTRACTOR_VERSION = '4.9.0';

  /**
   * Extract field value using fallback strategy chain
   */
  static async extractField(
    context: ExtractionContext,
    customThresholds?: Partial<ExtractionThresholds>
  ): Promise<ExtractionResult> {
    const thresholds = { ...this.DEFAULT_THRESHOLDS, ...customThresholds };
    let retries = 0;

    // Load site-specific extraction strategies
    const strategies = await this.loadExtractionStrategies(
      context.siteName,
      context.clusterId,
      context.field
    );

    // Try each strategy in order until success
    for (const strategy of strategies) {
      try {
        const result = await this.executeStrategy(
          strategy.strategy as ExtractionStrategy,
          context,
          strategy
        );

        const threshold = this.getThresholdForStrategy(strategy.strategy as ExtractionStrategy, thresholds);
        
        if (result.confidence >= threshold) {
          return {
            ...result,
            retries,
            driftDecision: retries > 0 ? 'switched' : 'none'
          };
        }

        retries++;
      } catch (error) {
        console.error(`Strategy ${strategy.strategy} failed:`, error);
        retries++;
      }
    }

    // All strategies failed - require human intervention
    return {
      value: null,
      confidence: 0,
      strategy: 'human',
      provenance: 'human_required',
      retries,
      driftDecision: 'manual_override'
    };
  }

  /**
   * Execute specific extraction strategy
   */
  private static async executeStrategy(
    strategy: ExtractionStrategy,
    context: ExtractionContext,
    config: any
  ): Promise<Omit<ExtractionResult, 'retries' | 'driftDecision'>> {
    switch (strategy) {
      case 'selector':
        return this.selectorExtract(context, config.selector_config);
      case 'ml':
        return this.mlExtract(context, config.ml_config);
      case 'llm':
        return this.llmExtract(context, config.llm_config);
      default:
        throw new Error(`Unknown strategy: ${strategy}`);
    }
  }

  /**
   * CSS selector-based extraction
   */
  private static async selectorExtract(
    context: ExtractionContext,
    config: any
  ): Promise<Omit<ExtractionResult, 'retries' | 'driftDecision'>> {
    // Mock implementation - in production, use actual DOM parsing
    const selectors = config?.selectors || [];
    
    // Simulate selector extraction with confidence based on field type
    const confidence = this.getFieldConfidence(context.field, 'selector');
    const value = this.mockExtractValue(context.field);
    
    return {
      value,
      confidence,
      strategy: 'selector',
      provenance: selectors[0] || '.default-selector'
    };
  }

  /**
   * Machine learning-based extraction
   */
  private static async mlExtract(
    context: ExtractionContext,
    config: any
  ): Promise<Omit<ExtractionResult, 'retries' | 'driftDecision'>> {
    // Mock implementation - in production, call ML microservice
    const confidence = this.getFieldConfidence(context.field, 'ml');
    const value = this.mockExtractValue(context.field);
    
    return {
      value,
      confidence,
      strategy: 'ml',
      provenance: `ml_classifier_v${config?.version || '1.0'}`
    };
  }

  /**
   * LLM-based extraction with schema validation
   */
  private static async llmExtract(
    context: ExtractionContext,
    config: any
  ): Promise<Omit<ExtractionResult, 'retries' | 'driftDecision'>> {
    // Mock implementation - in production, call LLM with schema guards
    const confidence = this.getFieldConfidence(context.field, 'llm');
    const value = this.mockExtractValue(context.field);
    
    return {
      value,
      confidence,
      strategy: 'llm',
      provenance: `llm_${config?.model || 'gpt-4'}@${config?.version || '1.0'}`
    };
  }

  /**
   * Load extraction strategies for site/cluster/field combination
   */
  private static async loadExtractionStrategies(
    siteName: string,
    clusterId: string,
    fieldName: string
  ) {
    try {
      const { data, error } = await supabase
        .from('extraction_strategies')
        .select('*')
        .eq('site_name', siteName)
        .eq('field_name', fieldName)
        .eq('cluster_id', clusterId)
        .order('fallback_order');

      if (error) throw error;

      // If no specific strategies found, return default fallback chain
      if (!data || data.length === 0) {
        return this.getDefaultStrategies(fieldName);
      }

      return data;
    } catch (error) {
      console.error('Failed to load extraction strategies:', error);
      return this.getDefaultStrategies(fieldName);
    }
  }

  /**
   * Get default extraction strategies for a field
   */
  private static getDefaultStrategies(fieldName: string) {
    return [
      {
        strategy: 'selector',
        fallback_order: 1,
        confidence_threshold: 0.8,
        selector_config: { selectors: [`.${fieldName}`, `[data-${fieldName}]`] }
      },
      {
        strategy: 'ml',
        fallback_order: 2,
        confidence_threshold: 0.7,
        ml_config: { version: '1.0', features: ['text', 'position', 'siblings'] }
      },
      {
        strategy: 'llm',
        fallback_order: 3,
        confidence_threshold: 0.0,
        llm_config: { model: 'gpt-4', version: '1.0', schema_validation: true }
      }
    ];
  }

  /**
   * Get confidence threshold for strategy
   */
  private static getThresholdForStrategy(
    strategy: ExtractionStrategy,
    thresholds: ExtractionThresholds
  ): number {
    switch (strategy) {
      case 'selector': return thresholds.selectorMin;
      case 'ml': return thresholds.mlMin;
      case 'llm': return thresholds.llmMin;
      default: return 0;
    }
  }

  /**
   * Mock confidence calculation based on field type and strategy
   */
  private static getFieldConfidence(field: string, strategy: ExtractionStrategy): number {
    const baseConfidence = {
      selector: { price: 0.85, year: 0.90, make: 0.80, model: 0.75 },
      ml: { price: 0.75, year: 0.80, make: 0.85, model: 0.80 },
      llm: { price: 0.60, year: 0.70, make: 0.75, model: 0.65 }
    };

    const fieldConfidence = baseConfidence[strategy][field as keyof typeof baseConfidence.selector];
    return fieldConfidence || 0.5 + Math.random() * 0.3; // Random between 0.5-0.8
  }

  /**
   * Mock value extraction for testing
   */
  private static mockExtractValue(field: string): any {
    const mockValues = {
      price: '$' + (Math.floor(Math.random() * 50000) + 5000),
      year: 2015 + Math.floor(Math.random() * 8),
      make: ['Ford', 'Toyota', 'Chevrolet', 'Honda'][Math.floor(Math.random() * 4)],
      model: ['F-150', 'Camry', 'Silverado', 'Accord'][Math.floor(Math.random() * 4)],
      mileage: Math.floor(Math.random() * 150000) + 10000
    };

    return mockValues[field as keyof typeof mockValues] || 'Unknown';
  }

  /**
   * Generate provenance data for extraction result
   */
  static generateProvenance(
    context: ExtractionContext,
    result: ExtractionResult,
    renderMode: 'http' | 'headless' = 'http',
    limitsHit: { timeout?: boolean; maxBody?: boolean; rateLimit?: boolean } = {}
  ): ProvenanceData {
    return {
      field_name: context.field,
      extraction_strategy: result.strategy,
      confidence: result.confidence,
      provenance: result.provenance,
      lineage: {
        url: context.url,
        timestamp: new Date().toISOString(),
        extractor_version: this.EXTRACTOR_VERSION
      },
      render_mode: renderMode,
      cluster_id: context.clusterId,
      retries: result.retries,
      limits_hit: {
        timeout: limitsHit.timeout || false,
        max_body: limitsHit.maxBody || false,
        rate_limit: limitsHit.rateLimit || false
      },
      drift_decision: result.driftDecision,
      validator_results: {
        valid: result.confidence > 0.5,
        errors: result.confidence <= 0.5 ? ['Low confidence extraction'] : []
      }
    };
  }
}

export default ExtractionStrategyEngine;