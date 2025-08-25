/**
 * Compliance checking for web scraping operations
 * Handles robots.txt, PII detection/redaction, and retention policies
 */

export interface ComplianceResult {
  robotsAllowed: boolean;
  piiRedacted: boolean;
  retainedUntil?: string;
  piiFound?: string[];
  robotsRules?: string[];
  complianceScore: number; // 0-1, where 1 is fully compliant
}

export interface RetentionPolicy {
  htmlRetentionDays: number;
  piiRetentionDays: number;
  logRetentionDays: number;
  purgeAfterDays: number;
}

export class ComplianceChecker {
  private static readonly DEFAULT_RETENTION: RetentionPolicy = {
    htmlRetentionDays: 30,
    piiRetentionDays: 7,
    logRetentionDays: 90,
    purgeAfterDays: 365
  };

  private static readonly PII_PATTERNS = [
    // Email addresses
    /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    // Phone numbers (US format)
    /(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})/g,
    // Social Security Numbers
    /\b\d{3}-?\d{2}-?\d{4}\b/g,
    // Credit Card Numbers (basic pattern)
    /\b(?:\d{4}[-\s]?){3}\d{4}\b/g,
    // IP Addresses
    /\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b/g
  ];

  private static robotsCache = new Map<string, { rules: string[]; timestamp: number }>();
  private static readonly ROBOTS_CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours

  /**
   * Evaluate compliance for a URL and its content
   */
  static async evaluateCompliance(
    url: string,
    html: string,
    userAgent: string = 'DealerScope-Bot/1.0',
    retentionPolicy?: Partial<RetentionPolicy>
  ): Promise<ComplianceResult> {
    const policy = { ...this.DEFAULT_RETENTION, ...retentionPolicy };
    
    // Check robots.txt compliance
    const robotsResult = await this.checkRobotsCompliance(url, userAgent);
    
    // Detect and redact PII
    const piiResult = this.detectAndRedactPII(html);
    
    // Calculate retention dates
    const retainedUntil = new Date(
      Date.now() + policy.htmlRetentionDays * 24 * 60 * 60 * 1000
    ).toISOString();
    
    // Calculate overall compliance score
    const complianceScore = this.calculateComplianceScore(robotsResult, piiResult);
    
    return {
      robotsAllowed: robotsResult.allowed,
      robotsRules: robotsResult.rules,
      piiRedacted: piiResult.found.length > 0,
      piiFound: piiResult.found,
      retainedUntil,
      complianceScore
    };
  }

  /**
   * Check robots.txt compliance for a URL
   */
  private static async checkRobotsCompliance(
    url: string,
    userAgent: string
  ): Promise<{ allowed: boolean; rules: string[] }> {
    try {
      const urlObj = new URL(url);
      const robotsUrl = `${urlObj.protocol}//${urlObj.host}/robots.txt`;
      const cacheKey = `${urlObj.host}:${userAgent}`;
      
      // Check cache first
      const cached = this.robotsCache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < this.ROBOTS_CACHE_TTL) {
        return this.parseRobotsRules(cached.rules, url, userAgent);
      }
      
      // Fetch robots.txt
      const response = await fetch(robotsUrl, {
        headers: { 'User-Agent': userAgent }
      });
      
      if (!response.ok) {
        // No robots.txt or error - assume allowed
        return { allowed: true, rules: ['No robots.txt found - allowing by default'] };
      }
      
      const robotsText = await response.text();
      const rules = robotsText.split('\n').filter(line => line.trim());
      
      // Cache the rules
      this.robotsCache.set(cacheKey, {
        rules,
        timestamp: Date.now()
      });
      
      return this.parseRobotsRules(rules, url, userAgent);
      
    } catch (error) {
      console.error('Error checking robots.txt:', error);
      return { allowed: true, rules: ['Error checking robots.txt - allowing by default'] };
    }
  }

  /**
   * Parse robots.txt rules and check if URL is allowed
   */
  private static parseRobotsRules(
    rules: string[],
    url: string,
    userAgent: string
  ): { allowed: boolean; rules: string[] } {
    const urlPath = new URL(url).pathname;
    let currentUserAgent = '';
    let isRelevantSection = false;
    const relevantRules: string[] = [];
    let allowed = true;
    
    for (const line of rules) {
      const trimmed = line.trim().toLowerCase();
      
      if (trimmed.startsWith('user-agent:')) {
        currentUserAgent = trimmed.substring(11).trim();
        isRelevantSection = currentUserAgent === '*' || 
                          userAgent.toLowerCase().includes(currentUserAgent);
      }
      
      if (isRelevantSection && trimmed.startsWith('disallow:')) {
        const disallowPath = trimmed.substring(9).trim();
        relevantRules.push(`Disallow: ${disallowPath}`);
        
        if (disallowPath === '/') {
          allowed = false;
        } else if (disallowPath && urlPath.startsWith(disallowPath)) {
          allowed = false;
        }
      }
      
      if (isRelevantSection && trimmed.startsWith('allow:')) {
        const allowPath = trimmed.substring(6).trim();
        relevantRules.push(`Allow: ${allowPath}`);
        
        if (allowPath && urlPath.startsWith(allowPath)) {
          allowed = true;
        }
      }
    }
    
    return { allowed, rules: relevantRules };
  }

  /**
   * Detect and redact PII from HTML content
   */
  private static detectAndRedactPII(html: string): {
    redactedHtml: string;
    found: string[];
  } {
    let redactedHtml = html;
    const found: string[] = [];
    
    for (const pattern of this.PII_PATTERNS) {
      const matches = html.match(pattern);
      if (matches) {
        found.push(...matches);
        redactedHtml = redactedHtml.replace(pattern, '[PII_REDACTED]');
      }
    }
    
    return { redactedHtml, found };
  }

  /**
   * Calculate overall compliance score
   */
  private static calculateComplianceScore(
    robotsResult: { allowed: boolean },
    piiResult: { found: string[] }
  ): number {
    let score = 1.0;
    
    // Penalize robots.txt violations
    if (!robotsResult.allowed) {
      score -= 0.5;
    }
    
    // Penalize PII presence (slight penalty as we can redact)
    if (piiResult.found.length > 0) {
      score -= Math.min(0.2, piiResult.found.length * 0.05);
    }
    
    return Math.max(0, score);
  }

  /**
   * Check if content should be retained based on policy
   */
  static shouldRetainContent(
    createdAt: string,
    policy: RetentionPolicy,
    hasPII: boolean = false
  ): {
    shouldRetain: boolean;
    reason: string;
    purgeDate?: string;
  } {
    const now = Date.now();
    const created = new Date(createdAt).getTime();
    const ageInDays = (now - created) / (24 * 60 * 60 * 1000);
    
    // Check PII retention limit
    if (hasPII && ageInDays > policy.piiRetentionDays) {
      return {
        shouldRetain: false,
        reason: `PII retention limit exceeded (${policy.piiRetentionDays} days)`
      };
    }
    
    // Check HTML retention limit
    if (ageInDays > policy.htmlRetentionDays) {
      return {
        shouldRetain: false,
        reason: `HTML retention limit exceeded (${policy.htmlRetentionDays} days)`
      };
    }
    
    // Calculate purge date
    const purgeDate = new Date(
      created + policy.purgeAfterDays * 24 * 60 * 60 * 1000
    ).toISOString();
    
    return {
      shouldRetain: true,
      reason: 'Within retention policy',
      purgeDate
    };
  }

  /**
   * Generate compliance report for audit purposes
   */
  static generateComplianceReport(
    url: string,
    complianceResult: ComplianceResult,
    retentionPolicy: RetentionPolicy
  ): {
    url: string;
    timestamp: string;
    compliant: boolean;
    issues: string[];
    recommendations: string[];
  } {
    const issues: string[] = [];
    const recommendations: string[] = [];
    
    if (!complianceResult.robotsAllowed) {
      issues.push('Robots.txt disallows access to this URL');
      recommendations.push('Respect robots.txt or contact site owner for permission');
    }
    
    if (complianceResult.piiFound && complianceResult.piiFound.length > 0) {
      issues.push(`PII detected: ${complianceResult.piiFound.length} instances`);
      recommendations.push('Implement PII redaction before storage');
    }
    
    if (complianceResult.complianceScore < 0.8) {
      recommendations.push('Review and improve compliance practices');
    }
    
    return {
      url,
      timestamp: new Date().toISOString(),
      compliant: complianceResult.complianceScore >= 0.8,
      issues,
      recommendations
    };
  }

  /**
   * Clear robots.txt cache (for testing or manual refresh)
   */
  static clearRobotsCache(): void {
    this.robotsCache.clear();
  }
}

export default ComplianceChecker;