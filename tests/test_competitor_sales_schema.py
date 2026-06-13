import re
from pathlib import Path


def _all_competitor_sales_sql() -> str:
    root = Path(__file__).resolve().parents[1]
    chunks = []
    for path in sorted((root / "supabase" / "migrations").glob("*competitor_sales*.sql")):
        chunks.append(path.read_text(encoding="utf-8").lower())
    return "\n".join(chunks)


def test_competitor_sales_url_upsert_conflict_target_has_non_partial_unique_index():
    sql = _all_competitor_sales_sql()

    assert "begin;" in sql
    assert "commit;" in sql
    assert sql.index("begin;") < sql.index("commit;")
    assert "max(source_listing_id)" not in sql
    assert "first_value(source_listing_id)" in sql
    assert "rows between unbounded preceding and unbounded following" in sql
    assert "create or replace function public.reconcile_competitor_sale_url_only_duplicate(row_payload jsonb)" in sql
    assert "grant execute on function public.reconcile_competitor_sale_url_only_duplicate(jsonb) to service_role" in sql

    duplicate_cleanup = re.search(
        r"partition\s+by\s+source,\s*listing_url[\s\S]+"
        r"delete\s+from\s+public\.competitor_sales\s+as\s+duplicate[\s\S]+"
        r"ranked\.id\s+<>\s+ranked\.keep_id",
        sql,
    )
    listing_duplicate_cleanup = re.search(
        r"partition\s+by\s+source,\s*source_listing_id[\s\S]+"
        r"where\s+source_listing_id\s+is\s+not\s+null[\s\S]+"
        r"delete\s+from\s+public\.competitor_sales\s+as\s+duplicate[\s\S]+"
        r"ranked\.id\s+<>\s+ranked\.keep_id",
        sql,
    )
    listing_index = re.search(
        r"create\s+unique\s+index\s+if\s+not\s+exists\s+idx_competitor_sales_source_listing_upsert"
        r"\s+on\s+public\.competitor_sales\(source,\s*source_listing_id\)\s*;",
        sql,
        re.DOTALL,
    )
    url_index = re.search(
        r"create\s+unique\s+index\s+if\s+not\s+exists\s+idx_competitor_sales_source_url_upsert"
        r"\s+on\s+public\.competitor_sales\(source,\s*listing_url\)\s*;",
        sql,
        re.DOTALL,
    )

    assert duplicate_cleanup is not None
    assert listing_duplicate_cleanup is not None
    assert listing_index is not None
    assert url_index is not None
    assert duplicate_cleanup.start() < url_index.start()
    assert listing_duplicate_cleanup.start() < listing_index.start()
    assert listing_index.start() < sql.index("drop index if exists public.idx_competitor_sales_source_listing")
    assert url_index.start() < sql.index("drop index if exists public.idx_competitor_sales_source_url")
    assert "drop index if exists public.idx_competitor_sales_source_listing" in sql
    assert "drop index if exists public.idx_competitor_sales_source_url" in sql
    assert sql.index("create or replace function public.reconcile_competitor_sale_url_only_duplicate") < sql.index(
        "notify pgrst, 'reload schema'"
    )
    assert "notify pgrst, 'reload schema'" in sql
