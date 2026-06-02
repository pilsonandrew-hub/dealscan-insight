import { describe, expect, test } from 'vitest';
import vm from 'node:vm';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

function loadHelperExports() {
  const helperStart = source.indexOf('function normalizeText');
  const helperEnd = source.indexOf('function parseYear');
  const helperSource = source.slice(helperStart, helperEnd) + `
({ extractVin })`;
  return vm.runInNewContext(helperSource, {});
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
});
