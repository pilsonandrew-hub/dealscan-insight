# Pricing External Comp Provenance - 2025 Ford Explorer Active

Generated: 2026-06-05 05:30 PDT

## Status

`locally validated only` until the guarded external-market-comp workflow inserts the
seed row and live pricing/source-yield proofs rerun from main.

## Live DealerScope Candidate

- Source: GovDeals
- Source run: `bGi42l0UTI6JOu32S`
- Title: `2025 Ford Explorer Active AWD Low Miles!`
- State: NJ
- VIN: `1FMUK8DH5SGA77978`
- Mileage: 1,435
- Current bid: 31,000.00
- Proxy MMR: 22,000.00
- Latest margin proof: `margin_below_floor | margin=$-13300 floor=$1500 tier=premium bid=$31000 mmr=$22000 cost=$35300 max_bid=$0 headroom=$0 pricing=proxy`
- GovDeals URL: `https://www.govdeals.com/asset/183/27535`

Live pricing-coverage proof:

- Workflow: `27014869522`
- Evidence: `blocked_no_internal_comp_evidence`
- Internal market coverage: `market=0/0`
- Dealer-sales coverage: `dealer_sales=0/0`
- Internal history coverage: `history=0/0`

## External Signals Checked

These are active retail-listing signals for 2025 Ford Explorer Active vehicles.
They are not closed-sale outcomes, and the seed row must retain that caveat.

- Jack Schmitt Ford listing:
  `https://jackschmittford.com/inventory/Used-2025-Ford-Explorer-Active-1FMUK8DH2SGD07301`
  - Price: 42,689
  - Mileage: 2,774
  - VIN: `1FMUK8DH2SGD07301`
  - Stock: `SP2800`
- Cooper Auto Group listing:
  `https://cooperautogroup.com/inventory/Used-2025-Ford-Explorer-Active-1FMUK8DH6SGB57130-231`
  - Price: 40,898
  - Mileage: 2,730
  - VIN: `1FMUK8DH6SGB57130`
  - Stock: `MMS57130`
- Power of Bowser listing:
  `https://www.powerofbowser.com/inventory/Used-2025-Ford-Explorer-Active-1FMUK8DH3SGB29043`
  - Price: 39,960
  - Mileage: 3,894
  - VIN: `1FMUK8DH3SGB29043`
  - Stock: `N26234A`

## Classification

This evidence is suitable for the guarded external-retail-comp seed path because:

- It has at least three independent public listing records.
- Each comp has price, mileage, VIN, source URL, and listing identifier.
- The candidate model year, make, model family, and trim are aligned closely
  enough for national retail-listing coverage.
- The seed row is explicitly marked as `external_retail_listing_comp`, not as
  Manheim/MMR or closed dealer-sale evidence.

This evidence is not sufficient to claim business-flow recovery by itself. The
only acceptable closure path is:

1. Validate the evidence JSON locally.
2. Merge the governed evidence file through PR review.
3. Run the external-market-comp seed workflow in dry-run mode.
4. Run the same workflow in apply mode with explicit confirmation.
5. Rerun pricing coverage and pricing-source proofs.
6. Rerun a fresh bounded GovDeals source proof and inspect production lineage.
