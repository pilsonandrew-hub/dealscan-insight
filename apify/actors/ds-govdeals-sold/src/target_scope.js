export const DEFAULT_TARGET_TERMS = [
    'f-150',
    'f150',
    'f 150',
    'f-250',
    'f250',
    'f 250',
    'silverado 1500',
    'silverado 2500',
    'ram 1500',
    'ram 2500',
];

function escapeRegex(value) {
    return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function normalizeTargetTerms(terms) {
    return (Array.isArray(terms) && terms.length > 0 ? terms : DEFAULT_TARGET_TERMS)
        .map(term => String(term).trim().toLowerCase())
        .filter(Boolean);
}

export function normalizeTargetSearchQueries({
    searchQuery = '',
    targetSearchQueries = null,
    targetTerms = null,
    maxSearchQueries = null,
} = {}) {
    const explicitSearchQuery = String(searchQuery || '').trim();
    const sourceQueries = explicitSearchQuery
        ? [explicitSearchQuery]
        : (Array.isArray(targetSearchQueries) && targetSearchQueries.length > 0
            ? targetSearchQueries
            : (Array.isArray(targetTerms) && targetTerms.length > 0 ? targetTerms : DEFAULT_TARGET_TERMS));
    const seen = new Set();
    const normalized = sourceQueries
        .map(term => String(term).trim())
        .filter(Boolean)
        .filter((term) => {
            const key = term.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    const limit = Number(maxSearchQueries);
    return Number.isFinite(limit) && limit > 0 ? normalized.slice(0, limit) : normalized;
}

function termPattern(term) {
    const pattern = escapeRegex(term).replace(/[-\s]+/g, '[\\s-]?');
    return new RegExp(`\\b${pattern}\\b`, 'i');
}

export function lotSearchText(lot) {
    return [
        lot.assetShortDescription,
        lot.title,
        lot.makebrand,
        lot.make,
        lot.model,
        lot.assetLongDescription,
        lot.longDescription,
        lot.itemDescription,
        lot.description,
        lot.notes,
        lot.itemNotes,
    ].filter(Boolean).join(' ').toLowerCase();
}

export function matchesTargetTerms(lot, terms = DEFAULT_TARGET_TERMS) {
    const text = lotSearchText(lot);
    return normalizeTargetTerms(terms).some(term => termPattern(term).test(text));
}
