# Pricing External Comp Provenance - 2020 Dodge Durango SRT

Generated: 2026-06-02 02:35 PDT

## Status

`hypothesis` for external retail comp evidence. Do not insert a `market_prices`
row from this report alone.

## Live DealerScope Candidate

- Opportunity id: `1bf97906-38c4-439c-9519-c5c246a6e2b9`
- Source: GovDeals
- Title: `2020 Dodge Durango SRT`
- State: MS
- VIN: `1C4SDJGJ6LC324462`
- Mileage: 13,983
- Current bid: 10,600.00
- Expected close: 16,162.13
- Retail proxy estimate: 40,500.00
- DOS: 86.9
- Grade: Platinum
- Pricing state: `pricing_maturity=proxy`, `pricing_source=model:durango`

Live internal coverage report:

- `market=0/0`
- `dealer_sales=0/0`
- `history=0/1`
- `evidence=blocked_no_internal_comp_evidence`

## External Signals Checked

These sources indicate an active public retail market for 2020 Dodge Durango SRT
vehicles, but they are not yet governed DealerScope evidence.

- CarGurus nationwide 2020 Dodge Durango SRT AWD results:
  `https://www.cargurus.com/Cars/l-Used-2020-Dodge-Durango-SRT-AWD-t87520`
  - Page showed 2020 SRT AWD listings including 40,992 miles at 41,984; 52,817
    miles at 46,079; 46,598 miles at 47,998; and 16,988 miles at 55,171.
- CARFAX 2020 Dodge Durango SRT results:
  `https://www.carfax.com/Used-2020-Dodge-Durango-SRT_x46652`
  - Page showed 107 listings and examples including 34,718 miles at 45,250,
    61,421 miles at 41,536, and 92,218 miles at 37,348.
- Cars.com 2020 Dodge Durango SRT results:
  `https://www.cars.com/shopping/dodge-durango-2020-srt/`
  - Page reported a nationwide average price of 42,963 and pricing starting at
    34,995 for 2020 Durango SRT.

## Classification

This is not safe to seed into `public.market_prices` as-is because:

- Sources are external retail asking/listing surfaces, not DealerScope closed
  outcomes.
- The current GovDeals unit has much lower mileage than most cited listings.
- Active listing prices can be stale, duplicated across marketplaces, or affected
  by dealer fees, title history, location, and options.
- The current `market_prices` seed script intentionally accepts only existing
  internal market-comp/dealer-sales-history evidence.

## Required Guardrail Before Any Insert

Before this Durango can become a governed external comp seed, DealerScope needs
an explicit external-comp ingestion path that stores:

- source URL for every comp used
- captured timestamp
- price, mileage, VIN/listing id when available
- title/trim/drivetrain normalization
- title-history caveats such as branded, salvage, accident, or damage
- duplicate detection across marketplaces
- confidence notes explaining active-listing vs closed-sale evidence

Until that exists, the correct live classification remains
`blocked_no_internal_comp_evidence`.
