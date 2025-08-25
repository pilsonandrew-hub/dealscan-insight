/**
 * SQLite Helper Functions - Database compatibility utilities
 * Provides SQLite-compatible alternatives to PostgreSQL functions
 */

/**
 * SQLite-compatible median calculation
 * Replaces PostgreSQL's percentile_cont function
 */
export function createMedianQuery(
  tableName: string,
  columnName: string,
  whereClause?: string
): string {
  const whereClauseSQL = whereClause ? `WHERE ${whereClause}` : '';
  
  return `
    WITH ordered AS (
      SELECT ${columnName} AS v,
             ROW_NUMBER() OVER (ORDER BY ${columnName}) AS rn,
             COUNT(*) OVER () AS cnt
      FROM ${tableName}
      ${whereClauseSQL}
      AND ${columnName} IS NOT NULL
    )
    SELECT AVG(v) AS median
    FROM ordered
    WHERE rn IN ((cnt+1)/2, (cnt+2)/2)
  `;
}

/**
 * SQLite-compatible percentile calculation
 * Alternative to PostgreSQL's percentile_cont
 */
export function createPercentileQuery(
  tableName: string,
  columnName: string,
  percentile: number, // 0.0 to 1.0
  whereClause?: string
): string {
  const whereClauseSQL = whereClause ? `WHERE ${whereClause}` : '';
  const targetPosition = Math.round(percentile * 100);
  
  return `
    WITH ordered AS (
      SELECT ${columnName} AS v,
             ROW_NUMBER() OVER (ORDER BY ${columnName}) AS rn,
             COUNT(*) OVER () AS cnt
      FROM ${tableName}
      ${whereClauseSQL}
      AND ${columnName} IS NOT NULL
    )
    SELECT v AS percentile_${targetPosition}
    FROM ordered
    WHERE rn = CAST((cnt * ${percentile}) AS INTEGER) + 1
  `;
}

/**
 * SQLite-compatible quartile calculation
 */
export function createQuartileQuery(
  tableName: string,
  columnName: string,
  whereClause?: string
): string {
  const whereClauseSQL = whereClause ? `WHERE ${whereClause}` : '';
  
  return `
    WITH ordered AS (
      SELECT ${columnName} AS v,
             ROW_NUMBER() OVER (ORDER BY ${columnName}) AS rn,
             COUNT(*) OVER () AS cnt
      FROM ${tableName}
      ${whereClauseSQL}
      AND ${columnName} IS NOT NULL
    )
    SELECT 
      MIN(CASE WHEN rn >= (cnt * 0.25) THEN v END) AS q1,
      MIN(CASE WHEN rn >= (cnt * 0.50) THEN v END) AS median,
      MIN(CASE WHEN rn >= (cnt * 0.75) THEN v END) AS q3
    FROM ordered
  `;
}

/**
 * Calculate statistics in memory for JavaScript arrays
 * Fallback when database functions aren't available
 */
export class StatisticsCalculator {
  /**
   * Calculate median from array of numbers
   */
  static median(values: number[]): number {
    if (values.length === 0) return 0;
    
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    
    if (sorted.length % 2 === 0) {
      return (sorted[middle - 1] + sorted[middle]) / 2;
    } else {
      return sorted[middle];
    }
  }
  
  /**
   * Calculate percentile from array of numbers
   */
  static percentile(values: number[], percentile: number): number {
    if (values.length === 0) return 0;
    if (percentile < 0 || percentile > 1) {
      throw new Error('Percentile must be between 0 and 1');
    }
    
    const sorted = [...values].sort((a, b) => a - b);
    const index = percentile * (sorted.length - 1);
    
    if (Number.isInteger(index)) {
      return sorted[index];
    } else {
      const lower = Math.floor(index);
      const upper = Math.ceil(index);
      const weight = index - lower;
      return sorted[lower] * (1 - weight) + sorted[upper] * weight;
    }
  }
  
  /**
   * Calculate quartiles from array of numbers
   */
  static quartiles(values: number[]): { q1: number; median: number; q3: number } {
    return {
      q1: this.percentile(values, 0.25),
      median: this.median(values),
      q3: this.percentile(values, 0.75)
    };
  }
  
  /**
   * Calculate standard deviation
   */
  static standardDeviation(values: number[]): number {
    if (values.length === 0) return 0;
    
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
    const avgSquaredDiff = squaredDiffs.reduce((sum, val) => sum + val, 0) / values.length;
    
    return Math.sqrt(avgSquaredDiff);
  }
  
  /**
   * Calculate comprehensive statistics
   */
  static analyze(values: number[]): {
    count: number;
    mean: number;
    median: number;
    min: number;
    max: number;
    q1: number;
    q3: number;
    standardDeviation: number;
    variance: number;
  } {
    if (values.length === 0) {
      return {
        count: 0,
        mean: 0,
        median: 0,
        min: 0,
        max: 0,
        q1: 0,
        q3: 0,
        standardDeviation: 0,
        variance: 0
      };
    }
    
    const sorted = [...values].sort((a, b) => a - b);
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const stdDev = this.standardDeviation(values);
    const quartiles = this.quartiles(values);
    
    return {
      count: values.length,
      mean,
      median: quartiles.median,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      q1: quartiles.q1,
      q3: quartiles.q3,
      standardDeviation: stdDev,
      variance: stdDev * stdDev
    };
  }
}

/**
 * Database-agnostic query builder for statistical functions
 */
export class DatabaseStats {
  private isPostgreSQL: boolean;
  
  constructor(isPostgreSQL = false) {
    this.isPostgreSQL = isPostgreSQL;
  }
  
  /**
   * Get appropriate median query for the database type
   */
  getMedianQuery(tableName: string, columnName: string, whereClause?: string): string {
    if (this.isPostgreSQL) {
      const whereClauseSQL = whereClause ? `WHERE ${whereClause}` : '';
      return `
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ${columnName}) AS median
        FROM ${tableName}
        ${whereClauseSQL}
      `;
    } else {
      return createMedianQuery(tableName, columnName, whereClause);
    }
  }
  
  /**
   * Get appropriate percentile query for the database type
   */
  getPercentileQuery(
    tableName: string,
    columnName: string,
    percentile: number,
    whereClause?: string
  ): string {
    if (this.isPostgreSQL) {
      const whereClauseSQL = whereClause ? `WHERE ${whereClause}` : '';
      return `
        SELECT percentile_cont(${percentile}) WITHIN GROUP (ORDER BY ${columnName}) AS percentile
        FROM ${tableName}
        ${whereClauseSQL}
      `;
    } else {
      return createPercentileQuery(tableName, columnName, percentile, whereClause);
    }
  }
}