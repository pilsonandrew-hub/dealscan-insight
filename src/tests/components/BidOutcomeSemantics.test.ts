import { describe, it, expect } from 'vitest';

type BidOutcomePayload = {
  bid: boolean;
  won?: boolean;
  purchase_price?: number;
};

type BidOutcomeNormalized = {
  bid: boolean;
  outcome: 'won' | 'lost' | 'passed' | 'pending';
  purchase_price: number | null;
  bid_amount: number | null;
};

function normalizeBidOutcome(payload: BidOutcomePayload, currentBid?: number | null): BidOutcomeNormalized {
  if (payload.won && !payload.bid) {
    throw new Error('Cannot mark won=true when bid=false');
  }

  if (payload.purchase_price != null && !payload.won) {
    throw new Error('purchase_price is only valid when won=true');
  }

  if (!payload.bid) {
    return {
      bid: false,
      outcome: 'passed',
      purchase_price: null,
      bid_amount: null,
    };
  }

  return {
    bid: true,
    outcome: payload.won ? 'won' : 'lost',
    purchase_price: payload.won ? payload.purchase_price ?? null : null,
    bid_amount: currentBid != null ? currentBid : null,
  };
}

function countBidOutcomeEvidence(outcomeNotes: unknown): number {
  if (!outcomeNotes || typeof outcomeNotes !== 'object') return 0;
  const record = outcomeNotes as Record<string, unknown>;
  return record.type === 'bid_outcome' ? 1 : 0;
}

describe('bid outcome semantics', () => {
  it('normalizes non-bids to passed without fake bid economics', () => {
    expect(normalizeBidOutcome({ bid: false, won: false }, 10000)).toEqual({
      bid: false,
      outcome: 'passed',
      purchase_price: null,
      bid_amount: null,
    });
  });

  it('rejects impossible won-without-bid combinations', () => {
    expect(() => normalizeBidOutcome({ bid: false, won: true }, 10000)).toThrow(
      'Cannot mark won=true when bid=false'
    );
  });

  it('rejects purchase price when the bid was not won', () => {
    expect(() => normalizeBidOutcome({ bid: true, won: false, purchase_price: 9000 }, 10000)).toThrow(
      'purchase_price is only valid when won=true'
    );
  });

  it('normalizes lost bids to lost with current bid captured as bid amount', () => {
    expect(normalizeBidOutcome({ bid: true, won: false }, 10500)).toEqual({
      bid: true,
      outcome: 'lost',
      purchase_price: null,
      bid_amount: 10500,
    });
  });

  it('normalizes winning bids to won with purchase price retained separately', () => {
    expect(normalizeBidOutcome({ bid: true, won: true, purchase_price: 9800 }, 10250)).toEqual({
      bid: true,
      outcome: 'won',
      purchase_price: 9800,
      bid_amount: 10250,
    });
  });

  it('counts only explicit bid_outcome notes as bid evidence', () => {
    expect(countBidOutcomeEvidence({ type: 'manual_outcome', outcome: 'won', sold_price: 13000 })).toBe(0);
    expect(countBidOutcomeEvidence({ bid: true, won: true, purchase_price: 12000 })).toBe(0);
    expect(countBidOutcomeEvidence({ type: 'bid_outcome', outcome: 'lost', bid_amount: 9500 })).toBe(1);
  });
});
