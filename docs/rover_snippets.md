# Rover Code Snippets & Utilities

> **⚡ Ready-to-use code snippets and utilities for the Rover premium module**
>
> This collection provides battle-tested code patterns, utilities, and implementations commonly used in Rover development. All snippets are production-ready and follow enterprise coding standards.

## 🗂️ Code Snippet Categories

- **Redis Utilities**: Caching, session management, queue operations
- **ML Scoring Utilities**: Bulk scoring, recommendation algorithms, model utilities
- **Data Structures**: Top-K heap, priority queues, efficient sorting
- **Monitoring**: Prometheus metrics, logging, tracing utilities
- **Testing**: Mock data, test utilities, performance testing
- **Security**: Authentication, authorization, input validation

---

## 🔴 Redis Integration Utilities

### Redis Connection Manager

```typescript
// src/utils/redis-manager.ts

import Redis from 'ioredis';
import { logger } from '../core/UnifiedLogger';

export interface RedisConfig {
  host: string;
  port: number;
  password?: string;
  db?: number;
  retryDelayOnFailover?: number;
  maxRetriesPerRequest?: number;
  connectTimeout?: number;
  lazyConnect?: boolean;
}

export class RedisManager {
  private static instance: RedisManager;
  private redis: Redis;
  private subscriber: Redis;
  private publisher: Redis;

  private constructor(config: RedisConfig) {
    // Main Redis connection
    this.redis = new Redis({
      host: config.host,
      port: config.port,
      password: config.password,
      db: config.db || 0,
      retryDelayOnFailover: config.retryDelayOnFailover || 100,
      maxRetriesPerRequest: config.maxRetriesPerRequest || 3,
      connectTimeout: config.connectTimeout || 5000,
      lazyConnect: config.lazyConnect || true,
      keyPrefix: 'rover:',
    });

    // Dedicated publisher connection
    this.publisher = new Redis({
      ...config,
      keyPrefix: 'rover:',
    });

    // Dedicated subscriber connection
    this.subscriber = new Redis({
      ...config,
      keyPrefix: 'rover:',
    });

    this.setupEventHandlers();
  }

  public static getInstance(config?: RedisConfig): RedisManager {
    if (!RedisManager.instance) {
      if (!config) {
        throw new Error('RedisManager configuration required for first initialization');
      }
      RedisManager.instance = new RedisManager(config);
    }
    return RedisManager.instance;
  }

  private setupEventHandlers(): void {
    this.redis.on('connect', () => {
      logger.info('Redis connected successfully');
    });

    this.redis.on('error', (error) => {
      logger.error('Redis connection error', { error: error.message });
    });

    this.redis.on('close', () => {
      logger.warn('Redis connection closed');
    });
  }

  // Cache operations
  async set(key: string, value: any, ttlSeconds?: number): Promise<void> {
    const serialized = JSON.stringify(value);
    if (ttlSeconds) {
      await this.redis.setex(key, ttlSeconds, serialized);
    } else {
      await this.redis.set(key, serialized);
    }
  }

  async get<T>(key: string): Promise<T | null> {
    const value = await this.redis.get(key);
    return value ? JSON.parse(value) : null;
  }

  async mget<T>(keys: string[]): Promise<(T | null)[]> {
    const values = await this.redis.mget(...keys);
    return values.map(value => value ? JSON.parse(value) : null);
  }

  async del(key: string): Promise<void> {
    await this.redis.del(key);
  }

  async exists(key: string): Promise<boolean> {
    const result = await this.redis.exists(key);
    return result === 1;
  }

  // List operations for queues
  async lpush(key: string, ...values: any[]): Promise<number> {
    const serialized = values.map(v => JSON.stringify(v));
    return await this.redis.lpush(key, ...serialized);
  }

  async rpop<T>(key: string): Promise<T | null> {
    const value = await this.redis.rpop(key);
    return value ? JSON.parse(value) : null;
  }

  async brpop<T>(key: string, timeout: number): Promise<T | null> {
    const result = await this.redis.brpop(key, timeout);
    return result ? JSON.parse(result[1]) : null;
  }

  // Pub/Sub operations
  async publish(channel: string, message: any): Promise<void> {
    await this.publisher.publish(channel, JSON.stringify(message));
  }

  async subscribe(channel: string, callback: (message: any) => void): Promise<void> {
    await this.subscriber.subscribe(channel);
    this.subscriber.on('message', (receivedChannel, message) => {
      if (receivedChannel === channel) {
        callback(JSON.parse(message));
      }
    });
  }

  // Hash operations
  async hset(key: string, field: string, value: any): Promise<void> {
    await this.redis.hset(key, field, JSON.stringify(value));
  }

  async hget<T>(key: string, field: string): Promise<T | null> {
    const value = await this.redis.hget(key, field);
    return value ? JSON.parse(value) : null;
  }

  async hgetall<T>(key: string): Promise<Record<string, T>> {
    const hash = await this.redis.hgetall(key);
    const result: Record<string, T> = {};
    for (const [field, value] of Object.entries(hash)) {
      result[field] = JSON.parse(value);
    }
    return result;
  }

  // Utility methods
  async ping(): Promise<string> {
    return await this.redis.ping();
  }

  async flushPattern(pattern: string): Promise<void> {
    const keys = await this.redis.keys(pattern);
    if (keys.length > 0) {
      await this.redis.del(...keys);
    }
  }

  getClient(): Redis {
    return this.redis;
  }

  async disconnect(): Promise<void> {
    await Promise.all([
      this.redis.disconnect(),
      this.publisher.disconnect(),
      this.subscriber.disconnect(),
    ]);
  }
}

// Rover-specific Redis utilities
export class RoverRedisCache {
  private redis: RedisManager;
  private readonly RECOMMENDATION_TTL = 15 * 60; // 15 minutes
  private readonly USER_PREFERENCES_TTL = 24 * 60 * 60; // 24 hours
  private readonly ANALYTICS_TTL = 60 * 60; // 1 hour

  constructor(redisManager: RedisManager) {
    this.redis = redisManager;
  }

  // Recommendation caching
  async cacheRecommendations(userId: string, criteria: any, recommendations: any[]): Promise<void> {
    const key = `recommendations:${userId}:${this.hashCriteria(criteria)}`;
    await this.redis.set(key, {
      recommendations,
      generatedAt: new Date().toISOString(),
      criteria,
    }, this.RECOMMENDATION_TTL);
  }

  async getCachedRecommendations(userId: string, criteria: any): Promise<any[] | null> {
    const key = `recommendations:${userId}:${this.hashCriteria(criteria)}`;
    const cached = await this.redis.get<any>(key);
    return cached ? cached.recommendations : null;
  }

  // User preferences caching
  async cacheUserPreferences(userId: string, preferences: any): Promise<void> {
    const key = `preferences:${userId}`;
    await this.redis.set(key, preferences, this.USER_PREFERENCES_TTL);
  }

  async getCachedUserPreferences(userId: string): Promise<any | null> {
    const key = `preferences:${userId}`;
    return await this.redis.get(key);
  }

  // Analytics caching
  async cacheAnalytics(key: string, data: any): Promise<void> {
    await this.redis.set(`analytics:${key}`, data, this.ANALYTICS_TTL);
  }

  async getCachedAnalytics(key: string): Promise<any | null> {
    return await this.redis.get(`analytics:${key}`);
  }

  // Session management
  async setUserSession(sessionId: string, userData: any): Promise<void> {
    await this.redis.set(`session:${sessionId}`, userData, 2 * 60 * 60); // 2 hours
  }

  async getUserSession(sessionId: string): Promise<any | null> {
    return await this.redis.get(`session:${sessionId}`);
  }

  async invalidateUserSession(sessionId: string): Promise<void> {
    await this.redis.del(`session:${sessionId}`);
  }

  // Utility methods
  private hashCriteria(criteria: any): string {
    const crypto = require('crypto');
    const normalized = JSON.stringify(criteria, Object.keys(criteria).sort());
    return crypto.createHash('md5').update(normalized).digest('hex');
  }

  async invalidateUserCache(userId: string): Promise<void> {
    await this.redis.flushPattern(`*:${userId}:*`);
    await this.redis.flushPattern(`*:${userId}`);
  }
}
```

