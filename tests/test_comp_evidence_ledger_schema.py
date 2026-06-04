from pathlib import Path


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def _migration_sql() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(MIGRATION_DIR.glob("20260603*.sql"))
    )


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


def test_sold_comp_reviews_are_idempotent_per_verifier_version():
    sql = _migration_sql()

    assert "sold_comp_reviews" in sql
    assert "candidate_id, reviewer, reviewer_version" in sql


def test_post_close_outcome_requests_are_separate_from_comp_evidence_ledger():
    sql = _migration_sql()

    assert "create table if not exists public.post_close_outcome_requests" in sql
    assert "referral_source" in sql
    assert "outcome_status" in sql
    assert "source_site, source_listing_id" in sql
    assert "sold_comp_candidates" in sql
