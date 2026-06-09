import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const sourcePath = fileURLToPath(new URL('../src/main.js', import.meta.url || import.meta.filename));
const source = readFileSync(sourcePath, 'utf8');

describe('AllSurplus detail enrichment source contract', () => {
  it('fetches asset detail before publish and maps mileage/VIN from Maestro detail truth', () => {
    expect(source).toContain('async function getAssetDetail');
    expect(source).toContain('${MAESTRO_URL}/assets/${assetId}/${accountId}/false');
    expect(source).toContain("'x-user-id': '-1'");
    expect(source).toContain("'x-api-correlation-id': correlationId");
    expect(source).toContain('enrichListingFromDetail');
    expect(source).toContain('detail.meterCount');
    expect(source).toContain('detail.vinserial');
    expect(source).toContain('stripHtmlToText(detail.assetLongDesc');
    expect(source).toContain('if (listing.mileage && failsDealerScopeAgeMileageGate(listing.year, listing.mileage))');
    expect(source).toContain('const STANDARD_MAX_MILES_PER_YEAR = 18000;');
    expect(source).toContain('await Actor.pushData(listing)');
  });

  it('keeps detail-enriched rows missing required VIN or mileage out of pushed opportunities', () => {
    const requiredGate = source.slice(
      source.indexOf('const missingRequiredReasons = []'),
      source.indexOf('if (REJECT_PATTERNS.some')
    );

    expect(requiredGate).toContain('missing_vin_after_detail');
    expect(requiredGate).toContain('missing_mileage_after_detail');
    expect(requiredGate).toContain('rowsExcludedMissingRequiredData++');
    expect(requiredGate).toContain('continue;');
    expect(requiredGate.indexOf('continue;')).toBeLessThan(source.indexOf('await Actor.pushData(listing)'));
  });

  it('mirrors backend title-brand policy phrases after detail enrichment before publish', () => {
    const rejectPatterns = source.slice(
      source.indexOf('const REJECT_PATTERNS = ['),
      source.indexOf('// Commercial/fleet patterns')
    );
    const detailRejectGate = source.slice(
      source.indexOf("if (REJECT_PATTERNS.some((pattern) => pattern.test(listing.description || listing.title || '')))"),
      source.indexOf('totalPassed++')
    );

    expect(rejectPatterns).toMatch(/as\[\\s-\]\?is/);
    expect(rejectPatterns).toMatch(/no\\s\+warrant/);
    expect(detailRejectGate).toContain('continue;');
    expect(source.indexOf("if (REJECT_PATTERNS.some((pattern) => pattern.test(listing.description || listing.title || '')))"))
      .toBeLessThan(source.indexOf('await Actor.pushData(listing)'));
  });

  it('rejects condition-trust phrases from detail enrichment before publish', () => {
    const rejectPatterns = source.slice(
      source.indexOf('const REJECT_PATTERNS = ['),
      source.indexOf('// Commercial/fleet patterns')
    );
    const detailRejectGate = source.slice(
      source.indexOf("if (REJECT_PATTERNS.some((pattern) => pattern.test(listing.description || listing.title || '')))"),
      source.indexOf('totalPassed++')
    );

    expect(rejectPatterns).toMatch(/sold\\s\+as\\s\+is/);
    expect(rejectPatterns).toMatch(/sold\\b\[\\s"'\\u201c\\u201d\]\+as\[\\s"'\\u201c\\u201d\]\+is/);
    expect(rejectPatterns).toMatch(/no\\s\+\(\?:guarantees\?\|warrant\(\?:y\|ies\)\)/);
    expect(detailRejectGate).toContain('continue;');
    expect(source.indexOf("if (REJECT_PATTERNS.some((pattern) => pattern.test(listing.description || listing.title || '')))"))
      .toBeLessThan(source.indexOf('await Actor.pushData(listing)'));
  });

  it('emits source-quality proof counters and samples', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain('found_rows_total: totalFound');
    expect(source).toContain('pushed_rows_total: totalPassed');
    expect(source).toContain('detail_pages_attempted: detailPagesAttempted');
    expect(source).toContain('detail_vins_found: detailVinsFound');
    expect(source).toContain('detail_mileages_found: detailMileagesFound');
    expect(source).toContain('rows_excluded_missing_required_data: rowsExcludedMissingRequiredData');
    expect(source).toContain('excluded_missing_required_samples: excludedMissingRequiredSamples');
  });

  it('accounts for every pre-detail and post-detail discard after found row counting', () => {
    expect(source).toContain('rowsExcludedDuplicate++');
    expect(source).toContain('rowsExcludedNonVehicle++');
    expect(source).toContain('rowsExcludedNonUsState++');
    expect(source).toContain('rowsExcludedNonUsdCurrency++');
    expect(source).toContain('rowsExcludedRustState++');
    expect(source).toContain('rowsExcludedNonTargetState++');
    expect(source).toContain('rowsExcludedBidRange++');
    expect(source).toContain('rowsExcludedAgeMileagePrefilter++');
    expect(source).toContain('rowsExcludedAgeMileageAfterDetail++');
    expect(source).toContain('rowsExcludedPolicyAfterDetail++');
    expect(source).toContain('const accountedRows = totalPassed');
    expect(source).toContain('rows_excluded_unaccounted_after_prefilter: Math.max(0, totalFound - accountedRows)');
  });

  it('does not send an empty webhook secret when actor env vars are absent', () => {
    expect(source).toContain('DEFAULT_WEBHOOK_SECRET');
    expect(source).toContain('process.env.WEBHOOK_SECRET || DEFAULT_WEBHOOK_SECRET');
    expect(source).not.toContain("'X-Apify-Webhook-Secret': process.env.WEBHOOK_SECRET || ''");
  });
});
