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

  test('reruns backend policy rejects after detail enrichment before publish', () => {
    const detailIndex = source.indexOf('await fetchLotPreview(lotId)');
    const postDetailRejectIndex = source.indexOf('source_policy_rejected_after_detail');
    const publishIndex = source.indexOf('await Actor.pushData(record);');

    expect(source).toContain('/\\bfront[\\s-]+end[\\s-]+damage\\b/i');
    expect(source).toContain('/\\brear[\\s-]+end[\\s-]+damage\\b/i');
    expect(source).toContain('/\\bside[\\s-]+damage\\b/i');
    expect(source).toContain('/\\bas[\\s-]?is\\b.*\\bno\\s+warrant|\\bno\\s+warrant.*\\bas[\\s-]?is\\b/i');
    expect(source).toContain('/\\bneeds?\\s+trans(?:mission)?\\b/i');
    expect(source).toContain('/\\brequires?\\s+trans(?:mission)?(?:\\s+replacement)?\\b/i');
    expect(source).toContain('/\\btransmission\\s+(?:fail|issues?|problem|gone|dead|shot)s?\\b/i');
    expect(source).toContain('/\\bnot\\s+operational\\b/i');
    expect(source).toContain('/\\bneeds?\\s+engine\\b/i');
    expect(source).toContain('/\\bengine\\s+(?:knock|miss)\\b/i');
    expect(source).toContain('function hasConditionReject(record)');
    expect(postDetailRejectIndex).toBeGreaterThan(detailIndex);
    expect(postDetailRejectIndex).toBeLessThan(publishIndex);
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
