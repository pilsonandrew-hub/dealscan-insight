from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "run-apify-actor.yml"


def test_run_apify_actor_workflow_supports_bounded_govdeals_proof():
    text = WORKFLOW.read_text()

    assert "ds-govdeals" in text
    assert "CuKaIAcWyFS0EPrAz" in text
    assert "max_pages" in text
    assert "runtime_budget_ms" in text
    assert '"maxPages": int(os.environ.get("MAX_PAGES") or "1")' in text
    assert '"runtimeBudgetMs": int(os.environ.get("RUNTIME_BUDGET_MS") or "240000")' in text
    assert "pushed_rows_with_description" in text
    assert "pushed_rows_with_detail_text" in text
    assert "description_samples" in text
    assert "source_quality_proof" in text
    assert "rows_excluded_age_mileage_prefilter" in text
    assert "rows_excluded_age_mileage_after_detail" in text
    assert "prefilter_age_mileage_rejected_samples" in text
    assert "post_age_mileage_rejected_samples" in text
    assert "rows_excluded_policy_after_detail" in text
    assert "rows_excluded_unaccounted_after_prefilter" in text
    assert "post_policy_rejected_samples" in text


def test_run_apify_actor_workflow_supports_manual_jjkane_proof():
    text = WORKFLOW.read_text()

    assert "ds-jjkane" in text
    assert "lvb7T6VMFfNUQpqlq" in text
    assert "JJ_KANE_MAX_ITEMS" in text
    assert '"maxItems": int(os.environ.get("JJ_KANE_MAX_ITEMS") or "75")' in text
    assert "rows_excluded_policy_prefilter" in text
    assert "rows_excluded_bid_range" in text
    assert "rows_excluded_zero_pricing_signal" in text
    assert "prefilter_policy_rejected_samples" in text
    assert "zero_pricing_rejected_samples" in text


def test_run_apify_actor_workflow_supports_all_enabled_source_proofs():
    text = WORKFLOW.read_text()

    for actor_name, actor_id in {
        "ds-govdeals": "CuKaIAcWyFS0EPrAz",
        "ds-publicsurplus": "9xxQLlRsROnSgA42i",
        "ds-municibid": "svmsItf3CRBZuIntp",
        "ds-gsaauctions": "fvDnYmGuFBCrwpEi9",
        "ds-allsurplus": "gYGIfHeYeN3EzmLnB",
        "ds-govplanet": "pO2t5UDoSVmO1gvKJ",
        "ds-proxibid": "bxhncvtHEP712WX2e",
        "ds-usgovbid": "6XO9La81aEmtsCT3g",
        "ds-jjkane": "lvb7T6VMFfNUQpqlq",
        "ds-hibid-v2": "7s9e0eATTt1kuGGfE",
    }.items():
        assert actor_name in text
        assert actor_id in text


def test_run_apify_actor_workflow_supports_bounded_bidspotter_supply_proof():
    text = WORKFLOW.read_text()

    assert "ds-bidspotter" in text
    assert "5Eu3hfCcBBdzp6I1u" in text
    assert "FIRECRAWL_API_KEY" in text
    assert "BIDSPOTTER_MAX_CATALOGUES" in text
    assert "BIDSPOTTER_MAX_PAGES" in text
    assert '"maxCatalogues": int(os.environ.get("BIDSPOTTER_MAX_CATALOGUES") or "2")' in text
    assert '"maxPages": int(os.environ.get("BIDSPOTTER_MAX_PAGES") or "1")' in text
    assert '"minYear": datetime.now(timezone.utc).year - 4' in text
    assert '"maxMileage": 50000' in text


def test_run_apify_actor_workflow_schedules_bidspotter_with_github_secret():
    text = WORKFLOW.read_text()

    assert "schedule:" in text
    assert "17 */12 * * *" in text
    assert "github.event_name == 'schedule' && 'ds-bidspotter' || inputs.actor" in text
    assert "FIRECRAWL_API_KEY: ${{ secrets.FIRECRAWL_API_KEY }}" in text


def test_run_apify_actor_workflow_supports_bounded_equipmentfacts_supply_proof():
    text = WORKFLOW.read_text()

    assert "ds-equipmentfacts" in text
    assert "0XjoegYZVcPldLstl" in text
    assert "EQUIPMENTFACTS_MAX_PAGES" in text
    assert '"maxPages": int(os.environ.get("EQUIPMENTFACTS_MAX_PAGES") or "1")' in text
    assert '"minYear": datetime.now(timezone.utc).year - 4' in text
    assert '"maxMileage": 50000' in text


def test_run_apify_actor_workflow_prints_usgovbid_zero_output_proof_fields():
    text = WORKFLOW.read_text()

    assert "auctions_discovered" in text
    assert "bid_urls_resolved" in text
    assert "rows_excluded_search_filter" in text
    assert "rows_excluded_non_vehicle" in text


def test_run_apify_actor_workflow_supports_bounded_govplanet_proof():
    text = WORKFLOW.read_text()

    assert "ds-govplanet" in text
    assert "pO2t5UDoSVmO1gvKJ" in text
    assert "GOVPLANET_MAX_ITEMS_PER_CATEGORY" in text
    assert "GOVPLANET_MAX_DETAIL_PAGES" in text
    assert '"maxItemsPerCategory": int(os.environ.get("GOVPLANET_MAX_ITEMS_PER_CATEGORY") or "1")' in text
    assert '"maxDetailPages": int(os.environ.get("GOVPLANET_MAX_DETAIL_PAGES") or "1")' in text


def test_run_apify_actor_workflow_supports_bounded_hibid_v2_proof():
    text = WORKFLOW.read_text()

    assert "ds-hibid-v2" in text
    assert "7s9e0eATTt1kuGGfE" in text
    assert "HIBID_MAX_PAGES" in text
    assert "HIBID_MAX_MILEAGE" in text
    assert "HIBID_MIN_YEAR" in text
    assert '"maxPages": int(os.environ.get("HIBID_MAX_PAGES") or "1")' in text
    assert '"maxMileage": int(os.environ.get("HIBID_MAX_MILEAGE") or "50000")' in text
    assert '"minYear": int(os.environ.get("HIBID_MIN_YEAR") or str(datetime.now(timezone.utc).year - 4))' in text
    assert '"requested_min_year"' in text
    assert '"requested_max_mileage"' in text
    assert '"effective_min_year"' in text
    assert '"effective_max_mileage"' in text


def test_run_apify_actor_workflow_supports_bounded_proxibid_source_parity_proof():
    text = WORKFLOW.read_text()

    assert "PROXIBID_MIN_YEAR" in text
    assert "PROXIBID_MAX_MILEAGE" in text
    assert '"minYear": int(os.environ.get("PROXIBID_MIN_YEAR") or str(datetime.now(timezone.utc).year - 4))' in text
    assert '"maxMileage": int(os.environ.get("PROXIBID_MAX_MILEAGE") or "50000")' in text
