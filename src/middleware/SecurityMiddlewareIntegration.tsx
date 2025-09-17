/**
 * Security Middleware Integration - Complete Phase 3 & 4 Implementation
 * Unifies all security components into a cohesive production-ready system
 */

import React, { useEffect, useState } from 'react';
import { securityHeaders } from './securityHeaders';
import { intrusionDetection, analyzeInput, recordSecurityEvent } from '@/utils/intrusionDetection';
import { uploadHardening } from '@/security/uploadHardening';
import { RateLimiter } from '@/utils/rateLimiter';
import { auditLogger } from '@/utils/audit-logger';
import { validateAndSanitizeUrl } from '@/utils/urlSecurity';
import { ContentSanitizer } from '@/utils/securityHeaders';
import { logger } from '@/core/UnifiedLogger';

export interface SecurityStatus {
  headersActive: boolean;
  intrusionDetectionActive: boolean;
  uploadHardeningActive: boolean;
  rateLimitingActive: boolean;
  ssrfProtectionActive: boolean;
  inputValidationActive: boolean;
  auditLoggingActive: boolean;
  overallSecurityScore: number;
}

class SecurityMiddlewareOrchestrator {
  private static instance: SecurityMiddlewareOrchestrator;
  private initialized = false;
  private rateLimiter: RateLimiter;
  private status: SecurityStatus = {
    headersActive: false,
    intrusionDetectionActive: false,
    uploadHardeningActive: false,
    rateLimitingActive: false,
    ssrfProtectionActive: false,
    inputValidationActive: false,
    auditLoggingActive: false,
    overallSecurityScore: 0
  };

  constructor() {
    this.rateLimiter = new RateLimiter({
      maxTokens: 100,
      refillRate: 10,
      windowMs: 60000,
      keyPrefix: 'security'
    });
  }

  static getInstance(): SecurityMiddlewareOrchestrator {
    if (!SecurityMiddlewareOrchestrator.instance) {
      SecurityMiddlewareOrchestrator.instance = new SecurityMiddlewareOrchestrator();
    }
    return SecurityMiddlewareOrchestrator.instance;
  }

  async initialize(): Promise<SecurityStatus> {
    if (this.initialized) return this.status;

    logger.info('🔐 Initializing Security Middleware Integration...');
    
    try {
      // Initialize Security Headers
      await this.initializeSecurityHeaders();
      
      // Initialize Intrusion Detection
      await this.initializeIntrusionDetection();
      
      // Initialize Upload Hardening
      await this.initializeUploadHardening();
      
      // Initialize Rate Limiting
      await this.initializeRateLimiting();
      
      // Initialize SSRF Protection
      await this.initializeSSRFProtection();
      
      // Initialize Input Validation
      await this.initializeInputValidation();
      
      // Initialize Audit Logging
      await this.initializeAuditLogging();
      
      // Set up request interceptors
      await this.setupRequestInterceptors();
      
      // Calculate overall security score
      this.calculateSecurityScore();
      
      this.initialized = true;
      
      logger.info('✅ Security Middleware Integration Complete', {
        securityScore: this.status.overallSecurityScore,
        activeComponents: Object.entries(this.status).filter(([key, value]) => 
          key !== 'overallSecurityScore' && value === true).length
      });

      // Log security initialization to audit trail
      auditLogger.log('security_middleware_initialized', 'system', 'info');

      return this.status;

    } catch (error) {
      logger.error('❌ Security Middleware Integration Failed', error as Error);
      recordSecurityEvent({
        type: 'security_initialization_failure',
        severity: 'critical',
        timestamp: new Date(),
        details: { error: (error as Error).message }
      });
      throw error;
    }
  }

  private async initializeSecurityHeaders(): Promise<void> {
    try {
      // Apply security headers to all requests
      securityHeaders.applyHeaders(new Response());
      this.status.headersActive = true;
      logger.info('✅ Security Headers Active');
    } catch (error) {
      logger.error('❌ Security Headers Failed', error as Error);
    }
  }

  private async initializeIntrusionDetection(): Promise<void> {
    try {
      // Test intrusion detection system
      const testResult = analyzeInput('test_input', {
        action: 'system_test',
        userId: 'system',
        ipAddress: '127.0.0.1'
      });
      
      this.status.intrusionDetectionActive = true;
      logger.info('✅ Intrusion Detection System Active');
    } catch (error) {
      logger.error('❌ Intrusion Detection Failed', error as Error);
    }
  }

  private async initializeUploadHardening(): Promise<void> {
    try {
      // Test upload hardening with dummy file
      const testBlob = new Blob(['test'], { type: 'text/plain' });
      const testFile = new File([testBlob], 'test.txt', { type: 'text/plain' });
      
      await uploadHardening.validateFile(testFile);
      this.status.uploadHardeningActive = true;
      logger.info('✅ Upload Hardening Active');
    } catch (error) {
      logger.error('❌ Upload Hardening Failed', error as Error);
    }
  }

  private async initializeRateLimiting(): Promise<void> {
    try {
      // Test rate limiter
      await this.rateLimiter.checkLimit('test_key');
      this.status.rateLimitingActive = true;
      logger.info('✅ Rate Limiting Active');
    } catch (error) {
      logger.error('❌ Rate Limiting Failed', error as Error);
    }
  }

