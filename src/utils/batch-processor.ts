/**
 * Batch processing utilities
 * Inspired by the pipeline processing in the bootstrap script
 */

import { settings } from '@/config/settings';
import { performanceMonitor } from './performance-monitor';
import { auditLogger } from './audit-logger';

export interface BatchJobConfig {
  batchSize?: number;
  concurrency?: number;
  retries?: number;
  timeout?: number;
  onProgress?: (progress: BatchProgress) => void;
  onError?: (error: Error, item: any) => void;
}

export interface BatchProgress {
  processed: number;
  total: number;
  failed: number;
  percentage: number;
  currentBatch: number;
  totalBatches: number;
  startTime: number;
  estimatedCompletion?: number;
}

export interface BatchResult<T> {
  successful: T[];
  failed: Array<{ item: any; error: Error }>;
  progress: BatchProgress;
  duration: number;
}

export class BatchProcessor {
  private config: Required<BatchJobConfig>;

  constructor(config: BatchJobConfig = {}) {
    this.config = {
      batchSize: config.batchSize || settings.processing.batchSize,
      concurrency: config.concurrency || settings.processing.maxWorkers,
      retries: config.retries || settings.processing.retries,
      timeout: config.timeout || settings.processing.timeout,
      onProgress: config.onProgress || (() => {}),
      onError: config.onError || (() => {})
    };
  }

  // Process items in batches with concurrency control
  async processBatch<TInput, TOutput>(
    items: TInput[],
    processor: (item: TInput) => Promise<TOutput>,
    jobName: string = 'batch_job'
  ): Promise<BatchResult<TOutput>> {
    const timer = performanceMonitor.startTimer(`batch_process_${jobName}`);
    const startTime = Date.now();
    
    auditLogger.log(
      'batch_process_start',
      'data',
      'info',
      { jobName, itemCount: items.length, batchSize: this.config.batchSize }
    );

    const totalBatches = Math.ceil(items.length / this.config.batchSize);
    const successful: TOutput[] = [];
    const failed: Array<{ item: TInput; error: Error }> = [];

    let processed = 0;

    // Process in batches
    for (let batchIndex = 0; batchIndex < totalBatches; batchIndex++) {
      const batchStart = batchIndex * this.config.batchSize;
      const batchEnd = Math.min(batchStart + this.config.batchSize, items.length);
      const batch = items.slice(batchStart, batchEnd);

      try {
        // Process batch with concurrency control
        const batchResults = await this.processBatchConcurrent(batch, processor);
        
        // Separate successful and failed results
        batchResults.forEach(result => {
          if (result.success) {
            successful.push(result.data);
          } else {
            failed.push({ item: result.item, error: result.error });
            this.config.onError(result.error, result.item);
          }
        });

        processed += batch.length;

        // Report progress
        const progress: BatchProgress = {
          processed,
          total: items.length,
          failed: failed.length,
          percentage: (processed / items.length) * 100,
          currentBatch: batchIndex + 1,
          totalBatches,
          startTime,
          estimatedCompletion: this.estimateCompletion(startTime, processed, items.length)
        };

        this.config.onProgress(progress);

      } catch (error) {
        auditLogger.logError(error as Error, `batch_process_${jobName}_batch_${batchIndex}`);
        
        // Mark entire batch as failed
        batch.forEach(item => {
          failed.push({ item, error: error as Error });
          this.config.onError(error as Error, item);
        });
        
        processed += batch.length;
      }
    }

    const duration = timer.end(failed.length === 0);
    
    const finalProgress: BatchProgress = {
      processed,
      total: items.length,
      failed: failed.length,
      percentage: 100,
      currentBatch: totalBatches,
      totalBatches,
      startTime
    };

    auditLogger.log(
      'batch_process_complete',
      'data',
      failed.length === 0 ? 'info' : 'warning',
      {
        jobName,
        successful: successful.length,
        failed: failed.length,
        duration,
        totalItems: items.length
      }
    );

    return {
      successful,
      failed,
      progress: finalProgress,
      duration
    };
  }

