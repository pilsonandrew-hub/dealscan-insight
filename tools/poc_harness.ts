import fs from 'fs';
import path from 'path';
import { ConditionalFetcher } from '../src/services/conditionalFetch';
import HeadlessOptimizer from '../src/services/headlessOptimizer';
import ExtractionStrategyEngine from '../src/services/extractionStrategy';
import { DataValidator } from '../src/utils/validators';
import ComplianceChecker from '../src/services/complianceChecker';

export interface POCConfig {
  urls: string[];
  outputDir: string;
  timeout: number;
  saveArtifacts: boolean;
  validateContracts: boolean;
  checkCompliance: boolean;
}

export interface POCResult {
  url: string;
  status: 'success' | 'error' | 'timeout';
  artifacts: {
    rawHtml?: string;
    extractedJson?: any;
    provenanceData?: any;
    validationReport?: any;
    complianceResult?: any;
    har?: any;
  };
  metadata: {
    timestamp: string;
    renderMode: 'http' | 'headless';
    strategyLog: any[];
    clusterId: string;
    modelVersions: Record<string, string>;
    performance: {
      totalTime: number;
      fetchTime: number;
      extractionTime: number;
      validationTime: number;
    };
  };
  errors: string[];
}

/**
 * Proof of Concept test harness for extraction pipeline validation
 * Runs extraction against test URLs and generates comprehensive artifacts
 */
export class POCHarness {
  private config: POCConfig;
  private validator: DataValidator;

  constructor(config: POCConfig) {
    this.config = config;
    this.validator = new DataValidator();
  }

