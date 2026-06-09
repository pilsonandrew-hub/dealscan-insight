import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

function loadProofHelpers() {
  const helperStart = source.indexOf('const SOURCE =');
  const helperEnd = source.indexOf('// ── Actor runtime');
  assert.notEqual(helperStart, -1, 'Purple Wave helpers must start at SOURCE constant');
  assert.notEqual(helperEnd, -1, 'Purple Wave actor runtime boundary must exist');
  const helperSource = `${source.slice(helperStart, helperEnd)}
({ normalizePurpleWaveLot, classifyPurpleWaveLot, buildSourceQualityProof })`;
  return vm.runInNewContext(helperSource, {});
}

test('Purple Wave normalizes identity, bid, mileage, state, and listing URL from public search rows', () => {
  const helpers = loadProofHelpers();

  const normalized = helpers.normalizePurpleWaveLot({
    auction: '260701',
    item: 'FH6629',
    title: '2021 GMC Sierra 1500 Crew Cab pickup',
    vin: '3GTU9DED8MG267110',
    mileage: '38,328 mi',
    current_bid: '$31,500',
    city: 'Oklahoma City',
    state: 'OK',
    close_date: '2026-06-18T18:00:00Z',
  });

  assert.equal(normalized.source_site, 'purplewave');
  assert.equal(normalized.source_type, 'purplewave_proof');
  assert.equal(normalized.year, 2021);
  assert.equal(normalized.make, 'GMC');
  assert.equal(normalized.model, 'Sierra 1500');
  assert.equal(normalized.vin, '3GTU9DED8MG267110');
  assert.equal(normalized.mileage, 38328);
  assert.equal(normalized.current_bid, 31500);
  assert.equal(normalized.state, 'OK');
  assert.equal(normalized.auction_end_time, '2026-06-18T18:00:00Z');
  assert.equal(normalized.listing_url, 'https://www.purplewave.com/auction/260701/item/FH6629');
});

test('Purple Wave proof does not invent listing URLs when auction identity is missing', () => {
  const helpers = loadProofHelpers();

  const normalized = helpers.normalizePurpleWaveLot({
    item_id: 12345,
    title: '2021 GMC Sierra 1500 Crew Cab pickup',
    vin: '3GTU9DED8MG267110',
    mileage: '38,328 mi',
    current_bid: '$31,500',
    city: 'Oklahoma City',
    state: 'OK',
  });

  assert.equal(normalized.listing_url, '');
});

test('Purple Wave derives state from public location markup when the state field is absent', () => {
  const helpers = loadProofHelpers();

  const normalized = helpers.normalizePurpleWaveLot({
    item_id: 12345,
    auction: '260701',
    item: 'FH6629',
    title: 'Wednesday July 01 Vehicles and Equipment Auction',
    first_line_description: '2021 GMC Sierra 1500 Crew Cab pickup truck',
    vin: '3GTU9DED8MG267110',
    description: '<span class="location">Energize Credit Union<br/>Oklahoma City, OK 73111</span>',
    additionalDescription: '<strong>Location</strong><br />Oklahoma City, OK 73111',
    sortgroups: { current_bid: 31500 },
    auction_timestamp: '2026-07-01T16:00:00.000Z',
  });

  assert.equal(normalized.state, 'OK');
  assert.equal(normalized.location, 'Oklahoma City, OK');
});

test('Purple Wave proof rejects proxy-only rows before accepted-yield delivery', () => {
  const helpers = loadProofHelpers();

  const row = helpers.normalizePurpleWaveLot({
    item_id: 98765,
    title: '2023 RAM 1500 Big Horn Crew Cab pickup',
    vin: '1C6RR7LG7PG675520',
    mileage: 42000,
    current_bid: 12500,
    state: 'AZ',
    close_date: '2026-06-19T18:00:00Z',
  });
  const classification = helpers.classifyPurpleWaveLot(row, { requireMarketPrice: true });

  assert.equal(classification.accepted, false);
  assert.equal(classification.reason, 'missing_market_price_evidence');
});

test('Purple Wave proof does not classify complete pickups as parts for equipment mentions', () => {
  const helpers = loadProofHelpers();

  const row = helpers.normalizePurpleWaveLot({
    item_id: 24680,
    title: '2023 RAM 1500 Big Horn Crew Cab pickup',
    vin: '1C6RR7LG7PG675520',
    mileage: 42000,
    current_bid: 12500,
    state: 'AZ',
    description: 'Runs and drives. Includes tonneau cover and tailgate step.',
    close_date: '2026-06-19T18:00:00Z',
  });
  const classification = helpers.classifyPurpleWaveLot(row, { requireMarketPrice: true });

  assert.equal(classification.accepted, false);
  assert.equal(classification.reason, 'missing_market_price_evidence');
});

test('Purple Wave proof does not classify complete pickups as parts for bed and camper shell mentions', () => {
  const helpers = loadProofHelpers();

  const row = helpers.normalizePurpleWaveLot({
    item_id: 24681,
    title: '2023 Ford F-150 SuperCrew pickup',
    vin: '1FTFW1E80PFA00001',
    mileage: 34000,
    current_bid: 14500,
    state: 'AZ',
    description: 'Runs and drives. Includes truck bed liner and camper shell.',
    close_date: '2026-06-19T18:00:00Z',
  });
  const classification = helpers.classifyPurpleWaveLot(row, { requireMarketPrice: true });

  assert.equal(classification.accepted, false);
  assert.equal(classification.reason, 'missing_market_price_evidence');
});

