import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

describe('ds-govplanet source contract', () => {
  test('does not publish vehicle rows without VIN identity', () => {
    const vinExtractionIndex = source.indexOf('const vin');
    const missingVinRejectIndex = source.indexOf('if (!vin)');
    const publishIndex = source.indexOf('records.push({');

    expect(vinExtractionIndex).toBeGreaterThan(-1);
    expect(missingVinRejectIndex).toBeGreaterThan(vinExtractionIndex);
    expect(missingVinRejectIndex).toBeLessThan(publishIndex);
    expect(source).toContain('missing_vin');
  });
});
