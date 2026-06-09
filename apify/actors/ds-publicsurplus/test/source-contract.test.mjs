import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');
const detailHandler = source.slice(
  source.indexOf("if (request.label === 'DETAIL_VIN')"),
  source.indexOf('// ── Texas State Surplus'),
);

describe('ds-publicsurplus source contract', () => {
  test('detail-page mileage extraction does not contain control-character word boundaries', () => {
    expect(source).not.toContain('\bMileage');
    expect(source).not.toContain('\bOdometer');
    expect(source).not.toContain('mi\b');
    expect(source).toContain('/\\bMileage[:\\s#\\-]*([\\d,]+)/i');
    expect(source).toContain('/\\bOdometer[:\\s#\\-]*([\\d,]+)/i');
    expect(source).toContain('(?:miles?|mi\\b)');
  });

  test('re-applies standard-lane age/mileage cap after detail-page enrichment before publishing', () => {
    expect(source).toContain('const STANDARD_MAX_MILEAGE = 100000;');
    expect(source).toContain('const STANDARD_MAX_MILES_PER_YEAR = 18000;');
    expect(detailHandler).toContain('if (vehicle.mileage !== null && failsDealerScopeAgeMileageGate(vehicle.year, vehicle.mileage))');
    expect(detailHandler).toContain('return;');
    expect(detailHandler.indexOf('if (vehicle.mileage !== null && failsDealerScopeAgeMileageGate(vehicle.year, vehicle.mileage))'))
      .toBeLessThan(detailHandler.indexOf('await pushVehicle(vehicle);'));
  });

  test('mirrors backend standard-lane max-age gate before publishing standard and Texas rows', () => {
    expect(source).toContain('const STANDARD_MAX_AGE_YEARS = 10;');
    expect(source).toContain('age > STANDARD_MAX_AGE_YEARS');
    expect(source.match(/age > STANDARD_MAX_AGE_YEARS/g)).toHaveLength(1);
    expect(source).toContain('failsDealerScopeAgeMileageGate(year, mileage, currentYear)');
  });

  test('detail-enriches rows missing condition evidence even when VIN is already present', () => {
    expect(source).toContain('const detailQueue = [];');
    expect(source).toContain('function needsDetailEvidence(vehicle)');
    expect(source).toContain('if (listingUrl && detailPageCount < MAX_DETAIL_PAGES && (!vehicle.vin || needsDetailEvidence(vehicle)))');
  });

  test('detail-enriches Texas mobile rows before publishing when condition evidence is missing', () => {
    const txHandler = source.slice(
      source.indexOf('async function pushTXListing'),
      source.indexOf('const crawler = new PlaywrightCrawler'),
    );
    expect(txHandler).toContain('if (listingUrl && detailPageCount < MAX_DETAIL_PAGES && (!vehicle.vin || needsDetailEvidence(vehicle)))');
    expect(txHandler.indexOf('detailQueue.push(vehicle);')).toBeLessThan(txHandler.indexOf('await pushVehicle(vehicle);'));
  });

  test('persists detail text and reruns source-policy rejects after detail enrichment', () => {
    expect(detailHandler).toContain('vehicle.detail_text = detailText;');
    expect(detailHandler).toContain('if (detailText && needsDetailEvidence(vehicle)) vehicle.description = detailText;');
    expect(detailHandler).toContain('if (hasConditionReject(vehicle))');
    expect(detailHandler.indexOf('if (hasConditionReject(vehicle))'))
      .toBeLessThan(detailHandler.indexOf('await pushVehicle(vehicle);'));
  });

  test('source policy rejects backend title-brand damage and as-is warranty phrases', () => {
    expect(source).toContain('/\\bfront[\\s-]+end[\\s-]+damage\\b/i');
    expect(source).toContain('/\\brear[\\s-]+end[\\s-]+damage\\b/i');
    expect(source).toContain('/\\bside[\\s-]+damage\\b/i');
    expect(source).toContain('/\\bas[\\s-]?is\\b.*\\bno\\s+warrant|\\bno\\s+warrant.*\\bas[\\s-]?is\\b/i');
  });

  test('source policy rejects backend condition-trust phrases from detail text', () => {
    expect(source).toContain('/\\bsold\\s+as\\s+is\\b.*\\bno\\s+(?:guarantees?|warrant(?:y|ies))/i');
    expect(source).toContain('/\\bno\\s+(?:guarantees?|warrant(?:y|ies))\\b.*\\bsold\\s+as\\s+is\\b/i');
    expect(source).toContain('/\\bneeds?\\s+jump\\s+(?:box|start)\\b/i');
    expect(source).toContain('/\\bwarning\\s+lights?\\s+on\\s+(?:the\\s+)?dash\\b/i');
    expect(source).toContain('/\\binvolved\\s+in\\s+(?:a\\s+)?motor\\s+vehicle\\s+accident\\b/i');
  });

  test('uses actual published row count for webhook itemCount', () => {
    expect(source).toContain('let totalPushed = 0;');
    expect(source).toContain('const datasetItemCount = totalPushed + 1;');
    expect(source).toContain('itemCount: datasetItemCount');
    expect(source).not.toContain('itemCount: totalAfterFilters');
  });

  test('emits a source-quality proof record even when no opportunities are pushed', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain("source: 'publicsurplus'");
    expect(source).toContain('found_rows_total: totalFound');
    expect(source).toContain('prefilter_passed_rows_total: totalAfterFilters');
    expect(source).toContain('pushed_rows_total: totalPushed');
    expect(source).toContain('pushed_rows_with_description: totalPushedWithDescription');
    expect(source).toContain('pushed_rows_with_detail_text: totalPushedWithDetailText');
    expect(source.indexOf("record_type: 'source_quality_proof'"))
      .toBeLessThan(source.indexOf('if (webhookUrl && datasetItemCount > 0)'));
  });

  test('source-quality proof explains post-detail rejection outcomes', () => {
    expect(source).toContain('const rejectionReasons = {};');
    expect(source).toContain("incrementRejectionReason('age_or_mileage_exceeded')");
    expect(source).toContain("incrementRejectionReason('condition_reject_after_detail')");
    expect(source).toContain("incrementRejectionReason('missing_detail_evidence_after_enrichment')");
    expect(source).toContain('enriched_rows_accepted: enrichedRowsAccepted');
    expect(source).toContain('enriched_rows_rejected: enrichedRowsRejected');
    expect(source).toContain('detail_pages_fetched: detailPagesFetched');
    expect(source).toContain('detail_pages_failed: detailPagesFailed');
    expect(source).toContain('detail_vins_found: detailVinsFound');
    expect(source).toContain('detail_mileages_found: detailMileagesFound');
    expect(source).toContain('rejection_reasons: rejectionReasons');
  });

  test('source-quality proof accounts for every prefilter discard class', () => {
    expect(source).toContain('let rowsExcludedMissingTitle = 0;');
    expect(source).toContain('let rowsExcludedConditionPrefilter = 0;');
    expect(source).toContain('let rowsExcludedNonVehicle = 0;');
    expect(source).toContain('let rowsExcludedRustState = 0;');
    expect(source).toContain('let rowsExcludedNonTargetState = 0;');
    expect(source).toContain('let rowsExcludedBidRange = 0;');
    expect(source).toContain('let rowsExcludedAgeMileagePrefilter = 0;');
    expect(source).toContain('let rowsExcludedDuplicate = 0;');
    expect(source).toContain('const accountedRows = totalAfterFilters');
    expect(source).toContain('+ rowsExcludedMissingTitle');
    expect(source).toContain('+ rowsExcludedConditionPrefilter');
    expect(source).toContain('+ rowsExcludedNonVehicle');
    expect(source).toContain('+ rowsExcludedRustState');
    expect(source).toContain('+ rowsExcludedNonTargetState');
    expect(source).toContain('+ rowsExcludedBidRange');
    expect(source).toContain('+ rowsExcludedAgeMileagePrefilter');
    expect(source).toContain('+ rowsExcludedDuplicate');
    expect(source).toContain('rows_excluded_unaccounted_after_prefilter: Math.max(0, totalFound - accountedRows)');
    expect(source).toContain('rows_excluded_missing_required_data: rowsExcludedMissingTitle');
    expect(source).toContain('rows_excluded_non_vehicle: rowsExcludedNonVehicle');
    expect(source).toContain('rows_excluded_policy_prefilter: rowsExcludedConditionPrefilter');
    expect(source).toContain('rows_excluded_rust_state: rowsExcludedRustState');
    expect(source).toContain('rows_excluded_out_of_scope: rowsExcludedNonTargetState');
    expect(source).toContain('rows_excluded_bid_range: rowsExcludedBidRange');
    expect(source).toContain('rows_excluded_age_mileage_prefilter: rowsExcludedAgeMileagePrefilter');
    expect(source).toContain('rows_excluded_duplicate: rowsExcludedDuplicate');
  });
});
