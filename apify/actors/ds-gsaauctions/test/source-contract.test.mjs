import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

describe('ds-gsaauctions source contract', () => {
  test('uses lotId, not auctionId, for the public preview URL', () => {
    expect(source).toContain('const listingId = String(lotId);');
    expect(source).toContain('const listingUrl = `${BASE_UI_URL}/auctions/preview/${listingId}`;');
    expect(source).not.toContain('const listingId = String(auctionId || lotId);');
  });

  test('enriches candidates from the public sales preview detail endpoint before publish', () => {
    expect(source).toContain('const SALES_PREVIEW_URL');
    expect(source).toContain('async function fetchLotPreview');
    expect(source).toContain('await fetchLotPreview(lotId)');
    expect(source).toContain('auctionDescriptionDTO');
    expect(source).toContain('parsePreviewDetail');
  });

  test('keeps the strict VIN and mileage publish gates after detail enrichment', () => {
    const detailIndex = source.indexOf('await fetchLotPreview(lotId)');
    const rejectMissingVinIndex = source.indexOf('missing_vin_after_detail');
    const rejectMissingMileageIndex = source.indexOf('missing_mileage_after_detail');
    const publishIndex = source.indexOf('await Actor.pushData(record);');

    expect(detailIndex).toBeGreaterThan(-1);
    expect(rejectMissingVinIndex).toBeGreaterThan(detailIndex);
    expect(rejectMissingMileageIndex).toBeGreaterThan(detailIndex);
    expect(rejectMissingVinIndex).toBeLessThan(publishIndex);
    expect(rejectMissingMileageIndex).toBeLessThan(publishIndex);
  });

  test('emits source quality proof for list/detail field visibility', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain('list_rows_with_vin');
    expect(source).toContain('list_rows_with_mileage');
    expect(source).toContain('detail_pages_attempted');
    expect(source).toContain('detail_vins_found');
    expect(source).toContain('detail_mileages_found');
    expect(source).toContain('rows_excluded_missing_required_data');
  });
});
