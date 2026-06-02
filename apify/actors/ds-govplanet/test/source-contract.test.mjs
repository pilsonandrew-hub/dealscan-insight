import { describe, expect, test } from 'vitest';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');
const inputSchema = JSON.parse(readFileSync(join(__dirname, '../.actor/input_schema.json'), 'utf8'));

function loadHelperExports() {
  const helperStart = source.indexOf('const HIGH_RUST');
  const helperEnd = source.indexOf('// ── Parse quickviews');
  const helperSource = source.slice(helperStart, helperEnd) + `
({ extractVin, parseDetailVin, parseAuctionEnd, passesFilters, isGovPlanetMarketplace })`;
  return vm.runInNewContext(helperSource, {});
}

describe('ds-govplanet source contract', () => {
  test('does not publish vehicle rows without VIN identity', () => {
    const vinExtractionIndex = source.indexOf('const vin');
    const missingVinRejectIndex = source.indexOf('missing_vin_without_detail');
    const publishIndex = source.indexOf('records.push(vehicle)');

    expect(vinExtractionIndex).toBeGreaterThan(-1);
    expect(missingVinRejectIndex).toBeGreaterThan(vinExtractionIndex);
    expect(missingVinRejectIndex).toBeLessThan(publishIndex);
    expect(source).toContain('missing_vin');
  });

  test('extracts labeled VINs from GovPlanet detail text', () => {
    const helpers = loadHelperExports();

    expect(helpers.extractVin('VIN: 1FTFW1E50JFA12345')).toBe('1FTFW1E50JFA12345');
    expect(helpers.parseDetailVin('Vehicle Identification Number 1FTFW1E50JFA12345')).toBe('1FTFW1E50JFA12345');
    expect(helpers.parseDetailVin('Serial Number: 3C6UR5DL8JG123456')).toBe('3C6UR5DL8JG123456');
    expect(helpers.parseDetailVin('Lot number 15280228 and no vehicle identity')).toBeNull();
  });

  test('parses GovPlanet date-style auction end labels', () => {
    const helpers = loadHelperExports();
    const now = new Date('2026-06-02T10:00:00.000Z');

    expect(helpers.parseAuctionEnd('Jun 10', now)).toBe('2026-06-10T23:59:59.000Z');
    expect(helpers.parseAuctionEnd('2 days 3 hours', now)).toBe('2026-06-04T13:00:00.000Z');
    expect(helpers.parseAuctionEnd('', now)).toBeNull();
  });

  test('enforces GovPlanet max mileage and max age input gates before publish', () => {
    const helpers = loadHelperExports();

    expect(helpers.passesFilters({
      year: 2022,
      price: 12000,
      state: 'CA',
      locationText: 'Los Angeles, CA',
      mileage: 149039,
      maxMileage: 100000,
      maxAgeYears: 10,
    })).toBe(false);

    expect(helpers.passesFilters({
      year: 2018,
      price: 12000,
      state: 'CA',
      locationText: 'Los Angeles, CA',
      mileage: 42000,
      maxMileage: 100000,
      maxAgeYears: 4,
    })).toBe(false);
  });

  test('defaults GovPlanet source gates to DealerScope buyer-grade limits', () => {
    expect(source).toContain('maxMileage = 50000');
    expect(source).toContain('maxAgeYears = 4');
    expect(inputSchema.properties.maxMileage.default).toBe(50000);
    expect(inputSchema.properties.maxAgeYears.default).toBe(4);
  });

  test('keeps IronPlanet family aggregate rows out of the GovPlanet actor', () => {
    const helpers = loadHelperExports();

    expect(helpers.isGovPlanetMarketplace({ marketplace: 'G' })).toBe(true);
    expect(helpers.isGovPlanetMarketplace({ marketplace: 'I' })).toBe(false);
    expect(helpers.isGovPlanetMarketplace({ marketplace: 'M' })).toBe(false);
    expect(helpers.isGovPlanetMarketplace({ marketplace: 'T' })).toBe(false);
    expect(helpers.isGovPlanetMarketplace({ marketplace: 'S' })).toBe(false);
    expect(source).toContain('rows_excluded_non_govplanet_marketplace');
  });

  test('queues capped detail enrichment before rejecting list rows without VIN', () => {
    const detailQueueIndex = source.indexOf('await queue.addRequest({');
    const missingVinRejectIndex = source.indexOf('missing_vin_without_detail');
    const publishIndex = source.indexOf('records.push(vehicle)');

    expect(source).toContain('maxDetailPages = 120');
    expect(source).toContain("request.userData?.kind === 'detail'");
    expect(source).toContain('totalDetailQueued < maxDetailPages');
    expect(detailQueueIndex).toBeGreaterThan(-1);
    expect(missingVinRejectIndex).toBeGreaterThan(detailQueueIndex);
    expect(missingVinRejectIndex).toBeLessThan(publishIndex);
  });

  test('publishes detail-enriched rows only after detail VIN recovery', () => {
    const detailStart = source.indexOf("request.userData?.kind === 'detail'");
    const detailEnd = source.indexOf('// ── Parse total items ──');
    const detailHandler = source.slice(detailStart, detailEnd);

    expect(detailHandler).toContain('const detailVin = parseDetailVin(html);');
    expect(detailHandler).toContain('if (!detailVin)');
    expect(detailHandler).toContain('missing_vin_after_detail');
    expect(detailHandler).toContain('vin: detailVin');
    expect(detailHandler.indexOf('if (!detailVin)')).toBeLessThan(detailHandler.indexOf('await Actor.pushData(enriched);'));
  });

  test('emits source quality proof with VIN, auction end, and detail captcha counters', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain('source_site: SOURCE');
    expect(source).toContain('quickview_rows_with_vin');
    expect(source).toContain('quickview_rows_with_auction_end');
    expect(source).toContain('pushed_rows_missing_vin');
    expect(source).toContain('rows_excluded_mileage_over_limit');
    expect(source).toContain('rows_excluded_age_over_limit');
    expect(source).toContain('detail_pages_captcha');
    expect(source).toContain('detail_captcha_samples');
    expect(source).toContain('[SOURCE QUALITY PROOF]');
  });
});
