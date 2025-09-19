interface RoverMetrics {
  cacheHits: number;
  cacheMisses: number;
  apiCalls: number;
  errors: number;
  recommendationLatency: number[];
  mlScoringLatency: number[];
  userInteractions: number;
  successfulRecommendations: number;
}

class RoverMetricsService {
  private metrics: RoverMetrics;
  private startTime: number;

  constructor() {
    this.metrics = {
      cacheHits: 0,
      cacheMisses: 0,
      apiCalls: 0,
      errors: 0,
      recommendationLatency: [],
      mlScoringLatency: [],
      userInteractions: 0,
      successfulRecommendations: 0
    };
    this.startTime = Date.now();
  }

  // Cache metrics
  recordCacheHit() {
    this.metrics.cacheHits++;
  }

  recordCacheMiss() {
    this.metrics.cacheMisses++;
  }

  getCacheHitRate(): number {
    const total = this.metrics.cacheHits + this.metrics.cacheMisses;
    return total > 0 ? this.metrics.cacheHits / total : 0;
  }

  // API metrics
  recordApiCall() {
    this.metrics.apiCalls++;
  }

  recordError() {
    this.metrics.errors++;
  }

  getErrorRate(): number {
    return this.metrics.apiCalls > 0 ? this.metrics.errors / this.metrics.apiCalls : 0;
  }

  // Latency metrics
  recordRecommendationLatency(latencyMs: number) {
    this.metrics.recommendationLatency.push(latencyMs);
    // Keep only last 1000 measurements
    if (this.metrics.recommendationLatency.length > 1000) {
      this.metrics.recommendationLatency.shift();
    }
  }

  recordMLScoringLatency(latencyMs: number) {
    this.metrics.mlScoringLatency.push(latencyMs);
    if (this.metrics.mlScoringLatency.length > 1000) {
      this.metrics.mlScoringLatency.shift();
    }
  }

  getAverageRecommendationLatency(): number {
    const latencies = this.metrics.recommendationLatency;
    return latencies.length > 0 
      ? latencies.reduce((sum, l) => sum + l, 0) / latencies.length 
      : 0;
  }

  getAverageMLScoringLatency(): number {
    const latencies = this.metrics.mlScoringLatency;
    return latencies.length > 0 
      ? latencies.reduce((sum, l) => sum + l, 0) / latencies.length 
      : 0;
  }

  getP95RecommendationLatency(): number {
    const latencies = [...this.metrics.recommendationLatency].sort((a, b) => a - b);
    const index = Math.floor(latencies.length * 0.95);
    return latencies[index] || 0;
  }

  // User interaction metrics
  recordUserInteraction() {
    this.metrics.userInteractions++;
  }

  recordSuccessfulRecommendation() {
    this.metrics.successfulRecommendations++;
  }

  getRecommendationSuccessRate(): number {
    return this.metrics.userInteractions > 0 
      ? this.metrics.successfulRecommendations / this.metrics.userInteractions 
      : 0;
  }

  // System metrics
  getUptime(): number {
    return Date.now() - this.startTime;
  }

  // Prometheus-style metrics export
  exportPrometheusMetrics(): string {
    const lines = [
      `# HELP rover_cache_hit_total Cache hits`,
      `# TYPE rover_cache_hit_total counter`,
      `rover_cache_hit_total ${this.metrics.cacheHits}`,
      
      `# HELP rover_cache_miss_total Cache misses`,
      `# TYPE rover_cache_miss_total counter`,
      `rover_cache_miss_total ${this.metrics.cacheMisses}`,
      
      `# HELP rover_api_calls_total API calls`,
      `# TYPE rover_api_calls_total counter`,
      `rover_api_calls_total ${this.metrics.apiCalls}`,
      
      `# HELP rover_errors_total Errors`,
      `# TYPE rover_errors_total counter`,
      `rover_errors_total ${this.metrics.errors}`,
      
      `# HELP rover_recommendation_latency_ms Recommendation latency`,
      `# TYPE rover_recommendation_latency_ms histogram`,
      `rover_recommendation_latency_ms_sum ${this.metrics.recommendationLatency.reduce((sum, l) => sum + l, 0)}`,
      `rover_recommendation_latency_ms_count ${this.metrics.recommendationLatency.length}`,
      
      `# HELP rover_ml_scoring_latency_ms ML scoring latency`,
      `# TYPE rover_ml_scoring_latency_ms histogram`,
      `rover_ml_scoring_latency_ms_sum ${this.metrics.mlScoringLatency.reduce((sum, l) => sum + l, 0)}`,
      `rover_ml_scoring_latency_ms_count ${this.metrics.mlScoringLatency.length}`,
      
      `# HELP rover_user_interactions_total User interactions`,
      `# TYPE rover_user_interactions_total counter`,
      `rover_user_interactions_total ${this.metrics.userInteractions}`,
      
      `# HELP rover_successful_recommendations_total Successful recommendations`,
      `# TYPE rover_successful_recommendations_total counter`,
      `rover_successful_recommendations_total ${this.metrics.successfulRecommendations}`,
      
      `# HELP rover_uptime_seconds Uptime`,
      `# TYPE rover_uptime_seconds gauge`,
      `rover_uptime_seconds ${Math.floor(this.getUptime() / 1000)}`
    ];
    
    return lines.join('\n');
  }

  // JSON export for debugging
  exportJSON() {
    return {
      ...this.metrics,
      cacheHitRate: this.getCacheHitRate(),
      errorRate: this.getErrorRate(),
      avgRecommendationLatency: this.getAverageRecommendationLatency(),
      avgMLScoringLatency: this.getAverageMLScoringLatency(),
      p95RecommendationLatency: this.getP95RecommendationLatency(),
      recommendationSuccessRate: this.getRecommendationSuccessRate(),
      uptimeMs: this.getUptime()
    };
  }

  // Reset metrics (useful for testing)
  reset() {
    this.metrics = {
      cacheHits: 0,
      cacheMisses: 0,
      apiCalls: 0,
      errors: 0,
      recommendationLatency: [],
      mlScoringLatency: [],
      userInteractions: 0,
      successfulRecommendations: 0
    };
    this.startTime = Date.now();
  }
}

export const roverMetrics = new RoverMetricsService();
