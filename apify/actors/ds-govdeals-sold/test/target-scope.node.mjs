import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
    matchesTargetTerms,
    normalizeTargetSearchQueries,
    normalizeTargetTerms,
} from '../src/target_scope.js';
import {
    completedSaleDate,
    hasCompletedSaleEvidence,
} from '../src/sold_date_contract.js';
import {
    createQueryDiagnostics,
    recordLotDecision,
    sanitizedOutOfScopeExample,
} from '../src/source_quality_diagnostics.js';

describe('GovDeals sold target scope', () => {
    test('matches approved DealerScope comp models with common separators', () => {
        assert.equal(matchesTargetTerms({ title: '2019 Ford F-150 XL pickup' }), true);
        assert.equal(matchesTargetTerms({ title: '2020 Ford F150 crew cab' }), true);
        assert.equal(matchesTargetTerms({ title: '2018 Chevrolet Silverado 1500' }), true);
        assert.equal(matchesTargetTerms({ title: '2021 Ram 2500 Tradesman' }), true);
    });

    test('rejects substring false positives and longer non-approved models', () => {
        assert.equal(matchesTargetTerms({ title: 'Fleet Management Program 1500 units' }), false);
        assert.equal(matchesTargetTerms({ title: 'Ford F-1500 concept vehicle' }), false);
        assert.equal(matchesTargetTerms({ title: 'Chevrolet Silverado 1500HD utility truck' }), false);
    });

    test('allows bounded diagnostic overrides', () => {
        const terms = normalizeTargetTerms(['civic']);

        assert.equal(matchesTargetTerms({ title: '2018 Honda Civic' }, terms), true);
        assert.equal(matchesTargetTerms({ title: '2018 Ford F-150' }, terms), false);
    });

    test('uses custom target terms as search queries when no explicit search override is provided', () => {
        assert.deepEqual(
            normalizeTargetSearchQueries({ targetTerms: ['tacoma', 'camry'] }),
            ['tacoma', 'camry'],
        );
        assert.deepEqual(
            normalizeTargetSearchQueries({
                searchQuery: 'f-150',
                targetTerms: ['tacoma'],
            }),
            ['f-150'],
        );
        assert.deepEqual(
            normalizeTargetSearchQueries({
                targetSearchQueries: ['silverado 2500'],
                targetTerms: ['tacoma'],
            }),
            ['silverado 2500'],
        );
        assert.deepEqual(
            normalizeTargetSearchQueries({
                targetSearchQueries: ['Ford F-150', ' Silverado 1500 ', 'Ram 2500'],
                maxSearchQueries: 2,
            }),
            ['Ford F-150', 'Silverado 1500'],
        );
    });

    test('accepts only parseable non-future completed sale dates', () => {
        const now = new Date('2026-06-04T11:05:00.000Z');

        assert.equal(
            hasCompletedSaleEvidence({ auction_end_time: '2026-06-01T15:00:00Z' }, now),
            true,
        );
        assert.equal(
            completedSaleDate({ auction_end_time: '2026-06-01T15:00:00Z' }, now),
            '2026-06-01T15:00:00.000Z',
        );
        assert.equal(
            hasCompletedSaleEvidence({ auction_end_time: '2026-06-05T15:00:00Z' }, now),
            false,
        );
        assert.equal(
            hasCompletedSaleEvidence({ auction_end_time: 'not-a-date' }, now),
            false,
        );
        assert.equal(
            hasCompletedSaleEvidence({ title: '2019 Ford F-150' }, now),
            false,
        );
    });

    test('records sanitized per-query diagnostics without raw URLs or VINs', () => {
        const diagnostics = createQueryDiagnostics(['f-150']);
        const lot = {
            assetShortDescription: 'Industrial generator trailer',
            makebrand: 'Ford',
            vin: '1FTFW1E50PFA00000',
            url: 'https://example.invalid/private-listing',
            assetId: '12345',
        };

        recordLotDecision(diagnostics, 'f-150', 'out_of_scope', lot);
        recordLotDecision(diagnostics, 'f-150', 'future_sale_date', lot);

        assert.deepEqual(diagnostics.query_counts['f-150'], {
            found: 2,
            passed: 0,
            out_of_scope: 1,
            not_completed_sale: 1,
            future_sale_date: 1,
            missing_sale_date: 0,
            unparseable_sale_date: 0,
        });
        assert.deepEqual(sanitizedOutOfScopeExample(lot), {
            asset_id_present: true,
            keys_present: ['assetId', 'assetShortDescription', 'makebrand', 'url', 'vin'],
            search_text_excerpt: 'industrial generator trailer ford',
        });
        assert.equal(JSON.stringify(diagnostics).includes('example.invalid'), false);
        assert.equal(JSON.stringify(diagnostics).includes('1FTFW1E50PFA00000'), false);
    });

    test('keeps out-of-scope examples bucketed by query', () => {
        const diagnostics = createQueryDiagnostics(['intercepted', 'f-150']);

        for (let index = 0; index < 5; index++) {
            recordLotDecision(diagnostics, 'intercepted', 'out_of_scope', {
                assetId: `intercepted-${index}`,
                assetShortDescription: `Intercepted non-target ${index}`,
            });
        }
        recordLotDecision(diagnostics, 'f-150', 'out_of_scope', {
            assetId: 'query-row',
            assetShortDescription: 'Direct query non-target row',
        });

        assert.equal(diagnostics.out_of_scope_examples.length, 6);
        assert.equal(diagnostics.out_of_scope_examples_by_query.intercepted.length, 3);
        assert.equal(diagnostics.out_of_scope_examples_by_query['f-150'].length, 1);
        assert.equal(
            diagnostics.out_of_scope_examples_by_query['f-150'][0].search_text_excerpt,
            'direct query non-target row',
        );
    });
});
