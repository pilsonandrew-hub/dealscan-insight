/**
 * Shared types for the scraper system
 */

export interface ScraperSite {
  id: string;
  name: string;
  baseUrl: string;
  enabled: boolean;
  lastScrape?: string;
  vehiclesFound?: number;
  status: 'active' | 'blocked' | 'maintenance' | 'error';
  category: 'federal' | 'state' | 'local' | 'insurance' | 'dealer';
}

export interface ProxyConfig {
  ip: string;
  port: number;
  username?: string;
  password?: string;
  type: 'http' | 'socks5';
  country: string;
  status: 'active' | 'blocked' | 'rotating';
  successRate: number;
  lastUsed?: string;
}

export interface ScrapingResult {
  site: string;
  success: boolean;
  vehiclesFound: number;
  errors: string[];
  blocked: boolean;
  proxyUsed?: string;
  timeElapsed: number;
  nextRetry?: string;
}

export interface ScrapingJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  sitesTargeted: string[];
  startedAt?: Date;
  completedAt?: Date;
  results?: Map<string, ScrapingResult>;
  config?: any;
  errorMessage?: string;
}

export interface ExtractionStrategy {
  id: string;
  siteName: string;
  fieldName: string;
  strategy: 'selector' | 'regex' | 'attribute' | 'ml' | 'llm';
  config: any;
  fallbackOrder: number;
  confidenceThreshold: number;
  successRate: number;
}