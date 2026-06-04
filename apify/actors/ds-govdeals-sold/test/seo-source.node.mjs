import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
    extractSeoAssetUrls,
    parseGovDealsSeoAsset,
    seoSearchUrl,
} from '../src/govdeals_seo.js';
import { hasCompletedSaleEvidence } from '../src/sold_date_contract.js';
import { matchesTargetTerms } from '../src/target_scope.js';

const SOLD_F150_HTML = `
<html>
  <head>
    <title>3052A/ 2014 Ford F-150 | GovDeals</title>
    <meta property="og:url" content="https://www.govdeals.com/en/asset/17167/7167">
    <script id="seoSchemaScript" type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "Vehicle",
        "name": "3052A/ 2014 Ford F-150",
        "image": "https://webassets.lqdt1.com/assets/photos/7167/7167_17167_main.jpg",
        "model": "F-150",
        "datePosted": "2026-05-08",
        "offers": {
          "@type": "Offer",
          "priceCurrency": "USD",
          "availability": "https://schema.org/SoldOut",
          "url": "https://www.govdeals.com/en/asset/17167/7167",
          "price": 3074
        },
        "seller": {
          "@type": "Organization",
          "name": "Miami-Dade County, FL",
          "address": {
            "@type": "PostalAddress",
            "addressLocality": "Doral",
            "addressRegion": "Florida"
          }
        },
        "vehicleModelDate": "2014",
        "vehicleIdentificationNumber": "1FTEX1CM9EFB48531",
        "mileageFromOdometer": {
          "@type": "QuantitativeValue",
          "value": 143553,
          "unitText": "Miles"
        },
        "subjectOf": {
          "@type": "Auction",
          "endDate": "2026-05-16T00:08:00Z",
          "organizer": {"@type": "Organization", "name": "Miami-Dade County, FL"}
        },
        "brand": {"@type": "Brand", "name": "Ford"}
      }
    </script>
  </head>
  <body>
    <p id="lblSoldAmount" data-value="3458.25">USD 3,458.25</p>
    <p id="lblTotalAmount" data-value="3700.33">USD 3,700.33</p>
  </body>
</html>`;

describe('GovDeals SEO sold source', () => {
    test('builds completed SEO search URLs with explicit keyword and timing', () => {
        assert.equal(
            seoSearchUrl('Ford F-150'),
            'https://prod-seo.govdeals.com/en/search?keyword=Ford%20F-150&timing=completed',
        );
    });

    test('extracts canonical asset URLs from SEO search HTML', () => {
        const urls = extractSeoAssetUrls(`
            <a href="/en/asset/17167/7167">2014 Ford F-150</a>
            <a href="https://prod-seo.govdeals.com/en/asset/1194/1244">2015 Ford F-250 SD</a>
            <a href="/en/asset/17167/7167">duplicate</a>
        `);

        assert.deepEqual(urls, [
            'https://prod-seo.govdeals.com/en/asset/17167/7167',
            'https://prod-seo.govdeals.com/en/asset/1194/1244',
        ]);
    });

    test('normalizes SoldOut vehicle JSON-LD into the existing lot contract', () => {
        const lot = parseGovDealsSeoAsset(SOLD_F150_HTML, 'https://prod-seo.govdeals.com/en/asset/17167/7167');

        assert.equal(lot.assetId, '17167');
        assert.equal(lot.accountId, '7167');
        assert.equal(lot.title, '3052A/ 2014 Ford F-150');
        assert.equal(lot.make, 'Ford');
        assert.equal(lot.model, 'F-150');
        assert.equal(lot.year, 2014);
        assert.equal(lot.sold_price, 3074);
        assert.equal(lot.sold_price_all_in, 3458.25);
        assert.equal(lot.total_price, 3700.33);
        assert.equal(lot.price_basis, 'all_in');
        assert.equal(lot.sale_date, '2026-05-16T00:08:00.000Z');
        assert.equal(lot.auction_end_time, '2026-05-16T00:08:00.000Z');
        assert.equal(lot.vin, '1FTEX1CM9EFB48531');
        assert.equal(lot.mileage, 143553);
        assert.equal(lot.city, 'Doral');
        assert.equal(lot.state, 'Florida');
        assert.equal(lot.seller, 'Miami-Dade County, FL');
        assert.equal(lot.source_site, 'govdeals-sold');
        assert.equal(matchesTargetTerms(lot), true);
        assert.equal(hasCompletedSaleEvidence(lot, new Date('2026-06-04T12:00:00Z')), true);
    });

    test('rejects SEO pages that do not prove a sold completed vehicle', () => {
        const activeHtml = SOLD_F150_HTML.replace('https://schema.org/SoldOut', 'https://schema.org/InStock');
        const missingVehicleHtml = SOLD_F150_HTML.replace('"@type": "Vehicle"', '"@type": "Product"');

        assert.equal(parseGovDealsSeoAsset(activeHtml, 'https://prod-seo.govdeals.com/en/asset/17167/7167'), null);
        assert.equal(parseGovDealsSeoAsset(missingVehicleHtml, 'https://prod-seo.govdeals.com/en/asset/17167/7167'), null);
    });
});
