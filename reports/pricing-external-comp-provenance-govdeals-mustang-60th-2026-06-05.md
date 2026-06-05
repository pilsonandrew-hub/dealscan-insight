# GovDeals Mustang 60th Anniversary External Comp Provenance - 2026-06-05

Purpose: document current external retail-listing evidence for the GovDeals active candidate:

- Source run: `EPwVn5rEkaSza5HBq`
- Listing: `New (Surplus Inventory) 2025 Ford Mustang GT Premium 60th Anniversary Edition`
- VIN: `1FA6P8CF8S5410562`
- State: GA
- Mileage: 104
- Current bid: `$59,433`
- Current production proof before this seed: `pricing=proxy`, `mmr=$22,000`, `cost=$66,295`, `margin=$-44,295`

This report does not authorize treating retail asking prices as closed-sale proof. It exists to remove a proxy-pricing blind spot for the current accepted-yield boundary. Any production insert must pass `scripts/prepare_external_market_comp_seed.py`, be applied only through the guarded GitHub workflow, and then be proven by a fresh live GovDeals run plus exact Supabase inspection.

## Evidence

1. Kelley Blue Book inventory `759557159`
   - Captured: `2026-06-05T15:05:00Z`
   - Source URL: https://www.kbb.com/cars-for-sale/inventory/759557159?allListingType=all&clickType=listing&endYear=2025&makeCode=FORD&modelCode=MUST&startYear=2025&trimCode=MUST%7CGT+Premium
   - Title: `New 2025 Ford Mustang GT Premium w/ 60th Anniversary Package`
   - Price: `$59,170`
   - Mileage: `6`
   - Caveat: active retail listing; title history not independently verified by DealerScope; not closed-sale evidence.

2. Kelley Blue Book inventory `752418561`
   - Captured: `2026-06-05T15:05:00Z`
   - Source URL: https://www.kbb.com/cars-for-sale/inventory/752418561?allListingType=all&clickType=listing&endYear=2025&makeCode=FORD&modelCode=MUST&startYear=2025&trimCode=MUST%7CGT+Premium
   - Title: `New 2025 Ford Mustang GT Premium w/ 60th Anniversary Package`
   - Price: `$59,000`
   - Mileage: `14`
   - Caveat: active retail listing; title history not independently verified by DealerScope; not closed-sale evidence.

3. Kelley Blue Book inventory `747797546`
   - Captured: `2026-06-05T15:05:00Z`
   - Source URL: https://www.kbb.com/cars-for-sale/inventory/747797546?allListingType=all&clickType=listing&endYear=2025&makeCode=FORD&modelCode=MUST&startYear=2025&trimCode=MUST%7CGT+Premium
   - Title: `New 2025 Ford Mustang GT Premium w/ 60th Anniversary Package`
   - Price: `$58,562`
   - Mileage: `207`
   - Caveat: active retail listing; title history not independently verified by DealerScope; not closed-sale evidence.

## Computed Seed

- Average retail comp: `$58,910.67`
- Low retail comp: `$58,562`
- High retail comp: `$59,170`
- Sample size: `3`
- Current scoring conversion: retail comp divided by `1.35`, producing an approximate wholesale value of `$43,637.53`
- Expected business implication: this should remove the false `$22,000` proxy economics for this row, but it should not make the vehicle acceptable. Against the current `$66,295` all-in cost, the corrected wholesale estimate still implies deeply negative margin.