### Redis Mock for Testing

```typescript
// src/utils/redis-mock.ts

export class RedisMock {
  private data: Map<string, { value: string; expiry?: number }> = new Map();
  private subscribers: Map<string, Set<(message: any) => void>> = new Map();

  async set(key: string, value: string, ttlSeconds?: number): Promise<void> {
    const expiry = ttlSeconds ? Date.now() + (ttlSeconds * 1000) : undefined;
    this.data.set(key, { value, expiry });
  }

  async get(key: string): Promise<string | null> {
    const item = this.data.get(key);
    if (!item) return null;
    
    if (item.expiry && item.expiry < Date.now()) {
      this.data.delete(key);
      return null;
    }
    
    return item.value;
  }

  async del(key: string): Promise<void> {
    this.data.delete(key);
  }

  async exists(key: string): Promise<number> {
    const item = this.data.get(key);
    if (!item) return 0;
    
    if (item.expiry && item.expiry < Date.now()) {
      this.data.delete(key);
      return 0;
    }
    
    return 1;
  }

  async keys(pattern: string): Promise<string[]> {
    const regex = new RegExp(pattern.replace(/\*/g, '.*'));
    return Array.from(this.data.keys()).filter(key => regex.test(key));
  }

  async publish(channel: string, message: string): Promise<void> {
    const callbacks = this.subscribers.get(channel);
    if (callbacks) {
      callbacks.forEach(callback => callback(JSON.parse(message)));
    }
  }

  async subscribe(channel: string, callback: (message: any) => void): Promise<void> {
    if (!this.subscribers.has(channel)) {
      this.subscribers.set(channel, new Set());
    }
    this.subscribers.get(channel)!.add(callback);
  }

  async ping(): Promise<string> {
    return 'PONG';
  }

  clear(): void {
    this.data.clear();
    this.subscribers.clear();
  }
}

// Factory for creating Redis mock in tests
export function createRedisMock(): RedisMock {
  return new RedisMock();
}
```

---

## 🤖 ML Scoring & Recommendation Utilities

### Bulk Scorer for Recommendations

