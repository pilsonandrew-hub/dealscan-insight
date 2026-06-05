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

  test('re-applies mileage cap after detail-page enrichment before publishing', () => {
    expect(source).toContain('const MAX_ALLOWED_MILEAGE = 50000;');
    expect(detailHandler).toContain('if (vehicle.mileage !== null && vehicle.mileage > MAX_ALLOWED_MILEAGE)');
    expect(detailHandler).toContain('return;');
    expect(detailHandler.indexOf('if (vehicle.mileage !== null && vehicle.mileage > MAX_ALLOWED_MILEAGE)'))
      .toBeLessThan(detailHandler.indexOf('await pushVehicle(vehicle);'));
  });

  test('mirrors backend max-age gate before publishing standard and Texas rows', () => {
    expect(source).toContain('const MAX_ALLOWED_AGE_YEARS = 4;');
    expect(source).toContain('age > MAX_ALLOWED_AGE_YEARS');
    expect(source.match(/age > MAX_ALLOWED_AGE_YEARS/g)).toHaveLength(2);
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
    expect(source).toContain("incrementRejectionReason('mileage_over_50k')");
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
});
