from pathlib import Path

WORKFLOW = Path('.github/workflows/source-quality-proof.yml')
ACTOR = Path('apify/actors/ds-proxibid/src/main.js')


def test_source_quality_proof_reports_accepted_and_scraper_enrichment_layers():
    text = WORKFLOW.read_text()
    assert 'accepted_opportunity_quality' in text
    assert 'scraper_enrichment_attempt_quality' in text
    assert 'source_quality_proof' in text
    assert 'APIFY_TOKEN' in text
    assert 'PROXIBID_ACTOR_ID' in text


def test_proxibid_actor_emits_non_opportunity_enrichment_proof_record():
    text = ACTOR.read_text()
    assert "record_type: 'source_quality_proof'" in text
    assert 'detail_pages_attempted' in text
    assert 'detail_pages_fetched' in text
    assert 'detail_vins_found' in text
    assert 'detail_mileages_found' in text
    assert 'enriched_rows_accepted' in text
    assert 'enriched_rows_rejected' in text
    assert 'rejection_reasons' in text
    assert 'await Actor.pushData(proof)' in text


def test_proxibid_actor_keeps_rejected_detail_rows_out_of_opportunities():
    text = ACTOR.read_text()
    assert ".filter(lot => !lot.rejected_after_detail && applyBuyerGradeFilters(lot).length === 0)" in text
    assert 'mileage_over_50k' in text
    assert 'condition_reject' in text