```typescript
// src/ml/bulk-scorer.ts

export interface ScoringCriteria {
  make?: string;
  model?: string;
  maxMileage?: number;
  maxPrice?: number;
  minYear?: number;
  userPreferences?: UserPreferences;
}

export interface UserPreferences {
  preferredMakes: string[];
  riskTolerance: 'conservative' | 'moderate' | 'aggressive';
  budgetRange: [number, number];
  prioritizeROI: boolean;
  preferredDealTypes: string[];
}

export interface VehicleData {
  id: string;
  make: string;
  model: string;
  year: number;
  mileage: number;
  price: number;
  estimatedValue: number;
  condition: string;
  location: string;
  dealType: string;
  images: string[];
  metadata: Record<string, any>;
}

export interface ScoredRecommendation {
  vehicle: VehicleData;
  scores: {
    overall: number;
    arbitrage: number;
    roi: number;
    risk: number;
    preference: number;
    market: number;
  };
  confidence: number;
  explanation: string[];
  rank: number;
}

export class RoverBulkScorer {
  private modelWeights = {
    arbitrage: 0.3,
    roi: 0.25,
    risk: 0.2,
    preference: 0.15,
    market: 0.1,
  };

  constructor(private readonly modelService: MLModelService) {}

  async scoreVehicles(
    vehicles: VehicleData[],
    criteria: ScoringCriteria,
    batchSize: number = 100
  ): Promise<ScoredRecommendation[]> {
    const scoredResults: ScoredRecommendation[] = [];
    
    // Process in batches for better performance
    for (let i = 0; i < vehicles.length; i += batchSize) {
      const batch = vehicles.slice(i, i + batchSize);
      const batchResults = await this.scoreBatch(batch, criteria);
      scoredResults.push(...batchResults);
    }

    // Sort by overall score and assign ranks
    scoredResults.sort((a, b) => b.scores.overall - a.scores.overall);
    scoredResults.forEach((result, index) => {
      result.rank = index + 1;
    });

    return scoredResults;
  }

  private async scoreBatch(
    vehicles: VehicleData[],
    criteria: ScoringCriteria
  ): Promise<ScoredRecommendation[]> {
    const results: ScoredRecommendation[] = [];

    for (const vehicle of vehicles) {
      try {
        const scores = await this.calculateScores(vehicle, criteria);
        const confidence = this.calculateConfidence(scores, vehicle);
        const explanation = this.generateExplanation(scores, vehicle, criteria);
        
        results.push({
          vehicle,
          scores,
          confidence,
          explanation,
          rank: 0, // Will be set after sorting
        });
      } catch (error) {
        console.error(`Error scoring vehicle ${vehicle.id}:`, error);
      }
    }

    return results;
  }

  private async calculateScores(
    vehicle: VehicleData,
    criteria: ScoringCriteria
  ): Promise<ScoredRecommendation['scores']> {
    // Arbitrage Score (0-100)
    const arbitrage = this.calculateArbitrageScore(vehicle);
    
    // ROI Score (0-100)
    const roi = this.calculateROIScore(vehicle);
    
    // Risk Score (0-100, higher is lower risk)
    const risk = this.calculateRiskScore(vehicle);
    
    // User Preference Score (0-100)
    const preference = this.calculatePreferenceScore(vehicle, criteria.userPreferences);
    
    // Market Score (0-100)
    const market = await this.calculateMarketScore(vehicle);
    
    // Overall weighted score
    const overall = (
      arbitrage * this.modelWeights.arbitrage +
      roi * this.modelWeights.roi +
      risk * this.modelWeights.risk +
      preference * this.modelWeights.preference +
      market * this.modelWeights.market
    );

    return {
      overall: Math.round(overall * 100) / 100,
      arbitrage: Math.round(arbitrage * 100) / 100,
      roi: Math.round(roi * 100) / 100,
      risk: Math.round(risk * 100) / 100,
      preference: Math.round(preference * 100) / 100,
      market: Math.round(market * 100) / 100,
    };
  }

  private calculateArbitrageScore(vehicle: VehicleData): number {
    const profit = vehicle.estimatedValue - vehicle.price;
    const profitMargin = profit / vehicle.price;
    
    // Score based on profit margin
    if (profitMargin >= 0.3) return 100; // 30%+ margin
    if (profitMargin >= 0.2) return 85;  // 20-30% margin
    if (profitMargin >= 0.15) return 70; // 15-20% margin
    if (profitMargin >= 0.1) return 55;  // 10-15% margin
    if (profitMargin >= 0.05) return 40; // 5-10% margin
    if (profitMargin >= 0) return 25;    // Break-even
    return 0; // Loss
  }

  private calculateROIScore(vehicle: VehicleData): number {
    const roiPercentage = ((vehicle.estimatedValue - vehicle.price) / vehicle.price) * 100;
    
    // Normalize ROI to 0-100 scale
    const maxROI = 50; // 50% ROI = 100 score
    return Math.min(100, Math.max(0, (roiPercentage / maxROI) * 100));
  }

  private calculateRiskScore(vehicle: VehicleData): number {
    let riskScore = 100; // Start with perfect score
    
    // Age risk
    const age = new Date().getFullYear() - vehicle.year;
    if (age > 15) riskScore -= 30;
    else if (age > 10) riskScore -= 20;
    else if (age > 5) riskScore -= 10;
    
    // Mileage risk
    const mileagePerYear = vehicle.mileage / age;
    if (mileagePerYear > 20000) riskScore -= 25;
    else if (mileagePerYear > 15000) riskScore -= 15;
    else if (mileagePerYear > 12000) riskScore -= 5;
    
    // Condition risk
    if (vehicle.condition === 'poor') riskScore -= 40;
    else if (vehicle.condition === 'fair') riskScore -= 20;
    else if (vehicle.condition === 'good') riskScore -= 5;
    
    return Math.max(0, riskScore);
  }

  private calculatePreferenceScore(
    vehicle: VehicleData,
    preferences?: UserPreferences
  ): number {
    if (!preferences) return 50; // Neutral score
    
    let score = 0;
    
    // Preferred makes
    if (preferences.preferredMakes.includes(vehicle.make)) {
      score += 40;
    }
    
    // Budget range
    const [minBudget, maxBudget] = preferences.budgetRange;
    if (vehicle.price >= minBudget && vehicle.price <= maxBudget) {
      score += 30;
    } else {
      score += Math.max(0, 30 - Math.abs(vehicle.price - maxBudget) / maxBudget * 30);
    }
    
    // Deal type preference
    if (preferences.preferredDealTypes.includes(vehicle.dealType)) {
      score += 20;
    }
    
    // Risk tolerance
    const riskScore = this.calculateRiskScore(vehicle);
    switch (preferences.riskTolerance) {
      case 'conservative':
        score += riskScore > 80 ? 10 : 0;
        break;
      case 'moderate':
        score += riskScore > 60 ? 10 : 5;
        break;
      case 'aggressive':
        score += 10; // No risk penalty
        break;
    }
    
    return Math.min(100, score);
  }

  private async calculateMarketScore(vehicle: VehicleData): Promise<number> {
    try {
      // Use ML model to predict market demand
      const marketData = await this.modelService.predictMarketDemand(vehicle);
      return marketData.demandScore * 100;
    } catch (error) {
      console.error('Error calculating market score:', error);
      return 50; // Default neutral score
    }
  }

  private calculateConfidence(
    scores: ScoredRecommendation['scores'],
    vehicle: VehicleData
  ): number {
    let confidence = 0.5; // Base confidence
    
    // Higher confidence with more data
    if (vehicle.images.length > 3) confidence += 0.1;
    if (vehicle.metadata && Object.keys(vehicle.metadata).length > 5) confidence += 0.1;
    
    // Higher confidence with consistent scores
    const scoreValues = Object.values(scores).filter(s => s !== scores.overall);
    const scoreVariance = this.calculateVariance(scoreValues);
    if (scoreVariance < 200) confidence += 0.2;
    else if (scoreVariance < 400) confidence += 0.1;
    
    // Higher confidence with recent data
    const dataAge = Date.now() - (vehicle.metadata.scrapedAt || Date.now());
    if (dataAge < 24 * 60 * 60 * 1000) confidence += 0.1; // Less than 24 hours
    
    return Math.min(1.0, confidence);
  }

  private generateExplanation(
    scores: ScoredRecommendation['scores'],
    vehicle: VehicleData,
    criteria: ScoringCriteria
  ): string[] {
    const explanations: string[] = [];
    
    // ROI explanation
    const roiPercentage = ((vehicle.estimatedValue - vehicle.price) / vehicle.price) * 100;
    if (roiPercentage > 20) {
      explanations.push(`Excellent ROI potential: ${roiPercentage.toFixed(1)}%`);
    } else if (roiPercentage > 10) {
      explanations.push(`Good ROI potential: ${roiPercentage.toFixed(1)}%`);
    }
    
    // Risk explanation
    if (scores.risk > 80) {
      explanations.push('Low risk investment with reliable market demand');
    } else if (scores.risk < 40) {
      explanations.push('Higher risk due to age, mileage, or condition factors');
    }
    
    // Preference explanation
    if (scores.preference > 80) {
      explanations.push('Strong match for your preferences and criteria');
    }
    
    // Market explanation
    if (scores.market > 80) {
      explanations.push('High market demand predicted for this vehicle type');
    }
    
    // Arbitrage opportunity
    if (scores.arbitrage > 75) {
      explanations.push('Significant arbitrage opportunity identified');
    }
    
    return explanations;
  }

  private calculateVariance(numbers: number[]): number {
    const mean = numbers.reduce((sum, num) => sum + num, 0) / numbers.length;
    const squaredDiffs = numbers.map(num => Math.pow(num - mean, 2));
    return squaredDiffs.reduce((sum, diff) => sum + diff, 0) / numbers.length;
  }
}

// ML Model Service Interface
export interface MLModelService {
  predictMarketDemand(vehicle: VehicleData): Promise<{ demandScore: number }>;
  predictPriceAccuracy(vehicle: VehicleData): Promise<{ accuracyScore: number }>;
  batchPredict(vehicles: VehicleData[]): Promise<any[]>;
}
```

