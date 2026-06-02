import { readFileSync } from 'fs';
import { resolve } from 'path';
import { describe, expect, test } from 'vitest';

const source = readFileSync(resolve('apify/actors/ds-govdeals/src/main_api.js'), 'utf8');

describe('ds-govdeals source quality proof contract', () => {
  test('emits a non-opportunity proof record for mileage and VIN diagnostics', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain("source_site: 'govdeals'");
    expect(source).toContain('detail_pages_attempted');
    expect(source).toContain('detail_pages_fetched');
    expect(source).toContain('detail_pages_failed');
    expect(source).toContain('detail_vins_found');
    expect(source).toContain('detail_mileages_found');
    expect(source).toContain('pushed_rows_total');
    expect(source).toContain('pushed_rows_with_vin');
    expect(source).toContain('pushed_rows_with_mileage');
    expect(source).toContain('pushed_rows_missing_vin');
    expect(source).toContain('pushed_rows_missing_mileage');
    expect(source).toContain('await Actor.pushData(proof)');
  });
});