  /**
   * Run POC test against configured URLs
   */
  async runPOC(): Promise<POCResult[]> {
    console.log(`🧪 Starting POC test with ${this.config.urls.length} URLs`);
    console.log(`📁 Output directory: ${this.config.outputDir}`);

    // Ensure output directory exists
    await this.ensureOutputDirectory();

    const results: POCResult[] = [];
    
    for (let i = 0; i < this.config.urls.length; i++) {
      const url = this.config.urls[i];
      console.log(`\n[${i + 1}/${this.config.urls.length}] Processing: ${url}`);
      
      const result = await this.processURL(url);
      results.push(result);
      
      // Save individual result if artifacts enabled
      if (this.config.saveArtifacts) {
        await this.saveResult(result, i);
      }
      
      // Small delay between requests to be respectful
      if (i < this.config.urls.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
    }

    // Generate summary report
    await this.generateSummaryReport(results);
    
    console.log(`\n✅ POC test completed. Results saved to: ${this.config.outputDir}`);
    return results;
  }

  /**
   * Process a single URL through the complete extraction pipeline
   */
  private async processURL(url: string): Promise<POCResult> {
    const startTime = Date.now();
    const result: POCResult = {
      url,
      status: 'success',
      artifacts: {},
      metadata: {
        timestamp: new Date().toISOString(),
        renderMode: 'http',
        strategyLog: [],
        clusterId: this.generateClusterId(url),
        modelVersions: {
          extractor: '4.9.0',
          validator: '1.0.0',
          compliance: '1.0.0'
        },
        performance: {
          totalTime: 0,
          fetchTime: 0,
          extractionTime: 0,
          validationTime: 0
        }
      },
      errors: []
    };

    try {
      // Step 1: Fetch content (try HTTP first, fallback to headless)
      const fetchStartTime = Date.now();
      const fetchResult = await this.fetchContent(url);
      result.metadata.performance.fetchTime = Date.now() - fetchStartTime;
      result.metadata.renderMode = fetchResult.renderMode;

      if (!fetchResult.html) {
        result.status = 'error';
        result.errors.push('Failed to fetch content');
        return result;
      }

      result.artifacts.rawHtml = fetchResult.html;

      // Step 2: Extract structured data
      const extractionStartTime = Date.now();
      const extractionResult = await this.extractData(url, fetchResult.html, result.metadata.clusterId);
      result.metadata.performance.extractionTime = Date.now() - extractionStartTime;
      result.metadata.strategyLog = extractionResult.strategyLog;

      result.artifacts.extractedJson = extractionResult.data;
      result.artifacts.provenanceData = extractionResult.provenance;

      // Step 3: Validate contracts
      if (this.config.validateContracts) {
        const validationStartTime = Date.now();
        const validationResult = await this.validateData(extractionResult.data);
        result.metadata.performance.validationTime = Date.now() - validationStartTime;
        result.artifacts.validationReport = validationResult;

        if (!validationResult.valid) {
          result.errors.push(...validationResult.errors);
        }
      }

      // Step 4: Check compliance
      if (this.config.checkCompliance) {
        const complianceResult = await ComplianceChecker.evaluateCompliance(url, fetchResult.html);
        result.artifacts.complianceResult = complianceResult;

        if (!complianceResult.robotsAllowed) {
          result.errors.push('Robots.txt disallows this URL');
        }
      }

      result.metadata.performance.totalTime = Date.now() - startTime;

    } catch (error) {
      result.status = 'error';
      result.errors.push(error instanceof Error ? error.message : 'Unknown error');
      result.metadata.performance.totalTime = Date.now() - startTime;
    }

    return result;
  }

  /**
   * Fetch content using HTTP first, fallback to headless
   */
  private async fetchContent(url: string): Promise<{
    html: string;
    renderMode: 'http' | 'headless';
    performance?: any;
  }> {
    // Try HTTP first (faster and cheaper)
    try {
      const httpResult = await ConditionalFetcher.fetchConditional(url);
      
      if (httpResult.body && !httpResult.error) {
        // Check if content looks like it needs JavaScript
        const needsJS = this.detectJavaScriptRequirement(httpResult.body);
        
        if (!needsJS) {
          return {
            html: httpResult.body,
            renderMode: 'http'
          };
        }
      }
    } catch (error) {
      console.log(`HTTP fetch failed for ${url}, trying headless...`);
    }

    // Fallback to headless browser
    try {
      const headlessResult = await HeadlessOptimizer.fetchHeadless(url, {
        timeout: this.config.timeout,
        blockResources: ['image', 'font', 'media']
      });

      return {
        html: headlessResult.html,
        renderMode: 'headless',
        performance: headlessResult.performance
      };
    } catch (error) {
      throw new Error(`Both HTTP and headless fetch failed: ${error}`);
    }
  }

  /**
   * Extract structured data using the strategy engine
   */
  private async extractData(url: string, html: string, clusterId: string): Promise<{
    data: any;
    provenance: any[];
    strategyLog: any[];
  }> {
    const siteName = new URL(url).hostname;
    const strategyLog: any[] = [];
    const provenance: any[] = [];
    
    // Fields to extract (configurable based on site type)
    const fieldsToExtract = ['price', 'year', 'make', 'model', 'mileage', 'title', 'location'];
    const extractedData: any = {};

    for (const field of fieldsToExtract) {
      try {
        const context = { field, html, clusterId, url, siteName };
        const result = await ExtractionStrategyEngine.extractField(context);
        
        extractedData[field] = result.value;
        
        // Log the strategy used
        strategyLog.push({
          field,
          strategy: result.strategy,
          confidence: result.confidence,
          retries: result.retries,
          success: result.confidence > 0.5
        });

        // Generate provenance data
        const provenanceData = ExtractionStrategyEngine.generateProvenance(
          context,
          result,
          'http' // This would be determined by actual render mode
        );
        provenance.push(provenanceData);

      } catch (error) {
        strategyLog.push({
          field,
          strategy: 'error',
          confidence: 0,
          retries: 0,
          success: false,
          error: error instanceof Error ? error.message : 'Unknown error'
        });
      }
    }

    return {
      data: extractedData,
      provenance,
      strategyLog
    };
  }

  /**
   * Validate extracted data against contracts
   */
  private async validateData(data: any): Promise<any> {
    // Mock vehicle data for validation
    const vehicleData = {
      id: 'poc-test',
      make: data.make || 'Unknown',
      model: data.model || 'Unknown',
      year: data.year || 2020,
      price: this.parsePrice(data.price),
      mileage: data.mileage || 0,
      source: 'poc_test',
      provenance: []
    };

    return this.validator.validateVehicle(vehicleData);
  }

  /**
   * Parse price from extracted string
   */
  private parsePrice(priceStr: any): number {
    if (typeof priceStr === 'number') return priceStr;
    if (typeof priceStr === 'string') {
      const cleaned = priceStr.replace(/[^0-9.]/g, '');
      return parseFloat(cleaned) || 0;
    }
    return 0;
  }

  /**
   * Detect if content requires JavaScript execution
   */
  private detectJavaScriptRequirement(html: string): boolean {
    const jsIndicators = [
      /loading\.\.\./i,
      /please\s+enable\s+javascript/i,
      /<noscript>/i,
      /document\.addEventListener\s*\(\s*['"]DOMContentLoaded/i,
      /react-root/i,
      /ng-app/i,
      /__NEXT_DATA__/i
    ];

    return jsIndicators.some(pattern => pattern.test(html));
  }

  /**
   * Generate cluster ID for page grouping
   */
  private generateClusterId(url: string): string {
    const urlObj = new URL(url);
    const pathSegments = urlObj.pathname.split('/').filter(s => s);
    
    // Simple clustering based on URL structure
    if (pathSegments.length === 0) return `${urlObj.hostname}_home`;
    if (pathSegments.includes('listing') || pathSegments.includes('item')) return `${urlObj.hostname}_listing`;
    if (pathSegments.includes('search') || pathSegments.includes('results')) return `${urlObj.hostname}_search`;
    
    return `${urlObj.hostname}_${pathSegments[0] || 'unknown'}`;
  }

  /**
   * Ensure output directory exists
   */
  private async ensureOutputDirectory(): Promise<void> {
    if (!fs.existsSync(this.config.outputDir)) {
      fs.mkdirSync(this.config.outputDir, { recursive: true });
    }
  }

  /**
   * Save individual test result
   */
  private async saveResult(result: POCResult, index: number): Promise<void> {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const fileName = `poc_result_${index + 1}_${timestamp}.json`;
    const filePath = path.join(this.config.outputDir, fileName);

    const sanitizedResult = {
      ...result,
      artifacts: {
        ...result.artifacts,
        // Truncate HTML to prevent huge files
        rawHtml: result.artifacts.rawHtml?.substring(0, 50000) + '...[truncated]'
      }
    };

    fs.writeFileSync(filePath, JSON.stringify(sanitizedResult, null, 2));
    
    // Save full HTML separately if needed
    if (result.artifacts.rawHtml) {
      const htmlFileName = `poc_html_${index + 1}_${timestamp}.html`;
      const htmlFilePath = path.join(this.config.outputDir, htmlFileName);
      fs.writeFileSync(htmlFilePath, result.artifacts.rawHtml);
    }
  }

  /**
   * Generate summary report
   */
  private async generateSummaryReport(results: POCResult[]): Promise<void> {
    const summary = {
      timestamp: new Date().toISOString(),
      totalUrls: results.length,
      successCount: results.filter(r => r.status === 'success').length,
      errorCount: results.filter(r => r.status === 'error').length,
      timeoutCount: results.filter(r => r.status === 'timeout').length,
      averageTime: results.reduce((sum, r) => sum + r.metadata.performance.totalTime, 0) / results.length,
      strategyStats: this.calculateStrategyStats(results),
      validationStats: this.calculateValidationStats(results),
      topErrors: this.getTopErrors(results),
      siteBreakdown: this.calculateSiteBreakdown(results)
    };

    const summaryPath = path.join(this.config.outputDir, 'poc_summary.json');
    fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2));

    // Generate markdown report
    const markdownReport = this.generateMarkdownReport(summary, results);
    const markdownPath = path.join(this.config.outputDir, 'poc_report.md');
    fs.writeFileSync(markdownPath, markdownReport);

    console.log(`\n📊 Summary: ${summary.successCount}/${summary.totalUrls} successful, avg time: ${summary.averageTime.toFixed(0)}ms`);
  }

  /**
   * Calculate strategy usage statistics
   */
  private calculateStrategyStats(results: POCResult[]): any {
    const stats = { selector: 0, ml: 0, llm: 0, error: 0 };
    
    for (const result of results) {
      for (const log of result.metadata.strategyLog) {
        if (log.success) {
          stats[log.strategy as keyof typeof stats] = (stats[log.strategy as keyof typeof stats] || 0) + 1;
        }
      }
    }

    return stats;
  }

  /**
   * Calculate validation statistics
   */
  private calculateValidationStats(results: POCResult[]): any {
    const validResults = results.filter(r => r.artifacts.validationReport);
    const totalValidations = validResults.length;
    const passedValidations = validResults.filter(r => r.artifacts.validationReport.valid).length;

    return {
      total: totalValidations,
      passed: passedValidations,
      passRate: totalValidations > 0 ? (passedValidations / totalValidations) * 100 : 0
    };
  }

  /**
   * Get most common errors
   */
  private getTopErrors(results: POCResult[]): Array<{ error: string; count: number }> {
    const errorCounts: Record<string, number> = {};
    
    for (const result of results) {
      for (const error of result.errors) {
        errorCounts[error] = (errorCounts[error] || 0) + 1;
      }
    }

    return Object.entries(errorCounts)
      .map(([error, count]) => ({ error, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  }

  /**
   * Calculate per-site breakdown
   */
  private calculateSiteBreakdown(results: POCResult[]): any {
    const siteStats: Record<string, any> = {};
    
    for (const result of results) {
      const hostname = new URL(result.url).hostname;
      
      if (!siteStats[hostname]) {
        siteStats[hostname] = {
          total: 0,
          success: 0,
          errors: 0,
          avgTime: 0,
          renderModes: { http: 0, headless: 0 }
        };
      }
      
      const stats = siteStats[hostname];
      stats.total++;
      
      if (result.status === 'success') stats.success++;
      if (result.status === 'error') stats.errors++;
      
      stats.avgTime = (stats.avgTime * (stats.total - 1) + result.metadata.performance.totalTime) / stats.total;
      stats.renderModes[result.metadata.renderMode]++;
    }

    return siteStats;
  }

  /**
   * Generate markdown report
   */
  private generateMarkdownReport(summary: any, results: POCResult[]): string {
    return `# POC Test Report

## Summary
- **Total URLs**: ${summary.totalUrls}
- **Success Rate**: ${summary.successCount}/${summary.totalUrls} (${((summary.successCount/summary.totalUrls)*100).toFixed(1)}%)
- **Average Processing Time**: ${summary.averageTime.toFixed(0)}ms
- **Generated**: ${summary.timestamp}

## Strategy Performance
- **Selector**: ${summary.strategyStats.selector} extractions
- **ML**: ${summary.strategyStats.ml} extractions  
- **LLM**: ${summary.strategyStats.llm} extractions
- **Errors**: ${summary.strategyStats.error} failures

## Validation Results
- **Pass Rate**: ${summary.validationStats.passRate.toFixed(1)}%
- **Passed**: ${summary.validationStats.passed}/${summary.validationStats.total}

## Top Errors
${summary.topErrors.map((e: any) => `- ${e.error} (${e.count} times)`).join('\n')}

## Site Breakdown
${Object.entries(summary.siteBreakdown).map(([site, stats]: [string, any]) => 
  `- **${site}**: ${stats.success}/${stats.total} success (${(stats.success/stats.total*100).toFixed(1)}%), avg ${stats.avgTime.toFixed(0)}ms`
).join('\n')}
`;
  }
}

export default POCHarness;