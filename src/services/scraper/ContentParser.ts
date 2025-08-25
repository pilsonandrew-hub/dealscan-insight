/**
 * ContentParser - Handles parsing and extraction of vehicle data from scraped content
 * Implements site-specific parsing strategies and data normalization
 */

import { logger } from '@/lib/logger';
import { supabase } from '@/integrations/supabase/client';

export interface ParsedListing {
  source_site: string;
  listing_url: string;
  auction_end?: string;
  year?: number;
  make?: string;
  model?: string;
  trim?: string;
  mileage?: number;
  current_bid?: number;
  location?: string;
  state?: string;
  vin?: string;
  photo_url?: string;
  description?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export class ContentParser {
  private extractionStrategies = new Map<string, any>();

  constructor() {
    this.initializeExtractionStrategies();
  }

  private async initializeExtractionStrategies(): Promise<void> {
    try {
      const { data: strategies, error } = await supabase
        .from('extraction_strategies')
        .select('*')
        .order('fallback_order');

      if (error) throw error;

      // Group strategies by site and field
      strategies?.forEach(strategy => {
        const key = `${strategy.site_name}_${strategy.field_name}`;
        if (!this.extractionStrategies.has(key)) {
          this.extractionStrategies.set(key, []);
        }
        this.extractionStrategies.get(key).push(strategy);
      });

      logger.info(`Loaded ${strategies?.length || 0} extraction strategies`);
    } catch (error) {
      logger.error('Failed to load extraction strategies', error);
      // Fall back to basic parsing
      this.initializeBasicStrategies();
    }
  }

  private initializeBasicStrategies(): void {
    // Basic fallback parsing strategies
    const basicStrategies = {
      'govdeals.com_year': [
        { strategy: 'regex', config: { pattern: /\b(19|20)\d{2}\b/ } },
        { strategy: 'selector', config: { selector: '.year' } }
      ],
      'govdeals.com_make': [
        { strategy: 'regex', config: { pattern: /\b(Ford|Chevrolet|Toyota|Honda|Nissan|Dodge)\b/i } },
        { strategy: 'selector', config: { selector: '.make' } }
      ],
      'govdeals.com_model': [
        { strategy: 'regex', config: { pattern: /\b(F-150|Silverado|Camry|Accord|Altima|Ram)\b/i } },
        { strategy: 'selector', config: { selector: '.model' } }
      ]
    };

    Object.entries(basicStrategies).forEach(([key, strategies]) => {
      this.extractionStrategies.set(key, strategies);
    });
  }

  async parseContent(htmlContent: string, siteId: string): Promise<ParsedListing[]> {
    try {
      logger.debug(`Parsing content for site: ${siteId}`);
      
      // Create a DOM parser (in browser environment)
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlContent, 'text/html');
      
      const listings: ParsedListing[] = [];
      
      // Site-specific parsing logic
      switch (siteId) {
        case 'govdeals':
          listings.push(...await this.parseGovDeals(doc));
          break;
        case 'publicsurplus':
          listings.push(...await this.parsePublicSurplus(doc));
          break;
        case 'liquidation':
          listings.push(...await this.parseLiquidation(doc));
          break;
        default:
          listings.push(...await this.parseGeneric(doc, siteId));
      }

      logger.info(`Parsed ${listings.length} listings from ${siteId}`);
      return listings;

    } catch (error) {
      logger.error(`Failed to parse content for ${siteId}:`, error);
      return [];
    }
  }

  private async parseGovDeals(doc: Document): Promise<ParsedListing[]> {
    const listings: ParsedListing[] = [];
    
    // Look for auction listing containers
    const listingElements = doc.querySelectorAll('.auction-item, .listing-item, [class*="auction"]');
    
    for (const element of listingElements) {
      try {
        const listing: ParsedListing = {
          source_site: 'GovDeals',
          listing_url: this.extractListingUrl(element, 'govdeals'),
          year: await this.extractField(element, 'govdeals', 'year'),
          make: await this.extractField(element, 'govdeals', 'make'),
          model: await this.extractField(element, 'govdeals', 'model'),
          trim: await this.extractField(element, 'govdeals', 'trim'),
          mileage: await this.extractField(element, 'govdeals', 'mileage'),
          current_bid: await this.extractField(element, 'govdeals', 'current_bid'),
          location: await this.extractField(element, 'govdeals', 'location'),
          state: await this.extractField(element, 'govdeals', 'state'),
          vin: await this.extractField(element, 'govdeals', 'vin'),
          photo_url: this.extractPhotoUrl(element),
          description: this.extractDescription(element),
          auction_end: await this.extractField(element, 'govdeals', 'auction_end'),
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        };

        if (listing.listing_url && listing.year) {
          listings.push(listing);
        }
      } catch (error) {
        logger.debug('Failed to parse individual listing:', error);
      }
    }

    return listings;
  }

  private async parsePublicSurplus(doc: Document): Promise<ParsedListing[]> {
    const listings: ParsedListing[] = [];
    
    const listingElements = doc.querySelectorAll('.item, .product, [class*="listing"]');
    
    for (const element of listingElements) {
      try {
        const listing: ParsedListing = {
          source_site: 'PublicSurplus',
          listing_url: this.extractListingUrl(element, 'publicsurplus'),
          year: await this.extractField(element, 'publicsurplus', 'year'),
          make: await this.extractField(element, 'publicsurplus', 'make'),
          model: await this.extractField(element, 'publicsurplus', 'model'),
          current_bid: await this.extractField(element, 'publicsurplus', 'current_bid'),
          location: await this.extractField(element, 'publicsurplus', 'location'),
          photo_url: this.extractPhotoUrl(element),
          description: this.extractDescription(element),
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        };

        if (listing.listing_url) {
          listings.push(listing);
        }
      } catch (error) {
        logger.debug('Failed to parse PublicSurplus listing:', error);
      }
    }

    return listings;
  }

