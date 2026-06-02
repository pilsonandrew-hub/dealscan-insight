# 2023 Toyota Tacoma External Comp Evidence — 2026-06-02

Status: hypothesis / governed external listing evidence only.

Purpose: document current external retail listing signals for the AllSurplus source-level pricing gap:

- Source candidate: AllSurplus `2023 Toyota Tacoma`
- State: FL
- VIN: `3TMAZ5CN0PM202309`
- Mileage: `16,808`
- Bid: `$22,000`
- Proxy MMR: `$31,000`
- Prior classification: `unknown_auction_status_pricing_gap`

This report does not authorize proxy-derived market-price seeding and does not treat active retail listings as closed-sale outcome evidence. Any insert must pass `scripts/prepare_external_market_comp_seed.py` and preserve the active-listing caveat.

## Evidence

1. Lakeland Toyota, Lakeland FL
   - Listing: Gold Certified 2023 Toyota Tacoma 2WD SR5
   - URL: https://www.lakelandtoyota.com/used-Lakeland-2023-Toyota-Tacoma%2B2WD-SR5-3TMAZ5CN1PM198528
   - Price used: `$31,343` total price
   - Mileage: `47,330`
   - VIN: `3TMAZ5CN1PM198528`
   - Caveat: dealer active retail listing; total price includes disclosed dealer fees; not closed-sale evidence.

2. CARFAX / Peter Boulware Toyota, Tallahassee FL
   - Listing: Used 2023 Toyota Tacoma SR5
   - URL: https://www.carfax.com/Used-Toyota-Tacoma-Tallahassee-FL_w641_c21359
   - Price used: `$34,879`
   - Mileage: `75,085`
   - VIN: `3TMAZ5CNXPM212782`
   - Caveat: active CARFAX retail listing; no accident/damage reported on the listing; not closed-sale evidence.

3. CARFAX / Peter Boulware Toyota, Tallahassee FL
   - Listing: Used 2023 Toyota Tacoma SR5
   - URL: https://www.carfax.com/Used-Toyota-Tacoma-Tallahassee-FL_w641_c21359
   - Price used: `$36,838`
   - Mileage: `45,132`
   - VIN: `3TMAZ5CN8PM203014`
   - Caveat: active CARFAX retail listing; no accident/damage reported on the listing; not closed-sale evidence.

4. CARFAX / Peter Boulware Toyota, Tallahassee FL
   - Listing: Used 2023 Toyota Tacoma TRD Off Road
   - URL: https://www.carfax.com/Used-Toyota-Tacoma-Tallahassee-FL_w641_c21359
   - Price used: `$40,944`
   - Mileage: `69,957`
   - VIN: `3TMCZ5AN5PM577883`
   - Caveat: active CARFAX retail listing; no accident/damage reported on the listing; not closed-sale evidence.

## Boundary

This evidence is enough to validate a dry-run external comp seed candidate, not enough to treat the Tacoma gap as live-confirmed resolved unless the governed insert is applied and verified through the pricing coverage reporter / retail comp service.
