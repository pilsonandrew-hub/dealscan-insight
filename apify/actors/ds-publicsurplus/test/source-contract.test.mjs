import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

describe('ds-publicsurplus source contract', () => {
  test('detail-page mileage extraction does not contain control-character word boundaries', () => {
    expect(source).not.toContain('\bMileage');
    expect(source).not.toContain('\bOdometer');
    expect(source).not.toContain('mi\b');
    expect(source).toContain('/\\bMileage[:\\s#\\-]*([\\d,]+)/i');
    expect(source).toContain('/\\bOdometer[:\\s#\\-]*([\\d,]+)/i');
    expect(source).toContain('(?:miles?|mi\\b)');
  });
});
