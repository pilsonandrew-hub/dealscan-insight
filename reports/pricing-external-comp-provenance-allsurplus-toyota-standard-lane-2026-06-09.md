# Pricing External Comp Provenance - AllSurplus Toyota Standard Lane

Generated: 2026-06-09 00:30 PDT

## Status

`locally validated only` until the evidence files pass PR review, the guarded
external-market-comp workflow validates them from main, the apply workflow
inserts/refreshed the exact market price rows, and fresh pricing/source-yield
proofs confirm the live blocker moved.

## Why This Exists

Issue #10 exposed a real two-lane mismatch: source/proof defaults were using
premium-only 4yr/50k assumptions while DealerScope's standard lane allows
10yr/100k with miles-per-year control. After PRs #272-#275 repaired that, the
standard-lane proof surface changed: clean active gov/public rows now reach the
pricing proof stack, but many are blocked because pricing maturity remains
proxy and there is no trusted internal comp evidence.

The highest-signal fresh blockers were active clean AllSurplus Toyota rows:

- 2025 Toyota Tundra, AL, VIN present, 14k-16k miles, bid/proxy bid 9,100,
  proxy MMR 38,000, no usable `market_prices`, `dealer_sales`, or history comp.
- 2025 Toyota Tacoma, AL, VIN present, active listing rows, bid/proxy bid around
  10,050-10,550, proxy MMR 31,000, no usable comp evidence.

DealerScope is correct to block alerts on proxy pricing alone. These artifacts
add governed active retail-listing evidence for the exact year/make/model/state
pricing keys without weakening that gate.

## Evidence Files

- `reports/external-comp-evidence-allsurplus-tundra-2026-06-09.json`
- `reports/external-comp-evidence-allsurplus-tacoma-2026-06-09.json`

## External Listing Evidence

Tundra comps:

- Capital One Auto Navigator / Springhill Toyota, VIN `5TFLA5DB5SX301117`,
  14,970 miles, price 49,572.
- CarMax Mobile, VIN `5TFLA5DB6SX261789`, 8,708 miles, price 46,998.
- CarGurus / Mullinax Ford of Mobile, VIN `5TFLA5DB2SX258727`, 33,140 miles,
  price 45,990.
- Edmunds national retail listing, VIN `5TFLA5DB9SX304814`, 12,527 miles,
  price 44,463.

Tacoma comps:

- CARFAX Birmingham-area listing, VIN `3TMLB5JN4SM106207`, 4,451 miles,
  price 42,706.
- CARFAX Opelika listing, VIN `3TMKB5FN4SM025633`, 34,919 miles, price 33,595.
- CARFAX national 2025 Tacoma listing, VIN `3TYLC5LN1ST033120`, 4,262 miles,
  price 39,991.
- Mullinax Ford of Mobile listing, VIN `3TYKD5HN9ST025817`, 7,027 miles,
  price 35,200.

## Guardrails

- These are active retail listings, not closed-sale outcomes.
- These evidence rows must stay marked `external_retail_listing_comp`.
- They should only cover the exact AL state pricing keys shown in the proof.
- They do not justify relaxing proxy-pricing alert policy.
- Issue #10 can only move after live apply and fresh proof reruns confirm
  whether these rows create accepted alert-grade opportunities or reveal the
  next blocker.
