/**
 * Per-Field Provenance Tracking - Phase 3 Data Quality & ML
 * Tracks extraction strategy, confidence, and lineage for each field
 */

import productionLogger from '@/utils/productionLogger';
import { supabase } from '@/integrations/supabase/client';

interface ProvenanceData {
  field_name: string;
  extraction_strategy: 'selector' | 'ml' | 'llm' | 'manual' | 'inferred';
  confidence: number; // 0.0 to 1.0
  provenance: string; // CSS selector, model@version, or method description  
  lineage: {
    url: string;
    timestamp: string;
    extractor_version: string;
    source_hash?: string;
  };
  validator_results?: {
    schema_valid: boolean;
    business_rules_valid: boolean;
    anomaly_score?: number;
  };
  drift_decision?: {
    triggered: boolean;
    old_strategy: string;
    new_strategy: string;
    reason: string;
    timestamp: string;
  };
}

interface FieldExtractionResult {
  value: any;
  provenance: ProvenanceData;
}

interface ExtractionContext {
  url: string;
  site_id: string;
  extractor_version: string;
  cluster_id?: string;
  page_content_hash?: string;
}

interface ModelPerformanceMetrics {
  model_name: string;
  field_name: string;
  accuracy: number;
  precision: number;
  recall: number;
  f1_score: number;
  confidence_distribution: number[]; // Buckets: [0-0.1, 0.1-0.2, ..., 0.9-1.0]
  last_updated: string;
}

export class ProvenanceTracker {
  private fieldMetrics: Map<string, ModelPerformanceMetrics> = new Map();
  private driftThresholds = {
    confidence: 0.7,
    accuracy_drop: 0.1,
    consecutive_failures: 5
  };

  constructor() {
    productionLogger.info('Provenance tracker initialized');
  }

  /**
   * Track field extraction with full provenance
   */
  async trackFieldExtraction(
    fieldName: string,
    value: any,
    strategy: ProvenanceData['extraction_strategy'],
    confidence: number,
    provenance: string,
    context: ExtractionContext,
    validationResults?: ProvenanceData['validator_results']
  ): Promise<ProvenanceData> {
    
    const provenanceData: ProvenanceData = {
      field_name: fieldName,
      extraction_strategy: strategy,
      confidence: Math.max(0, Math.min(1, confidence)), // Clamp to [0,1]
      provenance,
      lineage: {
        url: context.url,
        timestamp: new Date().toISOString(),
        extractor_version: context.extractor_version,
        source_hash: context.page_content_hash
      },
      validator_results: validationResults
    };

    // Check for drift and potentially switch strategies
    const driftDecision = await this.checkForDrift(fieldName, strategy, confidence, context);
    if (driftDecision) {
      provenanceData.drift_decision = driftDecision;
    }

    // Store provenance data
    await this.storeProvenance(provenanceData, context);

    // Update performance metrics
    await this.updatePerformanceMetrics(fieldName, strategy, confidence, validationResults?.schema_valid || false);

    productionLogger.debug('Field extraction tracked', {
      field: fieldName,
      strategy,
      confidence,
      drift: !!driftDecision
    });

    return provenanceData;
  }

  /**
   * Execute extraction with fallback chain
   */
  async extractWithFallback(
    fieldName: string,
    extractors: {
      selector: () => Promise<{ value: any; confidence: number }>;
      ml?: () => Promise<{ value: any; confidence: number }>;
      llm?: () => Promise<{ value: any; confidence: number }>;
    },
    context: ExtractionContext,
    thresholds = { ml: 0.8, llm: 0.7 }
  ): Promise<FieldExtractionResult> {

    // Try selector first
    try {
      const selectorResult = await extractors.selector();
      
      if (selectorResult.confidence >= 0.9) {
        const provenance = await this.trackFieldExtraction(
          fieldName,
          selectorResult.value,
          'selector',
          selectorResult.confidence,
          'css_selector',
          context,
          { schema_valid: true, business_rules_valid: true }
        );

        return {
          value: selectorResult.value,
          provenance
        };
      }
    } catch (error) {
      productionLogger.warn('Selector extraction failed', {
        field: fieldName,
        url: context.url
      }, error as Error);
    }

    // Try ML model if available and selector confidence was low
    if (extractors.ml) {
      try {
        const mlResult = await extractors.ml();
        
        if (mlResult.confidence >= thresholds.ml) {
          const provenance = await this.trackFieldExtraction(
            fieldName,
            mlResult.value,
            'ml',
            mlResult.confidence,
            'lightgbm_v2.1',
            context,
            { schema_valid: true, business_rules_valid: true }
          );

          return {
            value: mlResult.value,
            provenance
          };
        }
      } catch (error) {
        productionLogger.warn('ML extraction failed', {
          field: fieldName,
          url: context.url
        }, error as Error);
      }
    }

    // Try LLM as last resort
    if (extractors.llm) {
      try {
        const llmResult = await extractors.llm();
        
        if (llmResult.confidence >= thresholds.llm) {
          const provenance = await this.trackFieldExtraction(
            fieldName,
            llmResult.value,
            'llm',
            llmResult.confidence,
            'gpt-4o-mini',
            context,
            { schema_valid: true, business_rules_valid: true }
          );

          return {
            value: llmResult.value,
            provenance
          };
        }
      } catch (error) {
        productionLogger.warn('LLM extraction failed', {
          field: fieldName,
          url: context.url
        }, error as Error);
      }
    }

    // All methods failed - return with low confidence
    const provenance = await this.trackFieldExtraction(
      fieldName,
      null,
      'inferred',
      0.0,
      'all_methods_failed',
      context,
      { schema_valid: false, business_rules_valid: false }
    );

    return {
      value: null,
      provenance
    };
  }