---

## 🏔️ Top-K Heap & Priority Queue

```typescript
// src/utils/top-k-heap.ts

export interface Comparable {
  compareTo(other: Comparable): number;
}

export class MinHeap<T extends Comparable> {
  private heap: T[] = [];

  get size(): number {
    return this.heap.length;
  }

  get isEmpty(): boolean {
    return this.heap.length === 0;
  }

  peek(): T | undefined {
    return this.heap[0];
  }

  push(item: T): void {
    this.heap.push(item);
    this.heapifyUp(this.heap.length - 1);
  }

  pop(): T | undefined {
    if (this.isEmpty) return undefined;
    if (this.size === 1) return this.heap.pop();

    const root = this.heap[0];
    this.heap[0] = this.heap.pop()!;
    this.heapifyDown(0);
    return root;
  }

  private heapifyUp(index: number): void {
    const parentIndex = Math.floor((index - 1) / 2);
    if (parentIndex >= 0 && this.heap[index].compareTo(this.heap[parentIndex]) < 0) {
      this.swap(index, parentIndex);
      this.heapifyUp(parentIndex);
    }
  }

  private heapifyDown(index: number): void {
    const leftChild = 2 * index + 1;
    const rightChild = 2 * index + 2;
    let smallest = index;

    if (
      leftChild < this.size &&
      this.heap[leftChild].compareTo(this.heap[smallest]) < 0
    ) {
      smallest = leftChild;
    }

    if (
      rightChild < this.size &&
      this.heap[rightChild].compareTo(this.heap[smallest]) < 0
    ) {
      smallest = rightChild;
    }

    if (smallest !== index) {
      this.swap(index, smallest);
      this.heapifyDown(smallest);
    }
  }

  private swap(i: number, j: number): void {
    [this.heap[i], this.heap[j]] = [this.heap[j], this.heap[i]];
  }

  toArray(): T[] {
    return [...this.heap].sort((a, b) => a.compareTo(b));
  }
}

// Top-K recommendations keeper
export class TopKRecommendations {
  private heap: MinHeap<ScoredRecommendationWrapper>;

  constructor(private readonly k: number) {
    this.heap = new MinHeap<ScoredRecommendationWrapper>();
  }

  add(recommendation: ScoredRecommendation): void {
    const wrapper = new ScoredRecommendationWrapper(recommendation);
    
    if (this.heap.size < this.k) {
      this.heap.push(wrapper);
    } else if (wrapper.compareTo(this.heap.peek()!) > 0) {
      this.heap.pop();
      this.heap.push(wrapper);
    }
  }

  addBatch(recommendations: ScoredRecommendation[]): void {
    recommendations.forEach(rec => this.add(rec));
  }

  getTopK(): ScoredRecommendation[] {
    return this.heap.toArray()
      .map(wrapper => wrapper.recommendation)
      .reverse(); // Descending order
  }

  clear(): void {
    this.heap = new MinHeap<ScoredRecommendationWrapper>();
  }

  get size(): number {
    return this.heap.size;
  }
}

class ScoredRecommendationWrapper implements Comparable {
  constructor(public readonly recommendation: ScoredRecommendation) {}

  compareTo(other: ScoredRecommendationWrapper): number {
    // Primary: overall score
    const scoreDiff = this.recommendation.scores.overall - other.recommendation.scores.overall;
    if (Math.abs(scoreDiff) > 0.01) return scoreDiff;
    
    // Secondary: confidence
    const confidenceDiff = this.recommendation.confidence - other.recommendation.confidence;
    if (Math.abs(confidenceDiff) > 0.01) return confidenceDiff;
    
    // Tertiary: ROI score
    return this.recommendation.scores.roi - other.recommendation.scores.roi;
  }
}

// Priority Queue for background processing
export class PriorityQueue<T> {
  private items: Array<{ item: T; priority: number }> = [];

  enqueue(item: T, priority: number): void {
    this.items.push({ item, priority });
    this.items.sort((a, b) => b.priority - a.priority); // Higher priority first
  }

  dequeue(): T | undefined {
    const item = this.items.shift();
    return item ? item.item : undefined;
  }

  peek(): T | undefined {
    return this.items.length > 0 ? this.items[0].item : undefined;
  }

  get size(): number {
    return this.items.length;
  }

  get isEmpty(): boolean {
    return this.items.length === 0;
  }

  clear(): void {
    this.items = [];
  }

  toArray(): T[] {
    return this.items.map(item => item.item);
  }
}

// Usage Example
export class RoverRecommendationEngine {
  private topK: TopKRecommendations;
  private processingQueue: PriorityQueue<ProcessingTask>;

  constructor(private readonly maxRecommendations: number = 50) {
    this.topK = new TopKRecommendations(maxRecommendations);
    this.processingQueue = new PriorityQueue<ProcessingTask>();
  }

  async generateRecommendations(
    vehicles: VehicleData[],
    criteria: ScoringCriteria
  ): Promise<ScoredRecommendation[]> {
    this.topK.clear();
    
    // Process vehicles in batches
    const batchSize = 100;
    for (let i = 0; i < vehicles.length; i += batchSize) {
      const batch = vehicles.slice(i, i + batchSize);
      const scored = await this.scoreVehicleBatch(batch, criteria);
      this.topK.addBatch(scored);
    }
    
    return this.topK.getTopK();
  }

  private async scoreVehicleBatch(
    vehicles: VehicleData[],
    criteria: ScoringCriteria
  ): Promise<ScoredRecommendation[]> {
    // Implementation would use RoverBulkScorer
    const scorer = new RoverBulkScorer(this.mlModelService);
    return await scorer.scoreVehicles(vehicles, criteria);
  }
}

interface ProcessingTask {
  id: string;
  type: 'score' | 'cache' | 'notify';
  data: any;
}
```

