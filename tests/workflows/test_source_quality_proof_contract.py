from pathlib import Path

WORKFLOW = Path('.github/workflows/source-quality-proof.yml')
ACTOR = Path('apify/actors/ds-proxibid/src/main.js')


def test_source_quality_proof_reports_two_truth_layers_and_verdicts():
    text = WORKFLOW.read_text()
    assert 'accepted_opportunity_quality' in text
    assert 'scraper_enrichment_attempt_quality' in text
    assert 'issue10_verdict' in text
    assert 'PASS_ORIGINAL' in text
    assert 'low_yield_source_truth_detected' in text
    assert 'BLOCK' in text
    assert 'passes_original_enrichment_standard' in text
    assert 'strict_filter_rejection_detected' in text
    assert 'proof_window_start' in text
    assert 'pricing_raw_present' in text
    assert 'provenance_present' in text
    assert 'sanitized_enriched_samples' in text


def test_source_quality_proof_requires_exact_source_and_apify_proof_for_corrected_scope():
    text = WORKFLOW.read_text()
    assert 'source_site_exact_count' in text
    assert 'source_site_exact_pct' in text
    assert 'source_exact_count == n' in text
    assert 'source_filter_key: f"eq.{source}"' in text
    assert 'created_at' in text and 'timedelta(days=7)' in text
    assert 'or=(' not in text
    assert 'source_quality_proof' in text
    assert 'APIFY_TOKEN' in text
    assert 'PROXIBID_ACTOR_ID' in text
    assert 'SOURCE_ACTOR_IDS' in text
    assert '"govdeals": "CuKaIAcWyFS0EPrAz"' in text
    assert 'extraction_detected' in text


def test_source_quality_proof_requires_actor_run_lineage_pricing_and_provenance_for_original_pass():
    text = WORKFLOW.read_text()
    assert 'rows_for_actor_run' in text
    assert 'row_run_ids' in text
    assert 'accepted_opportunities_for_actor_run' in text
    assert 'run_lineage_proven' in text
    assert 'scraper_enrichment.get("run_lineage_proven")' in text
    assert 'pricing_raw_count == n' in text
    assert 'provenance_count == n' in text
    assert 'source_window_rows' in text


def test_proxibid_actor_emits_non_opportunity_enrichment_proof_record():
    text = ACTOR.read_text()
    assert "record_type: 'source_quality_proof'" in text
    assert 'detail_pages_attempted' in text
    assert 'detail_pages_fetched' in text
    assert 'detail_vins_found' in text
    assert 'detail_mileages_found' in text
    assert 'accepted_rows_total' in text
    assert 'rejected_rows_total' in text
    assert 'accepted_rows_with_vin' in text
    assert 'accepted_rows_with_mileage' in text
    assert 'enriched_rows_accepted' in text
    assert 'enriched_rows_rejected' in text
    assert 'rejection_reasons' in text
    assert 'accepted_enriched_samples' in text
    assert 'rejected_enriched_samples' in text
    assert 'await Actor.pushData(proof)' in text


def test_municibid_actor_emits_zero_output_source_quality_proof():
    text = Path('apify/actors/ds-municibid/src/main.js').read_text()

    assert "record_type: 'source_quality_proof'" in text
    assert 'found_rows_total: found' in text
    assert 'prefilter_passed_rows_total: passed' in text
    assert 'pushed_rows_total: pushed' in text
    assert 'rows_excluded_missing_required_data' in text
    assert 'rows_excluded_age_mileage_prefilter' in text
    assert 'rows_excluded_policy_prefilter' in text
    assert 'await Actor.pushData(proof)' in text


def test_hibid_v2_actor_emits_zero_output_source_quality_proof():
    text = Path('apify/actors/ds-hibid-v2/src/main.js').read_text()

    assert "record_type: 'source_quality_proof'" in text
    assert 'found_rows_total: totalFound' in text
    assert 'prefilter_passed_rows_total: totalPassed' in text
    assert 'pushed_rows_total: totalPassed' in text
    assert 'rows_excluded_missing_required_data' in text
    assert 'rows_excluded_age_mileage_prefilter' in text
    assert 'rows_excluded_policy_prefilter' in text
    assert 'await Actor.pushData(proof)' in text


