/**
 * ProxyManager - Handles proxy rotation and health monitoring
 * Manages proxy pools, rotation strategies, and failure handling
 */

import { logger } from '@/lib/logger';
import { ProxyConfig } from './types';

export class ProxyManager {
  private proxies: ProxyConfig[] = [];
  private currentProxyIndex = 0;
  private blockedProxies = new Set<string>();
  private proxyStats = new Map<string, { 
    requests: number; 
    failures: number; 
    lastUsed: Date; 
    successRate: number; 
  }>();

  constructor() {
    this.initializeProxies();
  }

  private initializeProxies(): void {
    // In a real implementation, these would come from configuration or database
    this.proxies = [
      {
        ip: '192.168.1.100',
        port: 8080,
        type: 'http',
        country: 'US',
        status: 'active',
        successRate: 95
      },
      {
        ip: '192.168.1.101', 
        port: 8080,
        type: 'http',
        country: 'CA',
        status: 'active',
        successRate: 88
      }
    ];

    // Initialize stats
    this.proxies.forEach(proxy => {
      const key = `${proxy.ip}:${proxy.port}`;
      this.proxyStats.set(key, {
        requests: 0,
        failures: 0,
        lastUsed: new Date(0),
        successRate: proxy.successRate
      });
    });
  }

  async getNextProxy(siteId?: string): Promise<ProxyConfig | null> {
    const availableProxies = this.proxies.filter(proxy => {
      const key = `${proxy.ip}:${proxy.port}`;
      return !this.blockedProxies.has(key) && proxy.status === 'active';
    });

    if (availableProxies.length === 0) {
      logger.warn('No available proxies, proceeding without proxy');
      return null;
    }

    // Implement smart rotation based on success rates
    const sortedProxies = availableProxies.sort((a, b) => {
      const aKey = `${a.ip}:${a.port}`;
      const bKey = `${b.ip}:${b.port}`;
      const aStats = this.proxyStats.get(aKey)!;
      const bStats = this.proxyStats.get(bKey)!;
      
      // Prefer proxies with higher success rates and less recent usage
      const aScore = aStats.successRate - (Date.now() - aStats.lastUsed.getTime()) / 10000;
      const bScore = bStats.successRate - (Date.now() - bStats.lastUsed.getTime()) / 10000;
      
      return bScore - aScore;
    });

    const selectedProxy = sortedProxies[0];
    const key = `${selectedProxy.ip}:${selectedProxy.port}`;
    
    // Update usage stats
    const stats = this.proxyStats.get(key)!;
    stats.requests++;
    stats.lastUsed = new Date();
    
    logger.debug(`Selected proxy ${key} for site ${siteId}`);
    return selectedProxy;
  }

  async markProxyBlocked(proxyKey: string): Promise<void> {
    this.blockedProxies.add(proxyKey);
    
    const stats = this.proxyStats.get(proxyKey);
    if (stats) {
      stats.failures++;
      stats.successRate = Math.max(0, stats.successRate - 10);
    }

    logger.warn(`Proxy ${proxyKey} marked as blocked`);
    
    // Schedule unblock after cooldown period
    setTimeout(() => {
      this.unblockProxy(proxyKey);
    }, 300000); // 5 minutes
  }

  private unblockProxy(proxyKey: string): void {
    this.blockedProxies.delete(proxyKey);
    logger.info(`Proxy ${proxyKey} unblocked after cooldown`);
  }

  async recordProxySuccess(proxyKey: string): Promise<void> {
    const stats = this.proxyStats.get(proxyKey);
    if (stats) {
      stats.successRate = Math.min(100, stats.successRate + 1);
    }
  }

  async recordProxyFailure(proxyKey: string): Promise<void> {
    const stats = this.proxyStats.get(proxyKey);
    if (stats) {
      stats.failures++;
      stats.successRate = Math.max(0, stats.successRate - 2);
    }
  }

  getProxyStats(): Map<string, any> {
    return new Map(this.proxyStats);
  }

  async refreshProxies(): Promise<void> {
    // Reset blocked proxies after a longer period
    this.blockedProxies.clear();
    logger.info('Proxy list refreshed');
  }

  async testProxyHealth(proxy: ProxyConfig): Promise<boolean> {
    try {
      // In a real implementation, this would test the proxy connection
      // For now, we'll simulate based on success rate
      return proxy.successRate > 50;
    } catch (error) {
      logger.error(`Proxy health test failed for ${proxy.ip}:${proxy.port}`, error);
      return false;
    }
  }

  async rotateProxies(): Promise<void> {
    // Rotate to next proxy in round-robin fashion
    this.currentProxyIndex = (this.currentProxyIndex + 1) % this.proxies.length;
  }
}