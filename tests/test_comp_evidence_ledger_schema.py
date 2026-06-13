from pathlib import Path


MIGRATION_DIR = Path(__file__).resolve().parents[1] / "supabase" / "migrations"


def _migration_sql() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(MIGRATION_DIR.glob("*.sql"))
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


def test_market_scout_run_status_is_constrained():
    sql = _migration_sql()

    assert "constraint chk_market_scout_run_status" in sql
    assert "status in ('started', 'collecting', 'completed', 'failed')" in sql


def test_comp_evidence_ledger_rls_has_explicit_service_role_policies():
    sql = _migration_sql()

    for table in [
        "market_scout_runs",
        "sold_comp_candidates",
        "sold_comp_reviews",
        "verified_sold_comps",
        "market_scout_artifacts",
    ]:
        assert f"alter table public.{table} enable row level security" in sql
        assert f"on public.{table}" in sql
        assert "to service_role" in sql


def test_sold_comp_reviews_are_idempotent_per_verifier_version():
    sql = _migration_sql()

    assert "sold_comp_reviews" in sql
    assert "candidate_id, reviewer, reviewer_version" in sql


def test_verified_sold_comps_support_candidate_id_upsert_conflict():
    sql = _migration_sql()

    assert "create unique index if not exists idx_verified_sold_comps_candidate_id" in sql
    assert "on public.verified_sold_comps(candidate_id)" in sql
    assert "constraint verified_sold_comps_candidate_id_key" in sql
    assert "unique (candidate_id)" in sql
    assert "notify pgrst, 'reload schema'" in sql


def test_post_close_outcome_requests_are_separate_from_comp_evidence_ledger():
    sql = _migration_sql()

    assert "create table if not exists public.post_close_outcome_requests" in sql
    assert "referral_source" in sql
    assert "outcome_status" in sql
    assert "source_site, source_listing_id" in sql
    assert "sold_comp_candidates" in sql


def test_photo_count_empty_array_backfill_falls_through_to_single_image_evidence():
    sql = (
        MIGRATION_DIR / "20260613_backfill_opportunity_photo_count_empty_arrays.sql"
    ).read_text(encoding="utf-8").lower()

    assert "greatest(" in sql
    assert "jsonb_array_elements_text(raw_data->'photos')" in sql
    assert "jsonb_array_elements_text(raw_data->'photo_urls')" in sql
    assert "raw_data->>'photo_url'" in sql
    assert "raw_data->>'image_url'" in sql
    assert "raw_data->>'imageurl'" in sql
    assert "where opportunities.id = photo_evidence.id" in sql
    assert "photo_evidence.raw_photo_count > opportunities.photo_count" in sql
    assert "where photo_count = 0" not in sql


def test_bidder_count_migration_adds_nullable_governed_bidder_depth_and_backfill():
    sql = (MIGRATION_DIR / "20260613_opportunity_bidder_count.sql").read_text().lower()

    assert "add column if not exists bidder_count integer" in sql
    assert "opportunities_bidder_count_nonnegative" in sql
    assert "check (bidder_count is null or bidder_count >= 0)" in sql
    assert "raw_data->>'bid_count'" in sql
    assert "raw_data->>'bidcount'" in sql
    assert "opportunities.bidder_count is null" in sql
