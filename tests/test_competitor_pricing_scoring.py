import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ingest.score import score_deal


BASE = dict(
    bid=10000,
    state="CA",
    source_site="GovDeals",
    make="Ford",
    model="F-150",
    year=2022,
    mileage=40000,
    title_status="clean",
    description="clean fleet truck, runs and drives",
    photos=["https://example.com/a.jpg", "https://example.com/b.jpg"],
)


def test_competitor_comps_override_proxy_when_enough_comps():
    result = score_deal(
        mmr_ca=20000,
        competitor_comp_price=24000,
        competitor_comp_count=8,
        competitor_comp_low=22000,
        competitor_comp_high=26000,
        **BASE,
    )
    assert result["competitor_comp_used"] is True
    assert result["pricing_basis"] == "competitor_sales"
    assert result["pricing_maturity"] == "market_comp"
    # Actual median (24000) replaces the model-proxy (20000) as the ceiling basis.
    assert result["mmr_estimated"] == 24000


def test_competitor_comps_ignored_when_below_min_count():
    result = score_deal(
        mmr_ca=20000,
        competitor_comp_price=24000,
        competitor_comp_count=3,
        **BASE,
    )
    assert result["competitor_comp_used"] is False
    assert result["pricing_basis"] in ("model_proxy", "retail_comp")
    assert result["mmr_estimated"] == 20000


def test_proxy_actual_divergence_flagged_above_15_pct():
    result = score_deal(
        mmr_ca=20000,
        competitor_comp_price=24000,  # +20% vs proxy
        competitor_comp_count=8,
        **BASE,
    )
    assert result["proxy_actual_divergence_pct"] == 0.2
    assert result["proxy_actual_divergence_flag"] is True
    assert "proxy_actual_divergence" in result["score_provenance"]["fallback_flags"]


def test_proxy_actual_divergence_not_flagged_within_threshold():
    result = score_deal(
        mmr_ca=20000,
        competitor_comp_price=21000,  # +5% vs proxy
        competitor_comp_count=8,
        **BASE,
    )
    assert result["proxy_actual_divergence_flag"] is False
    assert "proxy_actual_divergence" not in result["score_provenance"]["fallback_flags"]


def test_live_manheim_takes_priority_over_competitor_comps():
    result = score_deal(
        mmr_ca=20000,
        competitor_comp_price=24000,
        competitor_comp_count=8,
        manheim_mmr_mid=21000,
        manheim_mmr_low=19000,
        manheim_mmr_high=23000,
        manheim_confidence=0.82,
        manheim_source_status="live",
        **BASE,
    )
    assert result["competitor_comp_used"] is False
    assert result["pricing_basis"] == "live_manheim"
    assert result["pricing_maturity"] == "live_market"
    assert result["mmr_estimated"] == 21000


def test_competitor_fields_present_in_output():
    result = score_deal(mmr_ca=20000, **BASE)
    for key in (
        "competitor_comp_price",
        "competitor_comp_count",
        "competitor_comp_used",
        "pricing_basis",
        "proxy_actual_divergence_flag",
        "proxy_mmr_estimate",
    ):
        assert key in result
