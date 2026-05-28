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
    expect(source).toContain('if (listing.mileage && listing.mileage > maxMileage)');
    expect(source).toContain('await Actor.pushData(listing)');
  });
});
