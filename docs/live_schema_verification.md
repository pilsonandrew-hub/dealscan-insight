# Live Opportunities Schema Verification

This is the operator check for the March 2026 launch-safe `public.opportunities` path.

It verifies the columns the current backend actually expects across:

- ingest writes in `webapp/routers/ingest.py`
- outcome writes in `webapp/routers/outcomes.py`
- March 2026 migrations in `supabase/migrations/`

## What It Checks

`scripts/verify_live_opportunities_schema.py` verifies the required canonical `opportunities` columns added by:

- `20260311_init_schema.sql`
- `20260312_event_identity.sql`
- `20260312_deduplication.sql`
- `20260314_total_cost.sql`
- `20260314_retail_comps.sql`
- `20260314_manheim_ready.sql`
- `20260314_investment_grade.sql`
- `20260314_proxy_scoring_upgrade.sql`
- `20260314_launch_alignment.sql`
- `20260315_expected_close_groundwork.sql`
- `20260315_price_basis_resolver.sql`

It does not fake verification. It connects to Postgres, reads `information_schema.columns`, and reports missing or mismatched columns.

## Usage

1. Get the live Postgres connection string for the Supabase project.
   Use the pooled or direct connection string from Supabase project settings.
2. Run:

```bash
DATABASE_URL='postgresql://...sslmode=require' python3 scripts/verify_live_opportunities_schema.py
```

If you only want the required column list without connecting:

```bash
python3 scripts/verify_live_opportunities_schema.py --print-required
```

You can also pass the DSN explicitly:

```bash
python3 scripts/verify_live_opportunities_schema.py --dsn 'postgresql://...sslmode=require'
```

## Expected Result

- Exit `0`: live schema matches the current launch-safe expectations.
- Exit `1`: one or more required columns are missing or have the wrong type.
- Exit `2`: no connection string was provided, or the database could not be inspected.

## Operator Note

This script is intentionally strict about the canonical `opportunities` path. It does not validate `market_prices` or `dealer_sales` as launch foundations, because they are not treated as canonical live truth in the current backend.
