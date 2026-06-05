import { describe, expect, test } from 'vitest';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = readFileSync(resolve('apify/actors/ds-proxibid/src/main.js'), 'utf8');

function loadParserExports() {
  const parserStart = source.indexOf('function normalize(text) {');
  const parserCoreEnd = source.indexOf('const crawler = new PlaywrightCrawler({');
  const detailStart = source.indexOf('function decodeHtmlEntities(text) {');
  const detailEnd = source.indexOf('async function enrichFromDetailPages(log) {');
  const parserSource = source.slice(parserStart, parserCoreEnd) + source.slice(detailStart, detailEnd) + `
({ detailTextFromHtml, parseMileage, parseVin })`;
  return vm.runInNewContext(parserSource, {});
}

const scraper = loadParserExports();

describe('ds-proxibid buyer-grade filter source contract', () => {
  test('enforces DealerScope max mileage and condition rejects found in live detail proof', () => {
    expect(source).toContain('mileage > 50000');
    expect(source).toContain('mileage_over_50k');
    expect(source).toContain('do\\s+not\\s+operate');
    expect(source).toContain('not\\s+operable');
  });

  test('extracts Proxibid detail-page VIN and mileage from robust meta description parsing', () => {
    const html = '<html><head><meta name="description" content="2015 Dodge Ram 2500 Pickup - 59,760 Miles on Meter SN# 3C6MR5AL7FG509771"></head><body></body></html>';
    const text = scraper.detailTextFromHtml(html);
    expect(scraper.parseVin(text)).toBe('3C6MR5AL7FG509771');
    expect(scraper.parseMileage(text)).toBe(59760);
  });

  test('extracts meta content with content-first attribute order and apostrophe entity', () => {
    const html = '<meta content="Seller&#39;s notes 44,321 Miles on Meter Serial Number: 1GTHK24K58E139687" name="description">';
    const text = scraper.detailTextFromHtml(html);
    expect(text).toContain("Seller's notes");
    expect(scraper.parseVin(text)).toBe('1GTHK24K58E139687');
    expect(scraper.parseMileage(text)).toBe(44321);
  });

  test('does not treat Proxibid driving directions as odometer mileage', () => {
    expect(scraper.parseMileage('Driving Directions: Approximately 12.4 miles west of I-35 and Hwy 6 Intersection')).toBeNull();
    expect(scraper.parseMileage('Driving Directions: 4 Miles West of US Hwy 27 on State Rd 66 Sebring Florida.')).toBeNull();
  });

  test('still extracts odometer-labeled mileage from detail text', () => {
    expect(scraper.parseMileage('Odometer shows 12,345 miles. VIN: 1GTHK24K58E139687')).toBe(12345);
    expect(scraper.parseMileage('Seller notes: 44,321 Miles on Meter Serial Number: 1GTHK24K58E139687')).toBe(44321);
    expect(scraper.parseMileage('2017 FORD FUSION 4 DOOR CAR, S/N 3FA6P0HD0HR334611, 4CYL, AUTO, OD READS 135620 MILES')).toBe(135620);
  });

  test('prefers primary item-detail miles over unrelated Proxibid page chrome', () => {
    const text = [
      'Similar Items 2016 FORD Explorer SUV VIN: 1FM5K8ARXGGA78391. Odometer: 89, $650.00 20d 1h Left',
      'Overview of 2016 GMC Arcadia VIN 5483 Item Details VIN 1GKKRPKD9GJ335483, NC TITLE, 145,983 Miles, Runs and drives',
      'Payment PAYMENT INSTRUCTIONS',
    ].join(' ');
    expect(scraper.parseMileage(text)).toBe(145983);
  });

  test('keeps mileage-labeled values without requiring a repeated unit', () => {
    expect(scraper.parseMileage('Item Details VIN 1GKKRPKD9GJ335483 Mileage: 12345 Payment')).toBe(12345);
  });

  test('does not let primary-section distance text beat VIN-adjacent mileage', () => {
    const text = [
      'Item Details pickup location is approximately 12 miles from the airport.',
      'VIN 1GKKRPKD9GJ335483, NC TITLE, 145,983 Miles, Runs and drives',
      'Payment PAYMENT INSTRUCTIONS',
    ].join(' ');
    expect(scraper.parseMileage(text)).toBe(145983);
  });

  test('does not treat unlabeled price-adjacent Proxibid odometer chrome as mileage', () => {
    expect(scraper.parseMileage('Similar Items 2016 FORD Explorer SUV VIN: 1FM5K8ARXGGA78391. Odometer: 89, $650.00 20d 1h Left')).toBeNull();
  });

  test('targets the Cars menu selections directly before VIN/odometer detail extraction', () => {
    const navigationIndex = source.indexOf("const CATEGORY_NAVIGATION_PATH = ['Vehicles', 'Cars & Vehicles', 'Cars'];");
    const selectableIndex = source.indexOf('function selectedTargetCategories(rawTargetCategories)');
    const suvIndex = source.indexOf("path: '/for-sale/cars-vehicles/suv-s'");
    const sedansIndex = source.indexOf("path: '/for-sale/cars-vehicles/sedans'");
    const wagonsIndex = source.indexOf("path: '/for-sale/cars-vehicles/wagons'");
    const coupesIndex = source.indexOf("path: '/for-sale/cars-vehicles/coupes'");
    const hatchbacksIndex = source.indexOf("path: '/for-sale/cars-vehicles/hatchbacks'");
    const sportsIndex = source.indexOf("path: '/for-sale/cars-vehicles/sports-cars'");
    const hybridsIndex = source.indexOf("path: '/for-sale/cars-vehicles/hybrid-cars'");
    const broadCarsIndex = source.indexOf("path: '/for-sale/cars-vehicles/cars'");
    const trucksIndex = source.indexOf("path: '/for-sale/cars-vehicles/trucks'");

    expect(navigationIndex).toBeGreaterThan(-1);
    expect(selectableIndex).toBeGreaterThan(navigationIndex);
    expect(source).toContain('targetCategories = ""');
    expect(source).toContain('selectedTargetCategories(targetCategories)');
    expect(source).toContain('No valid Proxibid target categories selected');
    expect(suvIndex).toBeGreaterThan(navigationIndex);
    expect(sedansIndex).toBeGreaterThan(suvIndex);
    expect(wagonsIndex).toBeGreaterThan(sedansIndex);
    expect(coupesIndex).toBeGreaterThan(wagonsIndex);
    expect(hatchbacksIndex).toBeGreaterThan(coupesIndex);
    expect(sportsIndex).toBeGreaterThan(hatchbacksIndex);
    expect(hybridsIndex).toBeGreaterThan(sportsIndex);
    expect(broadCarsIndex).toBe(-1);
    expect(trucksIndex).toBe(-1);
  });

  test('defaults detail enrichment to 200 pages while preserving input override', () => {
    expect(source).toContain('maxDetailPages = 200');
    expect(source).toContain('const detailLimit = Math.min(Math.max(Number(maxDetailPages) || 200, 0), 250);');
    expect(source).toContain('lotsNeedingDetail.slice(0, detailLimit)');
  });

  test('actor metadata allows the 200-page enrichment default to run without schema clipping or timeout truncation', () => {
    const inputSchema = JSON.parse(readFileSync(resolve('apify/actors/ds-proxibid/.actor/input_schema.json'), 'utf8'));
    const actorConfig = JSON.parse(readFileSync(resolve('apify/actors/ds-proxibid/.actor/actor.json'), 'utf8'));
    expect(inputSchema.properties.maxDetailPages.default).toBe(200);
    expect(inputSchema.properties.maxDetailPages.maximum).toBeGreaterThanOrEqual(200);
    expect(actorConfig.defaultRunOptions.timeoutSecs).toBeGreaterThanOrEqual(900);
    expect(actorConfig.defaultRunOptions.memoryMbytes).toBeGreaterThanOrEqual(1024);
  });

  test('emits structured enrichment proof without publishing rejected detail rows as opportunities', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain('detail_pages_attempted');
    expect(source).toContain('detail_vins_found');
    expect(source).toContain('detail_mileages_found');
    expect(source).toContain('accepted_rows_total');
    expect(source).toContain('rejected_rows_total');
    expect(source).toContain('accepted_rows_with_vin');
    expect(source).toContain('accepted_rows_with_mileage');
    expect(source).toContain('enriched_rows_rejected');
    expect(source).toContain('rejected_enriched_samples');
    expect(source).toContain('detail_enriched_by_detail_page');
    expect(source).toContain('actor_run_id: actorRunId');
    expect(source).toContain('source_run_id: actorRunId');
    expect(source).toContain('run_id: actorRunId');
    expect(source).toContain('actorRunId: env.actorRunId');
    expect(source).toContain('defaultDatasetId: dataset.id');
    expect(source).toContain('provenance_fields');
    expect(source).toContain('input_contract');
    expect(source).toContain('category_navigation_path');
    expect(source).toContain('targeted_categories');
    expect(source).toContain('targetCategories');
    expect(source).toContain('source_category_label');
    expect(source).toContain('source_category_path');
    expect(source).toContain('source_navigation_path');
    expect(source).toContain('actor_timeout_secs_expected: 900');
    expect(source).toContain('await Actor.pushData(proof)');
    expect(source).toContain('!lot.rejected_after_detail');
    expect(source).toContain('applyBuyerGradeFilters(lot).length === 0');
  });

  test('requires VIN and mileage before publishing Proxibid opportunity rows', () => {
    expect(source).toContain('rows_excluded_missing_required_data');
    expect(source).toContain('missing_required_data');
    expect(source).toContain('lot.vin && lot.mileage');
    expect(source).toContain('pushed_rows_total');
    expect(source).toContain('pushed_rows_with_vin');
    expect(source).toContain('pushed_rows_with_mileage');
  });

  test('uses a non-empty webhook secret fallback and logs real webhook HTTP status', () => {
    expect(source).toContain('DEFAULT_WEBHOOK_SECRET');
    expect(source).toContain("process.env.WEBHOOK_SECRET || DEFAULT_WEBHOOK_SECRET");
    expect(source).toContain('const webhookResponse = await fetch');
    expect(source).toContain('webhookResponse.status');
    expect(source).toContain('webhookResponse.ok');
  });

});
