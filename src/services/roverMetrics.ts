interface RoverMetrics {
  mlScoringLatency: number[];
  startTime: number;
}

class RoverMetricsService {
  private metrics: RoverMetrics;

  constructor() {
    this.metrics = {
      mlScoringLatency: [],
      startTime: Date.now(),
    };
  }

  recordMLScoringLatency(latencyMs: number) {
    if (!Number.isFinite(latencyMs) || latencyMs < 0) {
      return;
    }

    this.metrics.mlScoringLatency.push(latencyMs);
    if (this.metrics.mlScoringLatency.length > 1000) {
      this.metrics.mlScoringLatency.shift();
    }
  }

  getAverageMLScoringLatency(): number {
    const latencies = this.metrics.mlScoringLatency;
    return latencies.length > 0
      ? latencies.reduce((sum, latency) => sum + latency, 0) / latencies.length
      : 0;
  }

  exportJSON() {
    return {
      avgMLScoringLatency: this.getAverageMLScoringLatency(),
      mlScoringSampleCount: this.metrics.mlScoringLatency.length,
      uptimeMs: Date.now() - this.metrics.startTime,
    };
  }

  reset() {
    this.metrics = {
      mlScoringLatency: [],
      startTime: Date.now(),
    };
  }
}

export const roverMetrics = new RoverMetricsService();