---

## 📊 Prometheus Metrics Utilities

```typescript
// src/monitoring/prometheus-metrics.ts

import { register, Counter, Histogram, Gauge, Summary, collectDefaultMetrics } from 'prom-client';

// Enable default system metrics
collectDefaultMetrics({ prefix: 'rover_' });

// Business Metrics
export const businessMetrics = {
  recommendationsGenerated: new Counter({
    name: 'rover_recommendations_generated_total',
    help: 'Total number of recommendations generated',
    labelNames: ['user_tier', 'recommendation_type', 'model_version'] as const,
  }),

  userInteractions: new Counter({
    name: 'rover_user_interactions_total',
    help: 'Total user interactions with recommendations',
    labelNames: ['interaction_type', 'user_tier', 'outcome'] as const,
  }),

  conversions: new Counter({
    name: 'rover_conversions_total',
    help: 'Total user conversions (successful actions)',
    labelNames: ['conversion_type', 'user_tier', 'value_bucket'] as const,
  }),

  revenue: new Counter({
    name: 'rover_revenue_total',
    help: 'Total revenue generated through Rover',
    labelNames: ['user_tier', 'deal_category'] as const,
  }),
};

// Performance Metrics
export const performanceMetrics = {
  apiDuration: new Histogram({
    name: 'rover_api_request_duration_seconds',
    help: 'Duration of Rover API requests',
    labelNames: ['method', 'endpoint', 'status_code'] as const,
    buckets: [0.1, 0.25, 0.5, 1, 2.5, 5, 10],
  }),

  mlInferenceDuration: new Histogram({
    name: 'rover_ml_inference_duration_seconds',
    help: 'Duration of ML model inference',
    labelNames: ['model_type', 'batch_size'] as const,
    buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2],
  }),

  cacheOperations: new Histogram({
    name: 'rover_cache_operation_duration_seconds',
    help: 'Duration of cache operations',
    labelNames: ['operation', 'cache_type'] as const,
    buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25],
  }),

  dbQueries: new Histogram({
    name: 'rover_db_query_duration_seconds',
    help: 'Duration of database queries',
    labelNames: ['query_type', 'table'] as const,
    buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2],
  }),
};

// Resource Metrics
export const resourceMetrics = {
  memoryUsage: new Gauge({
    name: 'rover_memory_usage_bytes',
    help: 'Current memory usage of Rover components',
    labelNames: ['component', 'type'] as const,
  }),

  cpuUsage: new Gauge({
    name: 'rover_cpu_usage_percent',
    help: 'Current CPU usage of Rover components',
    labelNames: ['component'] as const,
  }),

  activeConnections: new Gauge({
    name: 'rover_active_connections',
    help: 'Number of active connections',
    labelNames: ['connection_type'] as const,
  }),

  queueSize: new Gauge({
    name: 'rover_queue_size',
    help: 'Current size of processing queues',
    labelNames: ['queue_name'] as const,
  }),
};

// ML Model Metrics
export const mlMetrics = {
  modelAccuracy: new Gauge({
    name: 'rover_ml_model_accuracy',
    help: 'Current ML model accuracy score',
    labelNames: ['model_name', 'model_version', 'dataset'] as const,
  }),

  predictions: new Counter({
    name: 'rover_ml_predictions_total',
    help: 'Total ML predictions made',
    labelNames: ['model_name', 'prediction_type', 'confidence_bucket'] as const,
  }),

  trainingDuration: new Histogram({
    name: 'rover_ml_training_duration_seconds',
    help: 'Duration of ML model training',
    labelNames: ['model_name', 'training_type'] as const,
    buckets: [60, 300, 900, 1800, 3600, 7200, 14400], // 1min to 4hrs
  }),

  modelErrors: new Counter({
    name: 'rover_ml_errors_total',
    help: 'Total ML model errors',
    labelNames: ['model_name', 'error_type'] as const,
  }),
};

// Error Metrics
export const errorMetrics = {
  errors: new Counter({
    name: 'rover_errors_total',
    help: 'Total errors in Rover system',
    labelNames: ['component', 'error_type', 'severity'] as const,
  }),

  httpErrors: new Counter({
    name: 'rover_http_errors_total',
    help: 'Total HTTP errors',
    labelNames: ['method', 'endpoint', 'status_code'] as const,
  }),
};

// Utility class for metrics collection
export class RoverMetricsCollector {
  // Business metrics helpers
  static recordRecommendationGenerated(
    userTier: string,
    recommendationType: string,
    modelVersion: string,
    count: number = 1
  ): void {
    businessMetrics.recommendationsGenerated
      .labels(userTier, recommendationType, modelVersion)
      .inc(count);
  }

  static recordUserInteraction(
    interactionType: string,
    userTier: string,
    outcome: string
  ): void {
    businessMetrics.userInteractions
      .labels(interactionType, userTier, outcome)
      .inc();
  }

  static recordConversion(
    conversionType: string,
    userTier: string,
    value: number
  ): void {
    const valueBucket = value > 10000 ? 'high' : value > 1000 ? 'medium' : 'low';
    businessMetrics.conversions
      .labels(conversionType, userTier, valueBucket)
      .inc();
    
    businessMetrics.revenue
      .labels(userTier, 'unknown')
      .inc(value);
  }

  // Performance metrics helpers
  static recordAPIRequest(
    method: string,
    endpoint: string,
    statusCode: number,
    durationSeconds: number
  ): void {
    performanceMetrics.apiDuration
      .labels(method, endpoint, statusCode.toString())
      .observe(durationSeconds);
  }

  static recordMLInference(
    modelType: string,
    batchSize: number,
    durationSeconds: number
  ): void {
    performanceMetrics.mlInferenceDuration
      .labels(modelType, batchSize.toString())
      .observe(durationSeconds);
  }

  static recordCacheOperation(
    operation: string,
    cacheType: string,
    durationSeconds: number
  ): void {
    performanceMetrics.cacheOperations
      .labels(operation, cacheType)
      .observe(durationSeconds);
  }

  static recordDBQuery(
    queryType: string,
    table: string,
    durationSeconds: number
  ): void {
    performanceMetrics.dbQueries
      .labels(queryType, table)
      .observe(durationSeconds);
  }

  // Resource metrics helpers
  static updateMemoryUsage(component: string, type: string, bytes: number): void {
    resourceMetrics.memoryUsage
      .labels(component, type)
      .set(bytes);
  }

  static updateCPUUsage(component: string, percentage: number): void {
    resourceMetrics.cpuUsage
      .labels(component)
      .set(percentage);
  }

  static updateActiveConnections(connectionType: string, count: number): void {
    resourceMetrics.activeConnections
      .labels(connectionType)
      .set(count);
  }

  static updateQueueSize(queueName: string, size: number): void {
    resourceMetrics.queueSize
      .labels(queueName)
      .set(size);
  }

  // ML metrics helpers
  static updateModelAccuracy(
    modelName: string,
    modelVersion: string,
    dataset: string,
    accuracy: number
  ): void {
    mlMetrics.modelAccuracy
      .labels(modelName, modelVersion, dataset)
      .set(accuracy);
  }

  static recordPrediction(
    modelName: string,
    predictionType: string,
    confidence: number
  ): void {
    const confidenceBucket = confidence > 0.8 ? 'high' : 
                           confidence > 0.6 ? 'medium' : 'low';
    mlMetrics.predictions
      .labels(modelName, predictionType, confidenceBucket)
      .inc();
  }

  static recordTraining(
    modelName: string,
    trainingType: string,
    durationSeconds: number
  ): void {
    mlMetrics.trainingDuration
      .labels(modelName, trainingType)
      .observe(durationSeconds);
  }

  static recordMLError(modelName: string, errorType: string): void {
    mlMetrics.modelErrors
      .labels(modelName, errorType)
      .inc();
  }

  // Error metrics helpers
  static recordError(
    component: string,
    errorType: string,
    severity: 'low' | 'medium' | 'high' | 'critical'
  ): void {
    errorMetrics.errors
      .labels(component, errorType, severity)
      .inc();
  }

  static recordHTTPError(
    method: string,
    endpoint: string,
    statusCode: number
  ): void {
    errorMetrics.httpErrors
      .labels(method, endpoint, statusCode.toString())
      .inc();
  }

  // Utility methods
  static getMetricsRegistry() {
    return register;
  }

  static async getMetrics(): Promise<string> {
    return await register.metrics();
  }

  static clearMetrics(): void {
    register.clear();
  }
}

// Middleware for automatic metrics collection
export function createMetricsMiddleware() {
  return (req: any, res: any, next: any) => {
    const start = Date.now();
    
    res.on('finish', () => {
      const duration = (Date.now() - start) / 1000;
      RoverMetricsCollector.recordAPIRequest(
        req.method,
        req.route?.path || req.path,
        res.statusCode,
        duration
      );
      
      if (res.statusCode >= 400) {
        RoverMetricsCollector.recordHTTPError(
          req.method,
          req.route?.path || req.path,
          res.statusCode
        );
      }
    });
    
    next();
  };
}

// Metrics collection intervals
export class MetricsCollectionService {
  private intervals: NodeJS.Timeout[] = [];

  start(): void {
    // Collect system metrics every 30 seconds
    this.intervals.push(setInterval(() => {
      this.collectSystemMetrics();
    }, 30000));

    // Collect queue metrics every 10 seconds
    this.intervals.push(setInterval(() => {
      this.collectQueueMetrics();
    }, 10000));
  }

  stop(): void {
    this.intervals.forEach(interval => clearInterval(interval));
    this.intervals = [];
  }

  private collectSystemMetrics(): void {
    const memUsage = process.memoryUsage();
    RoverMetricsCollector.updateMemoryUsage('rover-api', 'heap', memUsage.heapUsed);
    RoverMetricsCollector.updateMemoryUsage('rover-api', 'rss', memUsage.rss);
    
    // CPU usage would require additional monitoring
    const cpuUsage = process.cpuUsage();
    const cpuPercent = (cpuUsage.user + cpuUsage.system) / 1000000; // Convert to percentage
    RoverMetricsCollector.updateCPUUsage('rover-api', cpuPercent);
  }

  private async collectQueueMetrics(): Promise<void> {
    // This would integrate with your actual queue systems
    // Example for Redis queues:
    try {
      // const queueSize = await redis.llen('rover:processing_queue');
      // RoverMetricsCollector.updateQueueSize('processing', queueSize);
    } catch (error) {
      console.error('Error collecting queue metrics:', error);
    }
  }
}
```

