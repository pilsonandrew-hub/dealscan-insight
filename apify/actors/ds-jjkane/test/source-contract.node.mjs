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