test('Purple Wave proof treats zero mileage as present identity data', () => {
  const helpers = loadProofHelpers();

  const row = helpers.normalizePurpleWaveLot({
    item_id: 24682,
    title: '2023 Toyota Tacoma pickup',
    vin: '3TYCZ5AN0PT000001',
    mileage: 0,
    current_bid: 14500,
    state: 'AZ',
    close_date: '2026-06-19T18:00:00Z',
  });
  const classification = helpers.classifyPurpleWaveLot(row, { requireMarketPrice: true });

  assert.equal(row.mileage, 0);
  assert.equal(classification.accepted, false);
  assert.equal(classification.reason, 'missing_market_price_evidence');
});

test('Purple Wave proof counts zero mileage as mileage on accepted proof rows', () => {
  const helpers = loadProofHelpers();

  const rows = [
    {
      ...helpers.normalizePurpleWaveLot({
        item_id: 24683,
        title: '2023 Toyota Tacoma pickup',
        vin: '3TYCZ5AN0PT000001',
        mileage: 0,
        current_bid: 14500,
        state: 'AZ',
        close_date: '2026-06-19T18:00:00Z',
      }),
      market_price_evidence_id: 'fixture-comp',
    },
  ];
  const proof = helpers.buildSourceQualityProof(rows, { requireMarketPrice: true });

  assert.equal(proof.prefilter_passed_rows_total, 1);
  assert.equal(proof.pushed_rows_total, 1);
  assert.equal(proof.pushed_rows_with_mileage, 1);
});

test('Purple Wave proof can represent fetch failure without pushed rows', () => {
  const helpers = loadProofHelpers();

  const proof = helpers.buildSourceQualityProof([], {
    requireMarketPrice: true,
    fetchFailed: true,
    fetchError: 'Purple Wave search failed with HTTP 503',
  });

  assert.equal(proof.record_type, 'source_quality_proof');
  assert.equal(proof.found_rows_total, 0);
  assert.equal(proof.pushed_rows_total, 0);
  assert.equal(proof.fetch_failed, true);
  assert.equal(proof.fetch_error, 'Purple Wave search failed with HTTP 503');
});

test('Purple Wave proof does not count partial fetch rows as pushed', () => {
  const helpers = loadProofHelpers();

  const rows = [
    {
      ...helpers.normalizePurpleWaveLot({
        item_id: 24684,
        title: '2023 Toyota Tacoma pickup',
        vin: '3TYCZ5AN0PT000002',
        mileage: 12000,
        current_bid: 14500,
        state: 'AZ',
        close_date: '2026-06-19T18:00:00Z',
      }),
      market_price_evidence_id: 'fixture-comp',
    },
  ];
  const proof = helpers.buildSourceQualityProof(rows, {
    requireMarketPrice: true,
    fetchFailed: true,
    fetchError: 'Purple Wave search failed with HTTP 503',
  });

  assert.equal(proof.found_rows_total, 1);
  assert.equal(proof.prefilter_passed_rows_total, 1);
  assert.equal(proof.pushed_rows_total, 0);
  assert.equal(proof.pushed_rows_with_vin, 0);
  assert.equal(proof.pushed_rows_with_mileage, 0);
  assert.equal(proof.pushed_rows_with_auction_end, 0);
  assert.equal(proof.fetch_failed, true);
});

test('Purple Wave proof summary accounts for identity-rich rows without pushing proxy-only rows', () => {
  const helpers = loadProofHelpers();

  const rows = [
    helpers.normalizePurpleWaveLot({
      item_id: 1,
      title: '2023 RAM 1500 Big Horn Crew Cab pickup',
      vin: '1C6RR7LG7PG675520',
      mileage: 42000,
      current_bid: 12500,
      state: 'AZ',
      close_date: '2026-06-19T18:00:00Z',
    }),
    helpers.normalizePurpleWaveLot({
      item_id: 2,
      title: '2012 Ford F-150 pickup',
      vin: '1FTFW1EF1CFA00001',
      mileage: 132000,
      current_bid: 4500,
      state: 'OK',
      close_date: '2026-06-19T18:00:00Z',
    }),
    helpers.normalizePurpleWaveLot({
      item_id: 3,
      title: 'Pickup bed and tailgate',
      vin: '',
      mileage: '',
      current_bid: 300,
      state: 'TX',
      close_date: '2026-06-19T18:00:00Z',
    }),
  ];
  const proof = helpers.buildSourceQualityProof(rows, { requireMarketPrice: true });

  assert.equal(proof.record_type, 'source_quality_proof');
  assert.equal(proof.found_rows_total, 3);
  assert.equal(proof.identity_complete_rows_total, 2);
  assert.equal(proof.prefilter_passed_rows_total, 0);
  assert.equal(proof.pushed_rows_total, 0);
  assert.equal(proof.rows_excluded_missing_market_price, 1);
  assert.equal(proof.rows_excluded_age_mileage_prefilter, 1);
  assert.equal(proof.rows_excluded_non_vehicle_part_prefilter, 1);
});
