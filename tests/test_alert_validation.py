from backend.ingest.alert_validation import (
    alert_validation_mmr_estimate,
    build_alert_validation_prompt,
)


def test_alert_validation_mmr_prefers_top_level_mmr_then_breakdown_then_estimated_sale_price():
    assert alert_validation_mmr_estimate({"mmr_estimated": 21000, "estimated_sale_price": 18000}) == 21000
    assert alert_validation_mmr_estimate({"score_breakdown": {"mmr_estimated": 20500}}) == 20500
    assert alert_validation_mmr_estimate({"estimated_sale_price": 11575}) == 11575
    assert alert_validation_mmr_estimate({"score_breakdown": {"estimated_sale_price": 11750}}) == 11750


def test_alert_validation_mmr_falls_back_to_manheim_and_mmr_mid():
    assert alert_validation_mmr_estimate({"manheim_mmr_mid": 22000}) == 22000
    assert alert_validation_mmr_estimate({"score_breakdown": {"manheim_mmr_mid": 22500}}) == 22500
    assert alert_validation_mmr_estimate({"mmr_mid": 23000}) == 23000
    assert alert_validation_mmr_estimate({"score_breakdown": {"mmr_mid": 23500}}) == 23500


def test_alert_validation_prompt_keeps_dos_and_early_bid_instructions():
    prompt = build_alert_validation_prompt(
        {
            "title": "2024 Toyota Camry",
            "year": 2024,
            "make": "Toyota",
            "model": "Camry",
            "current_bid": 645,
            "expected_close_bid": 14_000,
            "max_bid": 18_000,
            "mmr_estimated": 22_000,
            "gross_margin": 3_000,
            "bid_headroom": 4_000,
            "pricing_maturity": "retail_comp",
            "pricing_source": "market_comps",
            "current_bid_trust_score": 0.82,
            "manheim_confidence": 78,
            "dos_score": 90.8,
            "state": "CA",
        }
    )

    assert "higher DOS score is better" in prompt
    assert "not a damage score" in prompt
    assert "do not reject solely because current bid is far below MMR" in prompt
    assert "Expected close bid: $14000" in prompt
    assert "Max bid: $18000" in prompt
    assert "Trust score: 0.82" in prompt
