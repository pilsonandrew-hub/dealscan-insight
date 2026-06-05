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

  test('does not expand pagination beyond the caller maxPages cap', () => {
    expect(source).not.toContain('Math.max(totalPages, Math.ceil(totalCount / pageSize))');
    expect(source).toMatch(/Math\.min\(\s*totalPages,\s*Math\.ceil\(totalCount \/ pageSize\),\s*HARD_MAX_PAGES,\s*\)/);
  });

  test('keeps detail enrichment budget aligned to observed page fetch cost', () => {
    expect(source).not.toContain('const DETAIL_PAGE_REQUIRED_MS = 45000;');
    expect(source).toContain('const DETAIL_PAGE_REQUIRED_MS = 12000;');
    expect(source).toContain('const DETAIL_PAGE_TIMEOUT_MS = 12000;');
  });

  test('normalizes intercepted lot ids before pagination dedupe', () => {
    expect(source).not.toContain('seenIds.add(lot.assetId);');
    expect(source).toContain("const lotId = String(lot.assetId ?? lot.id ?? '');");
    expect(source).toContain('if (lotId) seenIds.add(lotId);');
  });

  test('sets detail capacity and request timeout high enough for bounded proof runs', () => {
    expect(source).not.toContain('const MAX_DETAIL_PAGES = 30;');
    expect(source).toContain('const MAX_DETAIL_PAGES = 60;');
    expect(source).toContain('requestHandlerTimeoutSecs: 600');
  });

  test('rejects non-dealer-target vehicle-family lots before detail enrichment', () => {
    expect(source).toContain('NON_DEALER_TARGET_PATTERNS');
    expect(source).toContain('NON_DEALER_TARGET_PATTERNS.some((pattern) => pattern.test(conditionText))');
    expect(source).toContain('/\\btravel\\s+trailer\\b/i');
    expect(source).toContain('/\\btrail\\s+runner\\b/i');
    expect(source).toContain('/\\blot\\s+of\\b/i');
    expect(source).toContain('/\\b(?:jail|prisoner)\\s+(?:van|transport)\\b/i');
  });

  test('rejects backend-policy condition phrases before pushing rows', () => {
    expect(source).toContain('/\\bas[\\s-]+is\\b/i');
    expect(source).toContain('/\\bno\\s+warranty\\b/i');
    expect(source).toContain('/\\brebuilt\\b/i');
  });

  test('reruns source-policy rejects after detail enrichment before pushing rows', () => {
    expect(source).toContain('item.detail_text');
    expect(source).toContain('const pushableLots = passingLots.filter(lot => Boolean(lot.vin) && Boolean(lot.mileage) && passes(lot));');
    expect(source).toContain('const postPolicyRejectedLots = passingLots.filter(lot => Boolean(lot.vin) && Boolean(lot.mileage) && !passes(lot));');
    expect(source).toContain('rows_excluded_policy_after_detail');
  });

  test('rejects commercial-heavy vehicle families before pushing rows', () => {
    expect(source).toContain('/\\bsprinter\\b/i');
    expect(source).toContain('/\\btransit\\b/i');
    expect(source).toContain('/\\bbrightdrop\\b/i');
    expect(source).toContain('/\\bzevo\\b/i');
    expect(source).toContain('/\\bcargo\\s+delivery\\s+van\\b/i');
    expect(source).toContain('/\\bpeterbilt\\b/i');
    expect(source).toContain('/\\bfreightliner\\b/i');
    expect(source).toContain('/\\binternational\\b/i');
    expect(source).toContain('/\\b(?:box|dump|bucket|utility)\\s+truck\\b/i');
  });

  test('keeps detail-enriched rows missing required data out of pushed opportunities', () => {
    expect(source).toContain('const pushableLots = passingLots.filter(lot => Boolean(lot.vin) && Boolean(lot.mileage) && passes(lot));');
    expect(source).toContain('const incompleteLots = passingLots.filter(lot => !lot.vin || !lot.mileage);');
    expect(source).toContain('rows_excluded_missing_required_data');
    expect(source).toContain('rows_excluded_missing_vin');
    expect(source).toContain('rows_excluded_missing_mileage');
    expect(source).toContain('for (const lot of pushableLots)');
    expect(source).toContain('await pushSourceQualityProof(log, pushableLots)');
  });

  test('separates attempted detail misses from unattempted capacity exclusions', () => {
    expect(source).toContain('detail_attempted_urls: new Set()');
    expect(source).toContain('sourceQualityStats.detail_attempted_urls.add(lot.listing_url)');
    expect(source).toContain('const excludedAfterDetailAttempt = incompleteLots.filter(lot => sourceQualityStats.detail_attempted_urls.has(lot.listing_url));');
    expect(source).toContain('const excludedWithoutDetailAttempt = incompleteLots.filter(lot => !sourceQualityStats.detail_attempted_urls.has(lot.listing_url));');
    expect(source).toContain('rows_excluded_after_detail_attempt');
    expect(source).toContain('rows_excluded_without_detail_attempt');
  });

  test('counts only actually attempted detail pages when runtime budget stops enrichment', () => {
    expect(source).not.toContain('sourceQualityStats.detail_pages_attempted += toScrape.length;');
    expect(source).toContain('let detailAttempts = 0;');
    expect(source).toContain('sourceQualityStats.detail_pages_attempted++;');
    expect(source).toContain('detailAttempts++;');
    expect(source).toContain('Complete: attempted ${detailAttempts} of ${toScrape.length} planned pages');
  });

  test('samples attempted and unattempted exclusion rows for cap diagnosis', () => {
    expect(source).toContain('function sampleExcludedLots(lots, limit = 10)');
    expect(source).toContain('excluded_after_detail_attempt_samples: []');
    expect(source).toContain('excluded_without_detail_attempt_samples: []');
    expect(source).toContain('sourceQualityStats.excluded_after_detail_attempt_samples = sampleExcludedLots(excludedAfterDetailAttempt);');
    expect(source).toContain('sourceQualityStats.excluded_without_detail_attempt_samples = sampleExcludedLots(excludedWithoutDetailAttempt);');
    expect(source).toContain('excluded_after_detail_attempt_samples: sourceQualityStats.excluded_after_detail_attempt_samples');
    expect(source).toContain('excluded_without_detail_attempt_samples: sourceQualityStats.excluded_without_detail_attempt_samples');
    expect(source).toContain('missing_vin: !lot.vin');
    expect(source).toContain('missing_mileage: !lot.mileage');
  });

  test('accounts for prefilter-passed rows that are not otherwise explained', () => {
    expect(source).toContain('rows_excluded_unaccounted_after_prefilter: 0');
    expect(source).toContain('const accountedRows = (');
    expect(source).toContain('sourceQualityStats.rows_excluded_unaccounted_after_prefilter = Math.max(0, totalPassed - accountedRows);');
    expect(source).toContain('rows_excluded_unaccounted_after_prefilter: sourceQualityStats.rows_excluded_unaccounted_after_prefilter');
  });

  test('adds sanitized detail diagnostics to attempted exclusion samples', () => {
    expect(source).toContain('function extractDetailDiagnostics(bodyText, metadata = {})');
    expect(source).toContain('lot.detail_diagnostics = extractDetailDiagnostics(bodyText, {');
    expect(source).toContain('detail_diagnostics: lot.detail_diagnostics || null');
    expect(source).toContain('vin_candidates');
    expect(source).toContain('mileage_candidates');
    expect(source).toContain('field_snippets');
    expect(source).toContain('body_text_length');
    expect(source).toContain('page_title');
    expect(source).toContain('current_url');
    expect(source).toContain('no_field_text_sample');
  });

  test('extracts mileage from normalized GovDeals odometer detail text', () => {
    expect(source).toContain('function extractMileageFromText(bodyText)');
    expect(source).toContain('const mileage = extractMileageFromText(bodyText) ?? extractMileageFromDiagnostics(lot.detail_diagnostics);');
    expect(source).toContain("String(bodyText || '').replace(/\\s+/g, ' ').trim()");
    expect(source).toContain('/\\bOdometer\\s+(?:reads\\s+)?([\\d,]+)\\s*(?:miles?|mi\\b)?/i');
  });

  test('falls back to detail diagnostics when raw body mileage parsing misses', () => {
    expect(source).toContain('function extractMileageFromDiagnostics(detailDiagnostics)');
    expect(source).toContain('extractMileageFromText(bodyText) ?? extractMileageFromDiagnostics(lot.detail_diagnostics)');
    expect(source).toContain('detailDiagnostics.mileage_candidates');
    expect(source).toContain('detailDiagnostics.field_snippets');
  });

  test('preserves condition source text on pushed GovDeals opportunity rows', () => {
    expect(source).toContain('function buildDescriptionFromLot(lot)');
    expect(source).toContain('description:   buildDescriptionFromLot(lot)');
    expect(source).toContain('function descriptionNeedsDetailEvidence(lot)');
    expect(source).toContain('function missingIdentityDetail(lot)');
    expect(source).toContain('function detailEnrichmentPriority(lot)');
    expect(source).toContain('.filter(l => l.listing_url && (missingIdentityDetail(l) || descriptionNeedsDetailEvidence(l)))');
    expect(source).toContain('.sort((a, b) => detailEnrichmentPriority(a) - detailEnrichmentPriority(b));');
    expect(source).toContain('lot.detail_text = extractDetailText(bodyText);');
    expect(source).toContain('if (lot.detail_text && descriptionNeedsDetailEvidence(lot)) lot.description = lot.detail_text;');
  });
});