  // Process batch items with concurrency control
  private async processBatchConcurrent<TInput, TOutput>(
    batch: TInput[],
    processor: (item: TInput) => Promise<TOutput>
  ): Promise<Array<{ success: boolean; data?: TOutput; item: TInput; error?: Error }>> {
    const semaphore = new Semaphore(this.config.concurrency);
    
    const promises = batch.map(async (item) => {
      await semaphore.acquire();
      
      try {
        const result = await this.processWithRetry(item, processor);
        return { success: true, data: result, item };
      } catch (error) {
        return { success: false, item, error: error as Error };
      } finally {
        semaphore.release();
      }
    });

    return Promise.all(promises);
  }

  // Process single item with retry logic
  private async processWithRetry<TInput, TOutput>(
    item: TInput,
    processor: (item: TInput) => Promise<TOutput>
  ): Promise<TOutput> {
    let lastError: Error;
    
    for (let attempt = 0; attempt <= this.config.retries; attempt++) {
      try {
        // Add timeout to processor
        const timeoutPromise = new Promise<never>((_, reject) => {
          setTimeout(() => reject(new Error('Processing timeout')), this.config.timeout);
        });
        
        const processingPromise = processor(item);
        const result = await Promise.race([processingPromise, timeoutPromise]);
        
        return result;
      } catch (error) {
        lastError = error as Error;
        
        if (attempt < this.config.retries) {
          // Exponential backoff
          const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
          await new Promise(resolve => setTimeout(resolve, delay));
        }
      }
    }
    
    throw lastError!;
  }

  private estimateCompletion(startTime: number, processed: number, total: number): number {
    if (processed === 0) return 0;
    
    const elapsed = Date.now() - startTime;
    const rate = processed / elapsed;
    const remaining = total - processed;
    
    return Date.now() + (remaining / rate);
  }
}

// Semaphore for concurrency control
class Semaphore {
  private permits: number;
  private queue: Array<() => void> = [];

  constructor(permits: number) {
    this.permits = permits;
  }

  async acquire(): Promise<void> {
    if (this.permits > 0) {
      this.permits--;
      return;
    }

    return new Promise<void>(resolve => {
      this.queue.push(resolve);
    });
  }

  release(): void {
    if (this.queue.length > 0) {
      const next = this.queue.shift()!;
      next();
    } else {
      this.permits++;
    }
  }
}

// Utility functions for common batch operations
export const batchUtils = {
  // Chunk array into batches
  chunk<T>(array: T[], size: number): T[][] {
    const chunks: T[][] = [];
    for (let i = 0; i < array.length; i += size) {
      chunks.push(array.slice(i, i + size));
    }
    return chunks;
  },

  // Process CSV data in batches
  async processCSVBatch<T>(
    data: any[],
    transformer: (row: any) => Promise<T>,
    options: BatchJobConfig = {}
  ): Promise<BatchResult<T>> {
    const processor = new BatchProcessor(options);
    return processor.processBatch(data, transformer, 'csv_processing');
  },

  // Validate data in batches
  async validateBatch<T>(
    data: T[],
    validator: (item: T) => Promise<boolean>,
    options: BatchJobConfig = {}
  ): Promise<{ valid: T[]; invalid: T[] }> {
    const processor = new BatchProcessor(options);
    const result = await processor.processBatch(
      data,
      async (item) => {
        const isValid = await validator(item);
        return { item, isValid };
      },
      'data_validation'
    );

    const valid = result.successful
      .filter(r => r.isValid)
      .map(r => r.item);
    
    const invalid = result.successful
      .filter(r => !r.isValid)
      .map(r => r.item)
      .concat(result.failed.map(f => f.item));

    return { valid, invalid };
  }
};

// Export default processor instance
export const defaultProcessor = new BatchProcessor();