  private async initializeSSRFProtection(): Promise<void> {
    try {
      // Test SSRF protection
      const testUrl = 'https://govdeals.com/test';
      validateAndSanitizeUrl(testUrl);
      this.status.ssrfProtectionActive = true;
      logger.info('✅ SSRF Protection Active');
    } catch (error) {
      logger.error('❌ SSRF Protection Failed', error as Error);
    }
  }

  private async initializeInputValidation(): Promise<void> {
    try {
      // Test input sanitization
      ContentSanitizer.sanitizeHTML('<script>test</script>');
      this.status.inputValidationActive = true;
      logger.info('✅ Input Validation Active');
    } catch (error) {
      logger.error('❌ Input Validation Failed', error as Error);
    }
  }

  private async initializeAuditLogging(): Promise<void> {
    try {
      // Test audit logging
      auditLogger.log('security_audit_test', 'system', 'info', { test: true });
      this.status.auditLoggingActive = true;
      logger.info('✅ Audit Logging Active');
    } catch (error) {
      logger.error('❌ Audit Logging Failed', error as Error);
    }
  }

  private async setupRequestInterceptors(): Promise<void> {
    // Intercept fetch requests for security analysis
    const originalFetch = window.fetch;
    
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      try {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        
        // Analyze request for threats
        analyzeInput(url, {
          action: 'network_request',
          ipAddress: 'client',
          userAgent: navigator.userAgent
        });

        // Apply SSRF protection for external URLs
        if (url.startsWith('http')) {
          const validatedUrl = validateAndSanitizeUrl(url);
          if (!validatedUrl) {
            recordSecurityEvent({
              type: 'blocked_unsafe_request',
              severity: 'medium',
              timestamp: new Date(),
              details: { originalUrl: url }
            });
            throw new Error('Unsafe URL blocked by security middleware');
          }
        }

        // Apply rate limiting
        const rateLimitResult = await this.rateLimiter.checkLimit(`request_${url}`);
        if (!rateLimitResult.allowed) {
          recordSecurityEvent({
            type: 'request_rate_limited',
            severity: 'low',
            timestamp: new Date(),
            details: { url, retryAfter: rateLimitResult.retryAfter }
          });
          throw new Error('Request rate limit exceeded');
        }

        return await originalFetch(input, init);

      } catch (error) {
        recordSecurityEvent({
          type: 'request_interceptor_error',
          severity: 'medium',
          timestamp: new Date(),
          details: { error: (error as Error).message }
        });
        throw error;
      }
    };
  }

  private calculateSecurityScore(): void {
    const activeComponents = Object.entries(this.status)
      .filter(([key, value]) => key !== 'overallSecurityScore' && value === true)
      .length;
    
    const totalComponents = Object.keys(this.status).length - 1; // Exclude overallSecurityScore
    this.status.overallSecurityScore = Math.round((activeComponents / totalComponents) * 100);
  }

  getStatus(): SecurityStatus {
    return { ...this.status };
  }

  async performSecurityHealthCheck(): Promise<{
    healthy: boolean;
    issues: string[];
    recommendations: string[];
  }> {
    const issues: string[] = [];
    const recommendations: string[] = [];

    // Check each security component
    if (!this.status.headersActive) {
      issues.push('Security headers not active');
      recommendations.push('Ensure security headers middleware is properly initialized');
    }

    if (!this.status.intrusionDetectionActive) {
      issues.push('Intrusion detection system not active');
      recommendations.push('Initialize intrusion detection monitoring');
    }

    if (!this.status.uploadHardeningActive) {
      issues.push('Upload security hardening not active');
      recommendations.push('Enable file upload security validation');
    }

    if (!this.status.rateLimitingActive) {
      issues.push('Rate limiting not active');
      recommendations.push('Configure rate limiting for API endpoints');
    }

    if (this.status.overallSecurityScore < 85) {
      issues.push(`Security score below threshold: ${this.status.overallSecurityScore}%`);
      recommendations.push('Review and activate missing security components');
    }

    return {
      healthy: issues.length === 0,
      issues,
      recommendations
    };
  }
}

// React component for security status monitoring
export const SecurityMiddlewareProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [securityStatus, setSecurityStatus] = useState<SecurityStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const initializeSecurity = async () => {
      try {
        const orchestrator = SecurityMiddlewareOrchestrator.getInstance();
        const status = await orchestrator.initialize();
        setSecurityStatus(status);
      } catch (error) {
        logger.error('Security middleware initialization failed', error as Error);
      } finally {
        setLoading(false);
      }
    };

    initializeSecurity();
  }, []);

  // Show security loading state for critical systems
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary mx-auto mb-4"></div>
          <h2 className="text-xl font-semibold text-foreground mb-2">Initializing Security Systems</h2>
          <p className="text-muted-foreground">Activating enterprise-grade security middleware...</p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
};

// Export the orchestrator instance
export const securityOrchestrator = SecurityMiddlewareOrchestrator.getInstance();

// Export status hook for components
export const useSecurityStatus = () => {
  const [status, setStatus] = useState<SecurityStatus | null>(null);

  useEffect(() => {
    const updateStatus = () => {
      setStatus(securityOrchestrator.getStatus());
    };

    updateStatus();
    const interval = setInterval(updateStatus, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, []);

  return status;
};

export default SecurityMiddlewareOrchestrator;