import { describe, expect, test } from 'vitest';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

function loadHelperExports() {
  const helperStart = source.indexOf('function extractVin');
  const helperEnd = source.indexOf('// ── Parse quickviews');
  const helperSource = source.slice(helperStart, helperEnd) + `
({ extractVin, parseDetailVin })`;
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
});
