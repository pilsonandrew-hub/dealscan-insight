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
    expect(source).toContain('/\\blow\\s+cylinder\\s+compression\\b/i');
    expect(source).toContain('/\\bcoolant\\s+leaks?\\b/i');
    expect(source).toContain('/\\brequires?\\s+engine\\s+(?:inspection|repair)\\b/i');
    expect(source).toContain('function hasConditionReject(record)');
    expect(postDetailRejectIndex).toBeGreaterThan(detailIndex);
    expect(postDetailRejectIndex).toBeLessThan(publishIndex);
  });

  test('blocks backend commercial-duty tonnage before publish', () => {
    expect(source).toContain('const COMMERCIAL_DUTY_PATTERN = /\\b(?:4500|5500)\\b/i;');
    expect(source).toContain('if (COMMERCIAL_DUTY_PATTERN.test(title)) return false;');
    expect(source).toContain('box\\s*truck');
    expect(source).toContain('bucket\\s*truck');
    expect(source).toContain('utility\\s*bed');
  });

  test('mirrors backend standard-lane age and mileage gates before publish', () => {
    expect(source).toContain('const DEFAULT_MIN_YEAR = CURRENT_YEAR - 10;');
    expect(source).toContain('const DEFAULT_MAX_MILEAGE = 100000;');
    expect(source).toContain('const STANDARD_MAX_MILES_PER_YEAR = 18000;');
    expect(source).toContain('if (failsDealerScopeAgeMileageGate(year, record.mileage)) {');
    expect(source).toContain('reason=age_or_mileage_rejected_after_detail');
    expect(source).toContain('rows_excluded_age_or_mileage');
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

  test('accounts for every pre-detail discard after found row counting', () => {
    expect(source).toContain('rows_excluded_non_vehicle');
    expect(source).toContain('rows_excluded_search_filter');
    expect(source).toContain('rows_excluded_non_us_state');
    expect(source).toContain('rows_excluded_bid_range');

    const foundIndex = source.indexOf('totalFound++;');
    const nonVehicleIndex = source.indexOf('rowsExcludedNonVehicle++;');
    const searchIndex = source.indexOf('rowsExcludedSearchFilter++;');
    const stateIndex = source.indexOf('rowsExcludedNonUsState++;');
    const bidIndex = source.indexOf('rowsExcludedBidRange++;');
    const yearIndex = source.indexOf('rowsExcludedAgeOrMileage++;');
    const detailIndex = source.indexOf('await fetchLotPreview(lotId)');

    for (const index of [nonVehicleIndex, searchIndex, stateIndex, bidIndex, yearIndex]) {
      expect(index).toBeGreaterThan(foundIndex);
      expect(index).toBeLessThan(detailIndex);
    }
  });
});
