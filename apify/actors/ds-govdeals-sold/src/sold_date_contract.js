export const SOLD_DATE_FIELDS = [
    'sale_date',
    'auction_end_time',
    'auction_end_date',
    'auctionEndUtc',
    'assetAuctionEndDateUtc',
    'auctionEnd',
];

function parseDate(value) {
    if (value === null || value === undefined || value === '') return null;
    const parsed = new Date(String(value));
    return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function completedSaleDate(lot, now = new Date()) {
    for (const field of SOLD_DATE_FIELDS) {
        const parsed = parseDate(lot?.[field]);
        if (parsed && parsed <= now) return parsed.toISOString();
    }
    return null;
}

export function completedSaleRejectionReason(lot, now = new Date()) {
    let sawFutureDate = false;
    let sawUnparseableDate = false;

    for (const field of SOLD_DATE_FIELDS) {
        const value = lot?.[field];
        if (value === null || value === undefined || value === '') continue;
        const parsed = parseDate(value);
        if (!parsed) {
            sawUnparseableDate = true;
            continue;
        }
        if (parsed <= now) return null;
        sawFutureDate = true;
    }

    if (sawFutureDate) return 'future_sale_date';
    if (sawUnparseableDate) return 'unparseable_sale_date';
    return 'missing_sale_date';
}

export function hasCompletedSaleEvidence(lot, now = new Date()) {
    return completedSaleDate(lot, now) !== null;
}