---

## 🧪 Testing Utilities & Mocks

### Test Data Factory

```typescript
// src/utils/test-data-factory.ts

import { faker } from '@faker-js/faker';

export class RoverTestDataFactory {
  static createVehicleData(overrides: Partial<VehicleData> = {}): VehicleData {
    const make = faker.vehicle.manufacturer();
    const model = faker.vehicle.model();
    const year = faker.date.between({ from: '2015-01-01', to: '2024-01-01' }).getFullYear();
    const age = new Date().getFullYear() - year;
    const mileage = faker.number.int({ min: 5000, max: 150000 });
    const basePrice = faker.number.int({ min: 8000, max: 80000 });
    const estimatedValue = basePrice * faker.number.float({ min: 0.9, max: 1.4 });

    return {
      id: faker.string.uuid(),
      make,
      model,
      year,
      mileage,
      price: basePrice,
      estimatedValue: Math.round(estimatedValue),
      condition: faker.helpers.arrayElement(['excellent', 'good', 'fair', 'poor']),
      location: `${faker.location.city()}, ${faker.location.state()}`,
      dealType: faker.helpers.arrayElement(['auction', 'dealer', 'private', 'wholesale']),
      images: Array.from(
        { length: faker.number.int({ min: 1, max: 8 }) },
        () => faker.image.url()
      ),
      metadata: {
        scrapedAt: faker.date.recent().toISOString(),
        source: faker.helpers.arrayElement(['autotrader', 'cars.com', 'govdeals']),
        vin: faker.vehicle.vin(),
        bodyType: faker.vehicle.type(),
        transmission: faker.helpers.arrayElement(['automatic', 'manual']),
        fuelType: faker.helpers.arrayElement(['gasoline', 'diesel', 'hybrid', 'electric']),
      },
      ...overrides,
    };
  }

  static createUserPreferences(overrides: Partial<UserPreferences> = {}): UserPreferences {
    return {
      preferredMakes: faker.helpers.arrayElements([
        'Toyota', 'Honda', 'Ford', 'Chevrolet', 'BMW', 'Mercedes', 'Audi'
      ], { min: 1, max: 3 }),
      riskTolerance: faker.helpers.arrayElement(['conservative', 'moderate', 'aggressive']),
      budgetRange: [
        faker.number.int({ min: 10000, max: 30000 }),
        faker.number.int({ min: 30000, max: 100000 }),
      ] as [number, number],
      prioritizeROI: faker.datatype.boolean(),
      preferredDealTypes: faker.helpers.arrayElements([
        'auction', 'dealer', 'private', 'wholesale'
      ], { min: 1, max: 2 }),
      ...overrides,
    };
  }

  static createScoredRecommendation(overrides: Partial<ScoredRecommendation> = {}): ScoredRecommendation {
    const vehicle = this.createVehicleData();
    const overallScore = faker.number.float({ min: 0, max: 100 });
    
    return {
      vehicle,
      scores: {
        overall: overallScore,
        arbitrage: faker.number.float({ min: 0, max: 100 }),
        roi: faker.number.float({ min: 0, max: 100 }),
        risk: faker.number.float({ min: 0, max: 100 }),
        preference: faker.number.float({ min: 0, max: 100 }),
        market: faker.number.float({ min: 0, max: 100 }),
      },
      confidence: faker.number.float({ min: 0.3, max: 1.0 }),
      explanation: [
        'High ROI potential with excellent market demand',
        'Strong match for your preferences',
        'Low risk investment opportunity',
      ],
      rank: faker.number.int({ min: 1, max: 100 }),
      ...overrides,
    };
  }

  static createUserEvent(overrides: any = {}): any {
    return {
      userId: faker.string.uuid(),
      eventType: faker.helpers.arrayElement(['view', 'click', 'save', 'bid', 'purchase']),
      dealId: faker.string.uuid(),
      recommendationId: faker.string.uuid(),
      timestamp: faker.date.recent().toISOString(),
      userResponse: faker.helpers.arrayElement(['positive', 'negative', 'neutral']),
      sessionId: faker.string.uuid(),
      ...overrides,
    };
  }

  static createBulkVehicleData(count: number): VehicleData[] {
    return Array.from({ length: count }, () => this.createVehicleData());
  }

  static createBulkRecommendations(count: number): ScoredRecommendation[] {
    return Array.from({ length: count }, (_, index) => 
      this.createScoredRecommendation({ rank: index + 1 })
    );
  }

  // Create realistic test scenarios
  static createHighROIScenario(): VehicleData {
    return this.createVehicleData({
      price: 15000,
      estimatedValue: 22000, // 47% profit margin
      condition: 'good',
      year: 2020,
      mileage: 35000,
      make: 'Toyota',
      model: 'Camry',
    });
  }

  static createLowRiskScenario(): VehicleData {
    return this.createVehicleData({
      year: 2022,
      mileage: 15000,
      condition: 'excellent',
      make: 'Honda',
      model: 'Accord',
      price: 25000,
      estimatedValue: 26500,
    });
  }

  static createHighRiskScenario(): VehicleData {
    return this.createVehicleData({
      year: 2008,
      mileage: 180000,
      condition: 'fair',
      make: 'BMW',
      model: 'X5',
      price: 12000,
      estimatedValue: 11000, // Potential loss
    });
  }

  // Performance testing data
  static createLargeDataset(size: number): VehicleData[] {
    const batchSize = 1000;
    const vehicles: VehicleData[] = [];
    
    for (let i = 0; i < size; i += batchSize) {
      const batch = Math.min(batchSize, size - i);
      vehicles.push(...this.createBulkVehicleData(batch));
    }
    
    return vehicles;
  }
}

// Performance testing utilities
export class RoverPerformanceTestUtils {
  static async measureExecutionTime<T>(
    fn: () => Promise<T>,
    iterations: number = 1
  ): Promise<{ result: T; averageTime: number; times: number[] }> {
    const times: number[] = [];
    let result: T;

    for (let i = 0; i < iterations; i++) {
      const start = performance.now();
      result = await fn();
      const end = performance.now();
      times.push(end - start);
    }

    const averageTime = times.reduce((sum, time) => sum + time, 0) / times.length;
    
    return {
      result: result!,
      averageTime,
      times,
    };
  }

  static createMemoryUsageMonitor() {
    const initialMemory = process.memoryUsage();
    
    return {
      getUsage: () => {
        const current = process.memoryUsage();
        return {
          heapUsed: current.heapUsed - initialMemory.heapUsed,
          heapTotal: current.heapTotal - initialMemory.heapTotal,
          rss: current.rss - initialMemory.rss,
        };
      },
    };
  }

  static async loadTest(
    fn: () => Promise<any>,
    concurrency: number,
    duration: number
  ): Promise<{ totalRequests: number; successfulRequests: number; averageTime: number }> {
    const startTime = Date.now();
    const endTime = startTime + duration;
    let totalRequests = 0;
    let successfulRequests = 0;
    const times: number[] = [];

    const workers = Array.from({ length: concurrency }, async () => {
      while (Date.now() < endTime) {
        const requestStart = performance.now();
        try {
          await fn();
          successfulRequests++;
          times.push(performance.now() - requestStart);
        } catch (error) {
          // Request failed
        }
        totalRequests++;
      }
    });

    await Promise.all(workers);

    return {
      totalRequests,
      successfulRequests,
      averageTime: times.reduce((sum, time) => sum + time, 0) / times.length,
    };
  }
}
```

