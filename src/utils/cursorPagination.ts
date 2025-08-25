/**
 * Cursor-based pagination for production performance
 * Replaces offset/limit with keyset pagination for better performance at scale
 */

export interface CursorPaginationParams {
  cursor?: string;
  limit?: number;
  orderBy?: string;
  orderDirection?: 'asc' | 'desc';
}

export interface CursorPaginationResult<T> {
  items: T[];
  nextCursor?: string;
  hasMore: boolean;
  total?: number;
}

export interface CursorInfo {
  created_at: string;
  id: string;
}

/**
 * Parse cursor from base64 encoded string
 */
export function parseCursor(cursor?: string): CursorInfo | null {
  if (!cursor) return null;
  
  try {
    const decoded = atob(cursor);
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

/**
 * Create cursor from timestamp and ID
 */
export function createCursor(created_at: string, id: string): string {
  const cursorData = { created_at, id };
  return btoa(JSON.stringify(cursorData));
}

/**
 * Build Supabase query with cursor pagination
 */
export function buildCursorQuery<T>(
  query: any, 
  params: CursorPaginationParams,
  defaultLimit: number = 100
): any {
  const limit = Math.min(params.limit || defaultLimit, 200); // Cap at 200 for performance
  const orderBy = params.orderBy || 'created_at';
  const orderDirection = params.orderDirection || 'desc';
  
  let supabaseQuery = query.order(orderBy, { ascending: orderDirection === 'asc' });
  
  // Add cursor condition if provided
  if (params.cursor) {
    const cursorInfo = parseCursor(params.cursor);
    if (cursorInfo) {
      if (orderDirection === 'desc') {
        supabaseQuery = supabaseQuery
          .or(`created_at.lt.${cursorInfo.created_at},and(created_at.eq.${cursorInfo.created_at},id.lt.${cursorInfo.id})`);
      } else {
        supabaseQuery = supabaseQuery
          .or(`created_at.gt.${cursorInfo.created_at},and(created_at.eq.${cursorInfo.created_at},id.gt.${cursorInfo.id})`);
      }
    }
  }
  
  // Fetch one extra to determine if there are more results
  return supabaseQuery.limit(limit + 1);
}

/**
 * Process cursor pagination results
 */
export function processCursorResults<T extends { created_at: string; id: string }>(
  data: T[],
  limit: number
): CursorPaginationResult<T> {
  const hasMore = data.length > limit;
  const items = hasMore ? data.slice(0, limit) : data;
  
  const nextCursor = hasMore && items.length > 0 
    ? createCursor(items[items.length - 1].created_at, items[items.length - 1].id)
    : undefined;
  
  return {
    items,
    nextCursor,
    hasMore
  };
}