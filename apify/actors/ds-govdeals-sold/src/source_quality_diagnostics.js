import { lotSearchText } from './target_scope.js';

const DECISION_KEYS = [
    'found',
    'passed',
    'out_of_scope',
    'not_completed_sale',
    'future_sale_date',
    'missing_sale_date',
    'unparseable_sale_date',
];

function emptyCounts() {
    return Object.fromEntries(DECISION_KEYS.map(key => [key, 0]));
}

export function sanitizedOutOfScopeExample(lot) {
    return {
        asset_id_present: Boolean(lot?.assetId),
        keys_present: Object.keys(lot || {}).sort().slice(0, 20),
        search_text_excerpt: lotSearchText(lot).slice(0, 180),
    };
}

export function createQueryDiagnostics(queries = []) {
    const query_counts = {};
    for (const query of queries) {
        query_counts[String(query || '').trim() || '(blank)'] = emptyCounts();
    }
    return {
        query_counts,
        out_of_scope_examples: [],
        out_of_scope_examples_by_query: {},
    };
}

function countsFor(diagnostics, searchText) {
    const key = String(searchText || '').trim() || '(unknown)';
    if (!diagnostics.query_counts[key]) diagnostics.query_counts[key] = emptyCounts();
    return diagnostics.query_counts[key];
}

export function recordLotDecision(diagnostics, searchText, decision, lot = null) {
    const counts = countsFor(diagnostics, searchText);
    counts.found++;

    if (decision === 'passed') {
        counts.passed++;
        return;
    }

    if (decision === 'out_of_scope') {
        counts.out_of_scope++;
        const key = String(searchText || '').trim() || '(unknown)';
        if (!diagnostics.out_of_scope_examples_by_query[key]) {
            diagnostics.out_of_scope_examples_by_query[key] = [];
        }
        if (diagnostics.out_of_scope_examples_by_query[key].length < 3) {
            diagnostics.out_of_scope_examples_by_query[key].push(sanitizedOutOfScopeExample(lot));
        }
        if (diagnostics.out_of_scope_examples.length < 8) {
            diagnostics.out_of_scope_examples.push({
                search_text: key,
                ...sanitizedOutOfScopeExample(lot),
            });
        }
        return;
    }

    counts.not_completed_sale++;
    if (decision in counts) counts[decision]++;
}
