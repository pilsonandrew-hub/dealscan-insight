import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import {
    matchesTargetTerms,
    normalizeTargetTerms,
} from '../src/target_scope.js';

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
});
