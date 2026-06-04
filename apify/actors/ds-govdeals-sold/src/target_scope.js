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
