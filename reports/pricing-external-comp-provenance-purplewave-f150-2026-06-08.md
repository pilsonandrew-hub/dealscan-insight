# Purple Wave F-150 External Comp Provenance - 2026-06-08

Scope: proof-only market-comp enrichment for a public Purple Wave candidate. This report does not authorize alert delivery, live bidding, or relaxed DealerScope gates.

## Candidate

- Source: Purple Wave
- Item: `EC8354`
- URL: `https://www.purplewave.com/auction/260623/item/EC8354`
- Vehicle: 2018 Ford F150 Ext. Cab pickup truck
- VIN: `1FTEX1CB9JKE95602`
- Mileage: 71,023
- State: CA
- Current bid observed in public Purple Wave JSON: $300

## Evidence Boundary

Public TrueCar search results for used 2018 Ford F-150 listings in California showed multiple comparable SuperCab/SuperCrew retail listings. The selected comps are active retail listing evidence, not closed-sale evidence, and must retain that caveat if used for a governed `market_prices` seed.

Source used:

- `https://www.truecar.com/used-cars-for-sale/listings/ford/f-150/year-2018/location-san-diego-ca/`

Selected proof comps:

| Title | Price | Mileage | Evidence ID |
|---|---:|---:|---|
| 2018 Ford F-150 XLT SuperCab 6.5' Box 2WD | $22,684 | 85,238 | truecar-2018-f150-xlt-supercab-85238 |
| 2018 Ford F-150 XL SuperCab 6.5' Box 2WD | $22,900 | 69,255 | truecar-2018-f150-xl-supercab-69255 |
| 2018 Ford F-150 XL SuperCab 6.5' Box 2WD | $29,998 | 25,153 | truecar-2018-f150-xl-supercab-25153 |

Proof-only aggregate:

- Average: $25,194
- Low: $22,684
- High: $29,998
- Sample size: 3

## DealerScope Proof Result

When scored locally with these proof comps only, the candidate produced:

- Pricing maturity: `market_comp`
- DOS: 86.3
- Investment grade: Platinum
- Ceiling pass: true
- MMR estimate used by scorer: $18,662.22
- Gross margin: $17,147.22
- Max bid: $14,714.78
- Bid headroom: $14,414.78
- Expected close bid: $5,770.41

The proof metrics above come from one deterministic `score_deal` invocation using
the $25,194 retail-comp average, $300 current bid, 3 comps, 0.75 comp confidence,
and the scorer's existing conservative retail-to-wholesale conversion.

Truth label: **locally validated only** as an enriched proof candidate. Not live-confirmed accepted yield until the source row is ingested through a governed actor/proof path and the comp evidence is inserted only through the governed external market comp workflow.
