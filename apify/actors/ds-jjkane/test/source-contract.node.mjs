import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

function loadHelperExports() {
  const helperStart = source.indexOf('const CONDITION_REJECT_PATTERNS');
  const helperEnd = source.indexOf('// ── Marketcheck API');
  const helperSource = source.slice(helperStart, helperEnd) + `
({ hasConditionReject })`;
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

test('JJKane rejects defect and unknown-condition phrases before pricing', () => {
  const helpers = loadHelperExports();
  const blockedTexts = [
    'True Mileage Unknown State of Florida Unit (Wrecked) (Not Running, Condition Unknown) (Airbags Deployed, No Power)',
    'Wrecked, Airbags Deployed, Jump To Start, Does Not Move - Broken Axle, Dash Warning Indicators On',
    'Does Not Move, Condition Unknown, Check Engine Light On, ABS Light On, Traction Control Light On',
    'Branded Title - Police Vehicle',
  ];

  for (const text of blockedTexts) {
    assert.equal(helpers.hasConditionReject(text), true, text);
  }

  assert.equal(
    helpers.hasConditionReject('This unit is being sold AS IS/WHERE IS via Timed Auction and is located in FL.'),
    false,
    'JJ Kane boilerplate AS IS/WHERE IS is not sufficient source-policy evidence by itself',
  );
});

test('JJKane classifies Marketcheck rate limits as pricing unavailable, not zero pricing', async () => {
  const helpers = loadMarketcheckExports(async () => ({
    ok: false,
    status: 429,
  }));

  const result = await helpers.getMarketcheckPrice(2022, 'Ford', 'F150 4x4 Police Responder', 39294);

  assert.equal(result.pricing_unavailable, true);
  assert.equal(result.pricing_source, 'marketcheck_http_429');
});

test('JJKane retries Marketcheck with the next configured key after a rate limit', async () => {
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

  const result = await helpers.getMarketcheckPrice(2022, 'Ford', 'F150 4x4 Police Responder', 39294);

  assert.equal(result.retail_median, 32000);
  assert.equal(result.estimated_auction_price, 22400);
  assert.deepEqual(requestedKeys, ['rate-limited-key', 'live-key']);
});
