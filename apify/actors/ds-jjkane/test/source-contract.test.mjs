import { describe, expect, test } from 'vitest';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

function loadHelperExports() {
  const helperStart = source.indexOf('const CONDITION_REJECT_PATTERNS');
  const helperEnd = source.indexOf('// ── Marketcheck API');
  const helperSource = source.slice(helperStart, helperEnd) + `
({ extractVin, hasConditionReject, extractVinFromDetailHtml })`;
  return vm.runInNewContext(helperSource, {});
}

function loadMarketcheckExports(fetchImpl, marketcheckKeys = ['test-marketcheck-key']) {
  const marketcheckStart = source.indexOf('const marketcheckCache = new Map();');
  const marketcheckEnd = source.indexOf('// ── Algolia Query');
  const marketcheckSource = `
const MARKETCHECK_KEY = ${JSON.stringify(marketcheckKeys[0] || '')};
const MARKETCHECK_KEYS = ${JSON.stringify(marketcheckKeys)};
const MARKETCHECK_URL = 'https://marketcheck.example.test/search';
const AUCTION_DISCOUNT = 0.70;
function median(arr) {
  if (!arr || arr.length === 0) return null;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}
${source.slice(marketcheckStart, marketcheckEnd)}
({ getMarketcheckPrice })`;
  return vm.runInNewContext(marketcheckSource, {
    AbortSignal,
    URLSearchParams,
    console: { warn() {} },
    fetch: fetchImpl,
  });
}

describe('ds-jjkane source contract', () => {
  test('extracts VINs from JJ Kane serial-number source text before publish', () => {
    const helpers = loadHelperExports();

    expect(helpers.extractVin('s/n 1FM5K8AR2HGA24259, 3.7L V6')).toBe('1FM5K8AR2HGA24259');
    expect(helpers.extractVin('serial number: 1FM5K8AR5JGC94821')).toBe('1FM5K8AR5JGC94821');
    expect(helpers.extractVin('item number 1611970 with no vehicle identity')).toBeNull();

    expect(source).toContain('extractVin(conditionText)');
    expect(source).toContain('vin: vin || null');
  });

  test('extracts VIN identity from JJ Kane item detail pages before pricing', () => {
    const helpers = loadHelperExports();
    const detailHtml = `
      <table>
        <tr><th scope="row">Odometer:</th><td>39294</td></tr>
        <tr><th scope="row">VIN:</th><td>1FTFW1P86NKD26312</td></tr>
      </table>
    `;

    expect(helpers.extractVinFromDetailHtml(detailHtml)).toBe('1FTFW1P86NKD26312');
    expect(helpers.extractVinFromDetailHtml('<table><tr><th>VIN:</th><td></td></tr></table>')).toBeNull();

    expect(source.indexOf('const detailVin =')).toBeGreaterThan(source.indexOf('const vinFromSourceText ='));
    expect(source.indexOf('const detailVin =')).toBeLessThan(source.indexOf('const mcResult = await getMarketcheckPrice'));
    expect(source.indexOf("incrementCount(rejectionReasons, 'missing_vin')"))
      .toBeLessThan(source.indexOf('const mcResult = await getMarketcheckPrice'));
  });

  test('rejects JJ Kane defect and unknown-condition phrases before pricing', () => {
    const helpers = loadHelperExports();

    const blockedTexts = [
      'True Mileage Unknown State of Florida Unit (Wrecked) (Not Running, Condition Unknown) (Airbags Deployed, No Power)',
      'Wrecked, Airbags Deployed, Jump To Start, Does Not Move - Broken Axle, Dash Warning Indicators On',
      'Does Not Move, Condition Unknown, Check Engine Light On, ABS Light On, Traction Control Light On',
      'Branded Title - Police Vehicle',
    ];

    for (const text of blockedTexts) {
      expect(helpers.hasConditionReject(text)).toBe(true);
    }

    expect(
      helpers.hasConditionReject('This unit is being sold AS IS/WHERE IS via Timed Auction and is located in FL.')
    ).toBe(false);
  });

  test('emits source-quality proof before webhook even when no vehicles are pushed', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain("source: 'jjkane'");
    expect(source).toContain('found_rows_total: totalFound');
    expect(source).toContain('prefilter_passed_rows_total: totalPassed');
    expect(source).toContain('pushed_rows_total: totalPushed');
    expect(source).toContain('rows_excluded_missing_required_data');
    expect(source).toContain('rows_excluded_age_mileage_prefilter');
    expect(source).toContain('rows_excluded_policy_prefilter');
    expect(source).toContain('rows_excluded_bid_range');
    expect(source).toContain('rows_excluded_zero_pricing_signal');
    expect(source).toContain('rows_excluded_pricing_unavailable');
    expect(source.indexOf("record_type: 'source_quality_proof'"))
      .toBeLessThan(source.indexOf('if (effectiveWebhookUrl && datasetItemCount > 0)'));
  });

  test('classifies Marketcheck rate limits as pricing unavailable, not zero pricing', async () => {
    const helpers = loadMarketcheckExports(async () => ({
      ok: false,
      status: 429,
    }));

    await expect(
      helpers.getMarketcheckPrice(2022, 'Ford', 'F150 4x4 Police Responder', 39294)
    ).resolves.toEqual({
      pricing_unavailable: true,
      pricing_source: 'marketcheck_http_429',
    });
  });

  test('retries Marketcheck with the next configured key after a rate limit', async () => {
    const requestedKeys = [];
    const helpers = loadMarketcheckExports(async (url) => {
      requestedKeys.push(new URL(url).searchParams.get('api_key'));
      if (requestedKeys.length === 1) {
        return { ok: false, status: 429 };
      }
      return {
        ok: true,
        json: async () => ({
          listings: [
            { price: 30000, miles: 38000 },
            { price: 32000, miles: 41000 },
            { price: 34000, miles: 42000 },
          ],
        }),
      };
    }, ['rate-limited-key', 'live-key']);

    await expect(
      helpers.getMarketcheckPrice(2022, 'Ford', 'F150 4x4 Police Responder', 39294)
    ).resolves.toMatchObject({
      retail_median: 32000,
      estimated_auction_price: 22400,
    });
    expect(requestedKeys).toEqual(['rate-limited-key', 'live-key']);
  });
});
