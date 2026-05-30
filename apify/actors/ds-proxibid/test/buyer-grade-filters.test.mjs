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

  test('defaults detail enrichment to 200 pages while preserving input override', () => {
    expect(source).toContain('maxDetailPages = 200');
    expect(source).toContain('const detailLimit = Number(maxDetailPages) || 200;');
    expect(source).toContain('lotsNeedingDetail.slice(0, detailLimit)');
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
    expect(source).toContain('await Actor.pushData(proof)');
    expect(source).toContain('.filter(lot => !lot.rejected_after_detail && applyBuyerGradeFilters(lot).length === 0)');
  });

});