def test_hibid_v2_actor_does_not_embed_webhook_secret():
    text = Path('apify/actors/ds-hibid-v2/src/main.js').read_text()

    assert "webhookSecret || process.env.WEBHOOK_SECRET" in text
    assert "WEBHOOK_SECRET is required" in text
    assert "webhookSecret = '" not in text
    assert "rDyApg2UUIMl0a8ZUz_swOqsHX7HbjN-gly3xHNwiyA" not in text


def test_bidspotter_actor_is_safe_for_supply_reactivation():
    text = Path('apify/actors/ds-bidspotter/src/main.js').read_text()

    assert "record_type: 'source_quality_proof'" in text
    assert 'found_rows_total: totalFound' in text
    assert 'prefilter_passed_rows_total: totalPassed' in text
    assert 'pushed_rows_total: totalPassed' in text
    assert 'rows_excluded_age_mileage_prefilter' in text
    assert 'rows_excluded_policy_prefilter' in text
    assert 'rows_excluded_bid_range' in text
    assert 'await Actor.pushData(proof)' in text
    assert 'itemCount: totalPassed + 1' in text
    assert 'CURRENT_YEAR - 4' in text
    assert 'DEFAULT_MAX_MILEAGE = 50000' in text
    assert 'MAX_MILEAGE = Number(maxMileage) || DEFAULT_MAX_MILEAGE' in text
    assert "webhookSecret = process.env.WEBHOOK_SECRET" in text
    assert "webhookSecret = '" not in text
    assert 'CURRENT_YEAR - 10' not in text


def test_bidspotter_actor_accounts_for_all_prefilter_skips():
    text = Path('apify/actors/ds-bidspotter/src/main.js').read_text()

    early_non_vehicle_branch = text.split('if (!make && !isVehicleLot(lot.title))', 1)[1].split(
        'const lotDesc = lot.block ||', 1
    )[0]
    assert 'rows_excluded_non_vehicle' in early_non_vehicle_branch
    assert 'early_non_vehicle_reject' in early_non_vehicle_branch
    assert 'const accountedRows =' in text
    assert 'rows_excluded_unaccounted_after_prefilter: Math.max(0, totalFound - totalPassed - accountedRows)' in text


def test_allsurplus_actor_accounts_for_all_found_row_discards():
    text = Path('apify/actors/ds-allsurplus/src/main.js').read_text()

    assert 'rowsExcludedDuplicate++' in text
    assert 'rowsExcludedNonVehicle++' in text
    assert 'rowsExcludedNonUsState++' in text
    assert 'rowsExcludedNonUsdCurrency++' in text
    assert 'rowsExcludedRustState++' in text
    assert 'rowsExcludedNonTargetState++' in text
    assert 'rowsExcludedBidRange++' in text
    assert 'rowsExcludedAgeMileagePrefilter++' in text
    assert 'rowsExcludedAgeMileageAfterDetail++' in text
    assert 'rowsExcludedPolicyAfterDetail++' in text
    assert 'const accountedRows = totalPassed' in text
    assert 'rows_excluded_unaccounted_after_prefilter: Math.max(0, totalFound - accountedRows)' in text


def test_equipmentfacts_actor_is_safe_for_supply_reactivation():
    text = Path('apify/actors/ds-equipmentfacts/src/main.js').read_text()

    assert "record_type: 'source_quality_proof'" in text
    assert 'found_rows_total: totalFound' in text
    assert 'prefilter_passed_rows_total: totalPassed' in text
    assert 'pushed_rows_total: totalPassed' in text
    assert 'rows_excluded_age_mileage_prefilter' in text
    assert 'rows_excluded_policy_prefilter' in text
    assert 'rows_excluded_bid_range' in text
    assert 'rows_excluded_unaccounted_after_prefilter' in text
    assert 'await Actor.pushData(proof)' in text
    assert 'itemCount: totalPassed + 1' in text
    assert 'CURRENT_YEAR - 4' in text
    assert 'DEFAULT_MAX_MILEAGE = 50000' in text
    assert 'mileage > MAX_MILEAGE' in text
    assert 'age > 10' not in text
    assert 'mileage > 100000' not in text


