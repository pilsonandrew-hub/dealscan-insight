import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

function loadTitleIdentityExports() {
  const helperStart = source.indexOf('const MAKE_NORMALIZATION');
  const helperEnd = source.indexOf('function normalizeLot');
  assert.notEqual(helperStart, -1, 'title identity constants must exist');
  assert.notEqual(helperEnd, -1, 'normalizeLot helper boundary must exist');
  const helperSource = `${source.slice(helperStart, helperEnd)}
({ parseVehicleIdentityFromTitle, withTitleVehicleIdentity })`;
  return vm.runInNewContext(helperSource, {});
}

test('EquipmentFacts derives vehicle identity from title before proof classification', () => {
  const helpers = loadTitleIdentityExports();

  const parsed = helpers.parseVehicleIdentityFromTitle(
    '2018 CHEVROLET EXPRESS 3500 Cargo / Straight Box Trucks',
  );
  assert.equal(parsed.year, 2018);
  assert.equal(parsed.make, 'Chevrolet');
  assert.equal(parsed.model, 'Express 3500');

  const enriched = helpers.withTitleVehicleIdentity({
    title: '2020 CHEVROLET EXPRESS 4500 Cutaway-Cube Box Trucks',
    currentBid: 0,
  });
  assert.equal(enriched.year, 2020);
  assert.equal(enriched.make, 'Chevrolet');
  assert.equal(enriched.model, 'Express 4500');
  assert.equal(enriched.currentBid, 0);
});

test('EquipmentFacts applies age and mileage proof before zero-pricing proof', () => {
  assert.ok(
    source.indexOf('const mileageValue = item.mileage ?? item.miles ?? item.meterCount ?? null;')
      < source.indexOf('const bid = parseFloat(item.currentBid || item.bidAmount || item.currentPrice || 0);'),
    'age/mileage proof must run before bid availability proof',
  );
});
