import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const ACTIVE_VEHICLE_ACTOR_SOURCES = [
  'apify/actors/ds-govdeals/src/main_api.js',
  'apify/actors/ds-publicsurplus/src/main.js',
  'apify/actors/ds-municibid/src/main.js',
  'apify/actors/ds-gsaauctions/src/main.js',
  'apify/actors/ds-allsurplus/src/main.js',
  'apify/actors/ds-govplanet/src/main.js',
  'apify/actors/ds-usgovbid/src/main.js',
  'apify/actors/ds-hibid-v2/src/main.js',
];

const REQUIRED_NON_VEHICLE_PART_TERMS = [
  'truck bed',
  'pickup bed',
  'camper shell',
  'tonneau',
  'bed cap',
  'utility body',
  'service body',
  'truck cap',
  'truck topper',
  'tailgate',
  'bed liner',
  'vehicle parts',
];

describe('active actor non-vehicle part source boundary', () => {
  test.each(ACTIVE_VEHICLE_ACTOR_SOURCES)('%s rejects vehicle-adjacent parts and accessories at source', (sourcePath) => {
    const source = readFileSync(resolve(sourcePath), 'utf8').toLowerCase();

    for (const term of REQUIRED_NON_VEHICLE_PART_TERMS) {
      expect(source, `${sourcePath} is missing source-boundary term: ${term}`).toContain(term);
    }
  });
});
