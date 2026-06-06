# GovDeals Mustang EcoBoost Premium External Comp Provenance - 2026-06-06

Purpose: document current external retail-listing evidence for the GovDeals active candidate:

- Source run: `3aNMtqZQ5LKoWWgH8`
- Listing: `New (Surplus Inventory) 2025 Ford Mustang EcoBoost Premium Coupe`
- VIN: `1FA6P8TH6S5107894`
- State: GA
- Mileage: 38
- Current bid: `$37,283`
- Current production proof before this seed: `pricing_maturity_proxy`, `mmr=$22,000`, `status=skipped_ceiling`

This report does not authorize treating retail asking prices as closed-sale proof. It exists to remove a proxy-pricing blind spot for the current accepted-yield boundary while preserving trim truth. The seed is for `2025 Ford Mustang EcoBoost Premium`, not generic `2025 Ford Mustang`, because GT and EcoBoost trims are materially different markets.

Any production insert must pass `scripts/prepare_external_market_comp_seed.py`, be applied only through the guarded GitHub workflow, and then be proven by a fresh live GovDeals run plus exact Supabase inspection.

## Evidence

1. CarGurus active listing `cargurus-forsyth-s5128436`
   - Captured: `2026-06-06T00:30:10Z`
   - Source URL: https://www.cargurus.com/Cars/new/nl-New-Ford-Mustang-Milledgeville-d2_L6383
   - Title: `New 2025 Ford Mustang EcoBoost Premium Fastback RWD`
   - VIN: `1FA6P8TH4S5128436`
   - Price: `$41,608`
   - Mileage: `60`
   - Caveat: active retail listing; title history not independently verified by DealerScope; not closed-sale evidence.

2. Capital One Auto Navigator active listing `capitalone-brannen-37795`
   - Captured: `2026-06-06T00:30:10Z`
   - Source URL: https://www.capitalone.com/cars/new-2025-ford-mustang/ecoboost-premium-in-warner-robins-ga
   - Title: `New 2025 Ford Mustang EcoBoost Premium RWD`
   - Price: `$37,795`
   - Mileage: `11`
   - Caveat: active retail listing; title history not independently verified by DealerScope; not closed-sale evidence.

3. Kelley Blue Book inventory `781883995`
   - Captured: `2026-06-06T00:30:10Z`
   - Source URL: https://www.kbb.com/cars-for-sale/inventory/781883995?allListingType=all&clickType=listing&endYear=2025&makeCode=FORD&modelCode=MUST&startYear=2025
   - Title: `Used 2025 Ford Mustang Premium`
   - Price: `$36,919`
   - Mileage: `3,033`
   - Caveat: active retail listing with EcoBoost-consistent MPG; title history not independently verified by DealerScope; not closed-sale evidence.

## Computed Seed

- Average retail comp: `$38,774`
- Low retail comp: `$36,919`
- High retail comp: `$41,608`
- Sample size: `3`
- Current scoring conversion: retail comp divided by `1.35`, producing an approximate wholesale value of `$28,721`
- Expected business implication: this should remove proxy-only pricing for the EcoBoost Premium row. It should not make the vehicle acceptable against the current bid; it should convert the outcome into governed comp-based economics.