  private async parseLiquidation(doc: Document): Promise<ParsedListing[]> {
    const listings: ParsedListing[] = [];
    
    const listingElements = doc.querySelectorAll('.lot, .auction-lot, [class*="vehicle"]');
    
    for (const element of listingElements) {
      try {
        const listing: ParsedListing = {
          source_site: 'Liquidation.com',
          listing_url: this.extractListingUrl(element, 'liquidation'),
          year: await this.extractField(element, 'liquidation', 'year'),
          make: await this.extractField(element, 'liquidation', 'make'),
          model: await this.extractField(element, 'liquidation', 'model'),
          current_bid: await this.extractField(element, 'liquidation', 'current_bid'),
          location: await this.extractField(element, 'liquidation', 'location'),
          photo_url: this.extractPhotoUrl(element),
          description: this.extractDescription(element),
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString()
        };

        if (listing.listing_url) {
          listings.push(listing);
        }
      } catch (error) {
        logger.debug('Failed to parse Liquidation listing:', error);
      }
    }

    return listings;
  }

  private async parseGeneric(doc: Document, siteId: string): Promise<ParsedListing[]> {
    // Generic parsing fallback
    const listings: ParsedListing[] = [];
    
    const possibleContainers = doc.querySelectorAll('div, article, section, li');
    
    for (const element of possibleContainers) {
      const text = element.textContent || '';
      
      // Basic heuristics to identify vehicle listings
      if (this.looksLikeVehicleListing(text)) {
        try {
          const listing: ParsedListing = {
            source_site: siteId,
            listing_url: this.extractListingUrl(element, siteId),
            year: this.extractYearFromText(text),
            make: this.extractMakeFromText(text),
            model: this.extractModelFromText(text),
            description: text.substring(0, 500),
            is_active: true,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString()
          };

          if (listing.listing_url && listing.year) {
            listings.push(listing);
          }
        } catch (error) {
          logger.debug('Failed to parse generic listing:', error);
        }
      }
    }

    return listings;
  }

  private async extractField(element: Element, site: string, fieldName: string): Promise<any> {
    const strategies = this.extractionStrategies.get(`${site}_${fieldName}`) || [];
    
    for (const strategy of strategies) {
      try {
        let value = null;

        switch (strategy.strategy) {
          case 'selector':
            const targetElement = element.querySelector(strategy.config?.selector);
            value = targetElement?.textContent?.trim();
            break;
            
          case 'regex':
            const text = element.textContent || '';
            const match = text.match(strategy.config?.pattern);
            value = match?.[1] || match?.[0];
            break;
            
          case 'attribute':
            value = element.getAttribute(strategy.config?.attribute);
            break;
        }

        if (value) {
          return this.normalizeFieldValue(fieldName, value);
        }
      } catch (error) {
        logger.debug(`Extraction strategy failed for ${fieldName}:`, error);
      }
    }

    return null;
  }

  private normalizeFieldValue(fieldName: string, value: string): any {
    switch (fieldName) {
      case 'year':
        const year = parseInt(value);
        return (year >= 1900 && year <= 2030) ? year : null;
        
      case 'mileage':
        const mileage = parseInt(value.replace(/[^\d]/g, ''));
        return isNaN(mileage) ? null : mileage;
        
      case 'current_bid':
        const bid = parseFloat(value.replace(/[^\d.]/g, ''));
        return isNaN(bid) ? null : bid;
        
      case 'state':
        return value.toUpperCase().substring(0, 2);
        
      default:
        return value.trim();
    }
  }

  private extractListingUrl(element: Element, site: string): string {
    const linkElement = element.querySelector('a[href]') as HTMLAnchorElement;
    const href = linkElement?.href;
    
    if (!href) return '';
    
    // Ensure absolute URL
    if (href.startsWith('/')) {
      const baseUrls = {
        'govdeals': 'https://www.govdeals.com',
        'publicsurplus': 'https://www.publicsurplus.com',
        'liquidation': 'https://www.liquidation.com'
      };
      return (baseUrls[site] || '') + href;
    }
    
    return href;
  }

  private extractPhotoUrl(element: Element): string | null {
    const img = element.querySelector('img[src]') as HTMLImageElement;
    return img?.src || null;
  }

  private extractDescription(element: Element): string | null {
    const descElement = element.querySelector('.description, .details, .summary');
    return descElement?.textContent?.trim().substring(0, 500) || null;
  }

  private looksLikeVehicleListing(text: string): boolean {
    const vehicleKeywords = /\b(car|truck|vehicle|auto|ford|chevrolet|toyota|honda|nissan|dodge)\b/i;
    const yearPattern = /\b(19|20)\d{2}\b/;
    
    return vehicleKeywords.test(text) && yearPattern.test(text);
  }

  private extractYearFromText(text: string): number | null {
    const match = text.match(/\b(19|20)\d{2}\b/);
    return match ? parseInt(match[0]) : null;
  }

  private extractMakeFromText(text: string): string | null {
    const makes = ['Ford', 'Chevrolet', 'Toyota', 'Honda', 'Nissan', 'Dodge', 'BMW', 'Mercedes'];
    for (const make of makes) {
      if (text.toLowerCase().includes(make.toLowerCase())) {
        return make;
      }
    }
    return null;
  }

  private extractModelFromText(text: string): string | null {
    const models = ['F-150', 'Silverado', 'Camry', 'Accord', 'Altima', 'Ram', 'Civic', 'Corolla'];
    for (const model of models) {
      if (text.toLowerCase().includes(model.toLowerCase())) {
        return model;
      }
    }
    return null;
  }
}