def test_proxibid_actor_keeps_rejected_detail_rows_out_of_opportunities():
    text = ACTOR.read_text()
    assert '!lot.rejected_after_detail' in text
    assert 'applyBuyerGradeFilters(lot).length === 0' in text
    assert 'lot.vin && lot.mileage' in text
    assert 'mileage_over_50k' in text
    assert 'condition_reject' in text
    assert 'rejected_after_detail' in text


def test_proxibid_actor_enforces_dealerscope_age_mileage_source_gate():
    text = ACTOR.read_text()

    assert 'DEFAULT_MIN_YEAR = CURRENT_YEAR - 4' in text
    assert 'DEFAULT_MAX_MILEAGE = 50000' in text
    assert 'EFFECTIVE_MIN_YEAR = Math.max(Number(minYear) || DEFAULT_MIN_YEAR, DEFAULT_MIN_YEAR)' in text
    assert 'EFFECTIVE_MAX_MILEAGE = Math.min(Number(maxMileage) || DEFAULT_MAX_MILEAGE, DEFAULT_MAX_MILEAGE)' in text
    assert 'requested_min_year: Number(minYear) || null' in text
    assert 'requested_max_mileage: Number(maxMileage) || null' in text
    assert 'effective_min_year: EFFECTIVE_MIN_YEAR' in text
    assert 'effective_max_mileage: EFFECTIVE_MAX_MILEAGE' in text
    assert 'rows_excluded_age_mileage_prefilter' in text
    assert 'prefilter_age_mileage_rejected_samples' in text
    assert 'year < EFFECTIVE_MIN_YEAR' in text
    assert 'mileage > EFFECTIVE_MAX_MILEAGE' in text
    assert 'year < minYear' not in text


def test_low_yield_source_truth_is_diagnostic_not_passing():
    text = WORKFLOW.read_text()
    assert 'low_yield_source_truth_detected' in text
    assert 'PASS_CORRECTED_LOW_YIELD_SOURCE_TRUTH' not in text
    assert 'issue10_verdict = "PASS_ORIGINAL" if accepted_quality["passes_original_enrichment_standard"] else "BLOCK"' in text
    assert 'Low-yield scraper truth is diagnostic only' in text


def test_source_quality_proof_reports_required_live_db_fields():
    text = WORKFLOW.read_text()
    for required in [
        'vin',
        'mileage',
        'pricing_raw',
        'pricing_maturity',
        'raw_data',
        'provenance_fields',
        'source_run_id',
        'run_id',
        'sanitized_enriched_samples',
    ]:
        assert required in text


def test_source_quality_proof_reports_actor_output_boundary_separately_from_accepted_rows():
    text = WORKFLOW.read_text()
    assert 'actor_output_quality' in text
    assert 'actor_output_clean' in text
    assert 'pushed_rows_with_description' in text
    assert 'pushed_rows_with_detail_text' in text
    assert 'accepted_landing_status' in text
    assert 'actor_output_live_confirmed_no_accepted_rows' in text
    assert 'dirty_actor_output' in text
    assert 'accepted_opportunity_quality' in text


def test_source_quality_proof_retries_transient_api_timeouts():
    text = WORKFLOW.read_text()
    assert 'import time' in text
    assert 'import urllib.error' in text
    assert 'def json_get(url, headers=None, attempts=3):' in text
    assert 'except (TimeoutError, urllib.error.URLError)' in text
    assert 'if attempt == attempts - 1' in text
    assert 'time.sleep' in text
