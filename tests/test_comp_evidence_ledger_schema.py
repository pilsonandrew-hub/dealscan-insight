from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[1] / "supabase" / "migrations" / "20260603_comp_evidence_ledger.sql"


def _migration_sql() -> str:
    return MIGRATION.read_text(encoding="utf-8").lower()


def test_comp_evidence_ledger_migration_defines_required_tables():
    sql = _migration_sql()

    for table in [
        "market_scout_runs",
        "sold_comp_candidates",
        "sold_comp_reviews",
        "verified_sold_comps",
        "market_scout_artifacts",
    ]:
        assert f"create table if not exists public.{table}" in sql


def test_sold_comp_candidates_preserve_provenance_price_basis_and_bias_controls():
    sql = _migration_sql()

    for column in [
        "run_id",
        "source_name",
        "source_listing_id",
        "listing_url",
        "evidence_ref",
        "raw_artifact_path",
        "screenshot_path",
        "sale_status_raw",
        "sale_status_normalized",
        "sold_price_raw",
        "sold_price_normalized",
        "sold_price_hammer",
        "buyer_premium",
        "fees",
        "price_includes_fees",
        "sold_price_all_in",
        "price_basis",
        "channel",
        "extractor_version",
        "schema_version",
        "source_policy_version",
        "candidate_status",
        "rejection_reason",
        "dedup_key",
        "raw_payload",
    ]:
        assert column in sql

    assert "unique" in sql
    assert "source_name, source_listing_id" in sql
