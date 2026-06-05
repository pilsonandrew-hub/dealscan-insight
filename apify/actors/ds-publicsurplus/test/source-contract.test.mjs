import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');
const detailHandler = source.slice(
  source.indexOf("if (request.label === 'DETAIL_VIN')"),
  source.indexOf('// ── Texas State Surplus'),
);

describe('ds-publicsurplus source contract', () => {
  test('detail-page mileage extraction does not contain control-character word boundaries', () => {
    expect(source).not.toContain('\bMileage');
    expect(source).not.toContain('\bOdometer');
    expect(source).not.toContain('mi\b');
    expect(source).toContain('/\\bMileage[:\\s#\\-]*([\\d,]+)/i');
    expect(source).toContain('/\\bOdometer[:\\s#\\-]*([\\d,]+)/i');
    expect(source).toContain('(?:miles?|mi\\b)');
  });

  test('re-applies mileage cap after detail-page enrichment before publishing', () => {
    expect(source).toContain('const MAX_ALLOWED_MILEAGE = 100000;');
    expect(detailHandler).toContain('if (vehicle.mileage !== null && vehicle.mileage > MAX_ALLOWED_MILEAGE)');
    expect(detailHandler).toContain('return;');
    expect(detailHandler.indexOf('if (vehicle.mileage !== null && vehicle.mileage > MAX_ALLOWED_MILEAGE)'))
      .toBeLessThan(detailHandler.indexOf('await Actor.pushData(vehicle);'));
  });

  test('detail-enriches rows missing condition evidence even when VIN is already present', () => {
    expect(source).toContain('const detailQueue = [];');
    expect(source).toContain('function needsDetailEvidence(vehicle)');
    expect(source).toContain('if (listingUrl && detailPageCount < MAX_DETAIL_PAGES && (!vehicle.vin || needsDetailEvidence(vehicle)))');
  });

  test('detail-enriches Texas mobile rows before publishing when condition evidence is missing', () => {
    const txHandler = source.slice(
      source.indexOf('async function pushTXListing'),
      source.indexOf('const crawler = new PlaywrightCrawler'),
    );
    expect(txHandler).toContain('if (listingUrl && detailPageCount < MAX_DETAIL_PAGES && (!vehicle.vin || needsDetailEvidence(vehicle)))');
    expect(txHandler.indexOf('detailQueue.push(vehicle);')).toBeLessThan(txHandler.indexOf('await Actor.pushData(vehicle);'));
  });

  test('persists detail text and reruns source-policy rejects after detail enrichment', () => {
    expect(detailHandler).toContain('vehicle.detail_text = detailText;');
    expect(detailHandler).toContain('if (detailText && needsDetailEvidence(vehicle)) vehicle.description = detailText;');
    expect(detailHandler).toContain('if (hasConditionReject(vehicle))');
    expect(detailHandler.indexOf('if (hasConditionReject(vehicle))'))
      .toBeLessThan(detailHandler.indexOf('await Actor.pushData(vehicle);'));
  });

  test('source policy rejects backend title-brand damage and as-is warranty phrases', () => {
    expect(source).toContain('/\\bfront[\\s-]+end[\\s-]+damage\\b/i');
    expect(source).toContain('/\\brear[\\s-]+end[\\s-]+damage\\b/i');
    expect(source).toContain('/\\bside[\\s-]+damage\\b/i');
    expect(source).toContain('/\\bas[\\s-]?is\\b.*\\bno\\s+warrant|\\bno\\s+warrant.*\\bas[\\s-]?is\\b/i');
  });

  test('uses actual published row count for webhook itemCount', () => {
    expect(source).toContain('let totalPushed = 0;');
    expect(source).toContain('totalPushed++;');
    expect(source).toContain('itemCount: totalPushed');
    expect(source).not.toContain('itemCount: totalAfterFilters');
  });
});
