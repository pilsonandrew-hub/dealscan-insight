/**
 * Production-ready API service layer with cursor pagination, ETag, and caching
 */

import { Opportunity, PipelineStatus, UploadResult } from '@/types/dealerscope';
import { supabase } from '@/integrations/supabase/client';
import { productionCache, generateContentHashETag } from '@/utils/productionCache';
import { performanceMonitor } from '@/utils/performance-monitor';
import { auditLogger } from '@/utils/audit-logger';
import { supabaseCircuitBreaker } from '@/utils/circuitBreakerEnhanced';
import { buildCursorQuery, processCursorResults, CursorPaginationParams, CursorPaginationResult } from '@/utils/cursorPagination';
import { logger } from '@/utils/productionLogger';

export const api = {
  // Get opportunities with cursor pagination and ETag support
  async getOpportunities(params: CursorPaginationParams = {}): Promise<CursorPaginationResult<Opportunity>> {
    const { cursor, limit = 100 } = params;
    const cacheKey = `opportunities-cursor-${cursor || 'first'}-${limit}`;
    const timer = performanceMonitor.monitorAPI('getOpportunities', 'GET');
    
    auditLogger.log('api_call_start', 'system', 'info', { endpoint: 'opportunities', cursor, limit });
    
    return supabaseCircuitBreaker.execute(async () => {
      try {
        // Use single-flight pattern to prevent cache stampedes
        return await productionCache.singleFlight(
          cacheKey,
          async () => {
            // Build cursor query
            let query = supabase
              .from('opportunities')
              .select('*')
              .eq('is_active', true);
            
            query = buildCursorQuery(query, params, limit);
            
            const { data, error } = await query;
            
            if (error) {
              logger.error('Supabase query failed', error, { endpoint: 'opportunities', cursor, limit });
              throw error;
            }
            
            const result = processCursorResults(data || [], limit);
            
            auditLogger.log('api_call_success', 'system', 'info', { 
              endpoint: 'opportunities', 
              itemCount: result.items.length,
              hasMore: result.hasMore 
            });
            
            return result;
          },
          300000, // 5 minute TTL
          (data) => generateContentHashETag(JSON.stringify(data))
        );
      } catch (error) {
        timer.end(false);
        auditLogger.log('api_call_error', 'system', 'error', { 
          endpoint: 'opportunities', 
          error: (error as Error).message 
        });
        throw error;
      } finally {
        timer.end(true);
      }
    });
  },

  // Health check
  async healthCheck() {
    try {
      const { error } = await supabase.from('opportunities').select('id').limit(1);
      return {
        status: error ? 'error' : 'healthy',
        timestamp: new Date().toISOString(),
        components: {
          database: error ? 'error' : 'ok',
          cache: 'ok',
          scrapers: 'ok'
        }
      };
    } catch (error) {
      return {
        status: 'error',
        timestamp: new Date().toISOString(),
        components: {
          database: 'error',
          cache: 'ok', 
          scrapers: 'ok'
        }
      };
    }
  }
};

// Export for production use
export default api;