  /**
   * Check for drift and decide on strategy change
   */
  private async checkForDrift(
    fieldName: string,
    currentStrategy: ProvenanceData['extraction_strategy'],
    confidence: number,
    context: ExtractionContext
  ): Promise<ProvenanceData['drift_decision'] | null> {

    // Get recent performance for this field
    const recentPerformance = await this.getRecentPerformance(fieldName, currentStrategy, 50);
    
    if (recentPerformance.length < 10) {
      return null; // Need more data
    }

    // Calculate recent metrics
    const avgConfidence = recentPerformance.reduce((sum, p) => sum + p.confidence, 0) / recentPerformance.length;
    const failureRate = recentPerformance.filter(p => p.confidence < this.driftThresholds.confidence).length / recentPerformance.length;
    
    // Check for drift conditions
    let driftDetected = false;
    let reason = '';

    if (avgConfidence < this.driftThresholds.confidence) {
      driftDetected = true;
      reason = `Average confidence dropped to ${avgConfidence.toFixed(3)}`;
    }

    if (failureRate > 0.3) {
      driftDetected = true;
      reason += ` High failure rate: ${(failureRate * 100).toFixed(1)}%`;
    }

    // Consecutive low confidence extractions
    const recentFive = recentPerformance.slice(-5);
    if (recentFive.every(p => p.confidence < this.driftThresholds.confidence)) {
      driftDetected = true;
      reason += ' 5 consecutive low-confidence extractions';
    }

    if (!driftDetected) {
      return null;
    }

    // Decide on new strategy
    let newStrategy: ProvenanceData['extraction_strategy'] = currentStrategy;
    
    if (currentStrategy === 'selector') {
      newStrategy = 'ml';
    } else if (currentStrategy === 'ml') {
      newStrategy = 'llm';
    } else if (currentStrategy === 'llm') {
      newStrategy = 'manual'; // Flag for human review
    }

    productionLogger.warn('Drift detected - switching extraction strategy', {
      field: fieldName,
      oldStrategy: currentStrategy,
      newStrategy,
      reason,
      avgConfidence,
      failureRate
    });

    return {
      triggered: true,
      old_strategy: currentStrategy,
      new_strategy: newStrategy,
      reason,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Store provenance data in database
   */
  private async storeProvenance(provenance: ProvenanceData, context: ExtractionContext): Promise<void> {
    try {
      const { error } = await supabase
        .from('field_provenance')
        .insert({
          site_id: context.site_id,
          field_name: provenance.field_name,
          extraction_strategy: provenance.extraction_strategy,
          confidence: provenance.confidence,
          provenance: provenance.provenance,
          lineage: provenance.lineage,
          validator_results: provenance.validator_results,
          drift_decision: provenance.drift_decision,
          created_at: new Date().toISOString()
        });

      if (error) {
        productionLogger.error('Failed to store provenance data', {
          field: provenance.field_name,
          site: context.site_id
        }, error);
      }
    } catch (error) {
      productionLogger.error('Exception storing provenance data', {
        field: provenance.field_name
      }, error as Error);
    }
  }

  /**
   * Update performance metrics for strategy/field combination
   */
  private async updatePerformanceMetrics(
    fieldName: string,
    strategy: ProvenanceData['extraction_strategy'],
    confidence: number,
    success: boolean
  ): Promise<void> {
    
    const metricKey = `${strategy}_${fieldName}`;
    let metrics = this.fieldMetrics.get(metricKey);

    if (!metrics) {
      metrics = {
        model_name: strategy,
        field_name: fieldName,
        accuracy: 0,
        precision: 0,
        recall: 0,
        f1_score: 0,
        confidence_distribution: new Array(10).fill(0),
        last_updated: new Date().toISOString()
      };
    }

    // Update confidence distribution
    const bucket = Math.min(9, Math.floor(confidence * 10));
    metrics.confidence_distribution[bucket]++;

    // Simple accuracy tracking (would need ground truth for proper metrics)
    const weight = 0.1; // Learning rate
    if (success) {
      metrics.accuracy = metrics.accuracy * (1 - weight) + weight;
    } else {
      metrics.accuracy = metrics.accuracy * (1 - weight);
    }

    metrics.last_updated = new Date().toISOString();
    this.fieldMetrics.set(metricKey, metrics);

    // Periodically save to database
    if (Math.random() < 0.1) { // 10% chance
      await this.saveMetricsToDatabase(metrics);
    }
  }

  /**
   * Get recent performance data for drift detection
   */
  private async getRecentPerformance(
    fieldName: string,
    strategy: ProvenanceData['extraction_strategy'],
    limit: number = 50
  ): Promise<Array<{ confidence: number; timestamp: string; success: boolean }>> {
    
    try {
      const { data, error } = await supabase
        .from('field_provenance')
        .select('confidence, created_at, validator_results')
        .eq('field_name', fieldName)
        .eq('extraction_strategy', strategy)
        .order('created_at', { ascending: false })
        .limit(limit);

      if (error) {
        productionLogger.error('Failed to get recent performance data', error);
        return [];
      }

      return (data || []).map(row => ({
        confidence: row.confidence,
        timestamp: row.created_at,
        success: row.validator_results?.schema_valid || false
      }));

    } catch (error) {
      productionLogger.error('Exception getting recent performance', {
        field: fieldName,
        strategy
      }, error as Error);
      return [];
    }
  }

  /**
   * Save metrics to database
   */
  private async saveMetricsToDatabase(metrics: ModelPerformanceMetrics): Promise<void> {
    try {
      const { error } = await supabase
        .from('model_performance_metrics')
        .upsert({
          model_name: metrics.model_name,
          field_name: metrics.field_name,
          accuracy: metrics.accuracy,
          precision: metrics.precision,
          recall: metrics.recall,
          f1_score: metrics.f1_score,
          confidence_distribution: metrics.confidence_distribution,
          last_updated: metrics.last_updated
        }, {
          onConflict: 'model_name,field_name'
        });

      if (error) {
        productionLogger.error('Failed to save performance metrics', error);
      }
    } catch (error) {
      productionLogger.error('Exception saving performance metrics', {
        model: metrics.model_name,
        field: metrics.field_name
      }, error as Error);
    }
  }

  /**
   * Get performance summary for monitoring
   */
  getPerformanceSummary(): Array<{
    strategy: string;
    field: string;
    accuracy: number;
    avgConfidence: number;
    totalExtractions: number;
  }> {
    
    return Array.from(this.fieldMetrics.entries()).map(([key, metrics]) => {
      const totalExtractions = metrics.confidence_distribution.reduce((sum, count) => sum + count, 0);
      const avgConfidence = metrics.confidence_distribution.reduce((sum, count, bucket) => {
        return sum + (count * (bucket + 0.5) / 10);
      }, 0) / Math.max(1, totalExtractions);

      return {
        strategy: metrics.model_name,
        field: metrics.field_name,
        accuracy: metrics.accuracy,
        avgConfidence,
        totalExtractions
      };
    });
  }

  /**
   * Generate provenance report for audit
   */
  async generateProvenanceReport(siteId: string, dateRange: { start: string; end: string }): Promise<{
    totalExtractions: number;
    strategyBreakdown: Record<string, number>;
    avgConfidence: number;
    driftEvents: number;
    topFields: Array<{ field: string; extractions: number; avgConfidence: number }>;
  }> {
    
    try {
      const { data, error } = await supabase
        .from('field_provenance')
        .select('field_name, extraction_strategy, confidence, drift_decision')
        .eq('site_id', siteId)
        .gte('created_at', dateRange.start)
        .lte('created_at', dateRange.end);

      if (error) {
        throw error;
      }

      const extractions = data || [];
      const strategyBreakdown: Record<string, number> = {};
      const fieldCounts: Record<string, { count: number; totalConfidence: number }> = {};
      let driftEvents = 0;

      for (const extraction of extractions) {
        // Strategy breakdown
        strategyBreakdown[extraction.extraction_strategy] = 
          (strategyBreakdown[extraction.extraction_strategy] || 0) + 1;

        // Field counts
        if (!fieldCounts[extraction.field_name]) {
          fieldCounts[extraction.field_name] = { count: 0, totalConfidence: 0 };
        }
        fieldCounts[extraction.field_name].count++;
        fieldCounts[extraction.field_name].totalConfidence += extraction.confidence;

        // Drift events
        if (extraction.drift_decision?.triggered) {
          driftEvents++;
        }
      }

      const totalExtractions = extractions.length;
      const avgConfidence = totalExtractions > 0 ? 
        extractions.reduce((sum, e) => sum + e.confidence, 0) / totalExtractions : 0;

      const topFields = Object.entries(fieldCounts)
        .map(([field, data]) => ({
          field,
          extractions: data.count,
          avgConfidence: data.totalConfidence / data.count
        }))
        .sort((a, b) => b.extractions - a.extractions)
        .slice(0, 10);

      return {
        totalExtractions,
        strategyBreakdown,
        avgConfidence,
        driftEvents,
        topFields
      };

    } catch (error) {
      productionLogger.error('Failed to generate provenance report', {
        siteId,
        dateRange
      }, error as Error);

      return {
        totalExtractions: 0,
        strategyBreakdown: {},
        avgConfidence: 0,
        driftEvents: 0,
        topFields: []
      };
    }
  }
}

// Global tracker instance
export const provenanceTracker = new ProvenanceTracker();