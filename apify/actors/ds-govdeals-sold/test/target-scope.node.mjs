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
});
