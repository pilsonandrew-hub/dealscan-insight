import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const source = readFileSync(resolve('apify/actors/ds-proxibid/src/main.js'), 'utf8');

describe('ds-proxibid buyer-grade filter source contract', () => {
  test('enforces DealerScope max mileage and condition rejects found in live detail proof', () => {
    expect(source).toContain('mileage > 50000');
    expect(source).toContain('mileage_over_50k');
    expect(source).toContain('do\\s+not\\s+operate');
    expect(source).toContain('not\\s+operable');
  });
});
