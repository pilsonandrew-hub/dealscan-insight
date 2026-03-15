# Small-Set Live Pipe Verification

This is the operator check for the Small-Set Live Verification sprint.

It is intentionally narrow. The goal is to verify live truth on a small trusted source set, not to claim broad-source completeness.

## What It Verifies

`scripts/verify_small_set_live_pipe.py` queries the canonical `public.opportunities` table and reports:

- whether rows landed for the trusted source set in a recent window
- pricing maturity mix (`live_market`, `market_comp`, `proxy`, `unknown`)
- whether required pricing fields are populated
- whether projected economics fields are present
- recent sample rows for spot checks
- whether outcome fields are writable, if you run the optional rolled-back write probe

It does not fake verification. It reads the live database directly. The write probe performs a real `UPDATE ... RETURNING` and then rolls the transaction back.

## Default Trusted Source Set

The default source set is:

- `govdeals`
- `publicsurplus`

You can override the sources explicitly if the trusted set changes.

## Usage

Basic recent-window verification:

```bash
DATABASE_URL='postgresql://...sslmode=require' \
python3 scripts/verify_small_set_live_pipe.py --lookback-hours 24
```

Explicit trusted sources:

```bash
DATABASE_URL='postgresql://...sslmode=require' \
python3 scripts/verify_small_set_live_pipe.py \
  --sources govdeals publicsurplus \
  --lookback-hours 48
```

Run the outcomes write probe against the most recent trusted-source row:

```bash
DATABASE_URL='postgresql://...sslmode=require' \
python3 scripts/verify_small_set_live_pipe.py \
  --lookback-hours 24 \
  --probe-outcome-write
```

Probe a specific opportunity id instead:

```bash
DATABASE_URL='postgresql://...sslmode=require' \
python3 scripts/verify_small_set_live_pipe.py \
  --probe-outcome-write \
  --outcome-opportunity-id '00000000-0000-0000-0000-000000000000'
```

## Exit Codes

- `0`: query completed, and rows were present in the requested window; if requested, the rolled-back outcome write probe also succeeded
- `1`: no rows landed in the window, or the optional outcome write probe failed
- `2`: no database connection string was provided, or the database could not be reached

## Operator Notes

- Run `scripts/verify_live_opportunities_schema.py` first if you need to confirm the canonical schema contract.
- Use this script after a live ingest run to answer operational questions about landing rate, pricing maturity quality, economics coverage, and outcome-field writability on the trusted source subset.
