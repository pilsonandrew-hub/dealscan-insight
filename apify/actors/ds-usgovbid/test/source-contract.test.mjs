import { describe, expect, test } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(__dirname, '../src/main.js'), 'utf8');

describe('ds-usgovbid source contract', () => {
  test('emits source-quality proof before every actor exit path', () => {
    expect(source).toContain("record_type: 'source_quality_proof'");
    expect(source).toContain("source: 'usgovbid'");
    expect(source).toContain('found_rows_total: totalFound');
    expect(source).toContain('pushed_rows_total: totalPassed');
    expect(source).toContain('auctions_discovered: auctionsDiscovered');
    expect(source).toContain('bid_urls_resolved: bidUrlsResolved');
    expect(source).toContain('rows_excluded_search_filter');
    expect(source).toContain('rows_excluded_non_vehicle');
    expect(source).toContain('rows_excluded_age_mileage_prefilter');
    expect(source).toContain('rows_excluded_bid_range');
    expect(source).toContain('rows_excluded_rust_state');

    const proofCalls = source.match(/await pushSourceQualityProof\(\);/g) || [];
    const exitCalls = source.match(/await Actor\.exit\(\);/g) || [];
    expect(proofCalls.length).toBe(exitCalls.length);

    for (const exitIndex of [...source.matchAll(/await Actor\.exit\(\);/g)].map(match => match.index)) {
      const priorProofIndex = source.lastIndexOf('await pushSourceQualityProof();', exitIndex);
      expect(priorProofIndex).toBeGreaterThan(-1);
    }
  });
});