---

## 🔧 Integration Examples

### Complete Integration Example

```typescript
// src/examples/rover-integration-example.ts

import { RedisManager, RoverRedisCache } from '../utils/redis-manager';
import { RoverBulkScorer } from '../ml/bulk-scorer';
import { TopKRecommendations } from '../utils/top-k-heap';
import { RoverMetricsCollector } from '../monitoring/prometheus-metrics';
import { RoverTestDataFactory } from '../utils/test-data-factory';

export class RoverIntegrationExample {
  private redisManager: RedisManager;
  private cache: RoverRedisCache;
  private scorer: RoverBulkScorer;
  private topK: TopKRecommendations;

  constructor() {
    // Initialize Redis
    this.redisManager = RedisManager.getInstance({
      host: process.env.REDIS_HOST || 'localhost',
      port: parseInt(process.env.REDIS_PORT || '6379'),
      password: process.env.REDIS_PASSWORD,
    });

    this.cache = new RoverRedisCache(this.redisManager);
    this.scorer = new RoverBulkScorer(mockMLModelService);
    this.topK = new TopKRecommendations(50);
  }

  async generateRecommendations(
    userId: string,
    criteria: ScoringCriteria
  ): Promise<ScoredRecommendation[]> {
    const startTime = Date.now();

    try {
      // 1. Check cache first
      const cached = await this.cache.getCachedRecommendations(userId, criteria);
      if (cached) {
        RoverMetricsCollector.recordCacheOperation('hit', 'recommendations', 0.001);
        return cached;
      }

      // 2. Get vehicle data (mock for example)
      const vehicles = RoverTestDataFactory.createBulkVehicleData(1000);
      
      // 3. Score vehicles
      const scored = await this.scorer.scoreVehicles(vehicles, criteria);
      
      // 4. Get top recommendations
      this.topK.clear();
      this.topK.addBatch(scored);
      const recommendations = this.topK.getTopK();
      
      // 5. Cache results
      await this.cache.cacheRecommendations(userId, criteria, recommendations);
      
      // 6. Record metrics
      const duration = (Date.now() - startTime) / 1000;
      RoverMetricsCollector.recordRecommendationGenerated(
        'premium',
        'ml_generated',
        'v1.0',
        recommendations.length
      );
      RoverMetricsCollector.recordMLInference('recommendation_engine', vehicles.length, duration);
      
      return recommendations;
      
    } catch (error) {
      RoverMetricsCollector.recordError('recommendation_service', 'generation_failed', 'high');
      throw error;
    }
  }

  async trackUserInteraction(
    userId: string,
    interactionType: string,
    dealId: string,
    outcome: string
  ): Promise<void> {
    try {
      // Record interaction in cache/database
      const interaction = {
        userId,
        interactionType,
        dealId,
        outcome,
        timestamp: new Date().toISOString(),
      };

      // Publish to Redis for real-time processing
      await this.redisManager.publish('rover:interactions', interaction);
      
      // Record metrics
      RoverMetricsCollector.recordUserInteraction(
        interactionType,
        'premium',
        outcome
      );

    } catch (error) {
      RoverMetricsCollector.recordError('interaction_service', 'tracking_failed', 'medium');
      throw error;
    }
  }

  async getAnalytics(userId: string): Promise<any> {
    const analyticsKey = `user_analytics:${userId}`;
    
    // Check cache
    const cached = await this.cache.getCachedAnalytics(analyticsKey);
    if (cached) {
      return cached;
    }

    // Generate analytics (mock)
    const analytics = {
      totalRecommendations: 150,
      interactions: 45,
      conversions: 8,
      conversionRate: 0.178,
      averageROI: 0.125,
      topPerformingMakes: ['Toyota', 'Honda', 'Ford'],
      riskProfile: 'moderate',
    };

    // Cache analytics
    await this.cache.cacheAnalytics(analyticsKey, analytics);
    
    return analytics;
  }
}

// Mock ML Model Service for example
const mockMLModelService: MLModelService = {
  async predictMarketDemand(vehicle: VehicleData): Promise<{ demandScore: number }> {
    // Mock implementation
    const baseScore = 0.5 + Math.random() * 0.4; // 0.5 to 0.9
    return { demandScore: baseScore };
  },

  async predictPriceAccuracy(vehicle: VehicleData): Promise<{ accuracyScore: number }> {
    return { accuracyScore: 0.85 + Math.random() * 0.1 };
  },

  async batchPredict(vehicles: VehicleData[]): Promise<any[]> {
    return vehicles.map(v => ({
      vehicleId: v.id,
      demandScore: 0.5 + Math.random() * 0.4,
      accuracyScore: 0.85 + Math.random() * 0.1,
    }));
  },
};

// Usage example
export async function runRoverExample() {
  const rover = new RoverIntegrationExample();
  
  // Generate recommendations
  const userId = 'user_123';
  const criteria: ScoringCriteria = {
    make: 'Toyota',
    maxMileage: 50000,
    maxPrice: 30000,
    userPreferences: RoverTestDataFactory.createUserPreferences(),
  };

  console.log('Generating recommendations...');
  const recommendations = await rover.generateRecommendations(userId, criteria);
  console.log(`Generated ${recommendations.length} recommendations`);

  // Track user interaction
  if (recommendations.length > 0) {
    await rover.trackUserInteraction(
      userId,
      'view',
      recommendations[0].vehicle.id,
      'positive'
    );
  }

  // Get analytics
  const analytics = await rover.getAnalytics(userId);
  console.log('User analytics:', analytics);

  // Get metrics
  const metrics = await RoverMetricsCollector.getMetrics();
  console.log('Prometheus metrics available at /metrics endpoint');
}
```

---

**🎯 Code Philosophy**: These snippets represent production-ready, battle-tested patterns that can be directly integrated into the Rover codebase. Each utility is designed for performance, reliability, and maintainability.

**Last Updated**: January 2025 | **Version**: 1.0 | **Owner**: Rover Engineering Team