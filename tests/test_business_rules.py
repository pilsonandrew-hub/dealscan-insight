from backend.business_rules.constants import (
    HOT_DEAL_ALERT_THRESHOLD,
    PREMIUM_BID_CEILING_PCT,
    PREMIUM_MIN_MARGIN,
    PRICING_MATURITY_ALERT_ALLOWED,
    PROXY_PRICING_ALERT_ALLOWED,
    STANDARD_BID_CEILING_PCT,
    STANDARD_MIN_MARGIN,
    STANDARD_MAX_MILEAGE,
)
from backend.business_rules.pricing import pricing_allows_hot_alert
from backend.business_rules.gates import (
    bid_ceiling_pct_for_tier,
    determine_vehicle_tier,
    min_margin_for_tier,
    passes_ingest_margin_floor,
)
from backend.business_rules.pricing import classify_pricing_confidence, PricingConfidence
from backend.business_rules import current_calendar_year


def test_lane_constants():
    assert PREMIUM_BID_CEILING_PCT == 0.88
    assert STANDARD_BID_CEILING_PCT == 0.80
    assert PREMIUM_MIN_MARGIN == 1500.0
    assert STANDARD_MIN_MARGIN == 2500.0
    assert HOT_DEAL_ALERT_THRESHOLD == 80.0


def test_determine_vehicle_tier_matches_canonical_policy():
    year = current_calendar_year()
    assert determine_vehicle_tier(year - 4, 50_000) == "premium"
    assert determine_vehicle_tier(year - 4, "50,000") == "premium"
    assert determine_vehicle_tier(year - 4, 50_001) == "rejected"
    assert determine_vehicle_tier(year - 5, 90_000) == "standard"
    assert determine_vehicle_tier(year - 5, STANDARD_MAX_MILEAGE + 1) == "rejected"
    assert determine_vehicle_tier(year - 2, None) == "rejected"
    assert determine_vehicle_tier(year - 5, None) == "rejected"


def test_lane_aware_margin_floor():
    assert passes_ingest_margin_floor(1600, "premium") is True
    assert passes_ingest_margin_floor(1600, "standard") is False
    assert passes_ingest_margin_floor(2600, "standard") is True
    assert bid_ceiling_pct_for_tier("standard") == STANDARD_BID_CEILING_PCT
    assert min_margin_for_tier("premium") == PREMIUM_MIN_MARGIN


def test_proxy_pricing_classification():
    result = classify_pricing_confidence({"mmr_estimated": 18000, "pricing_maturity": "proxy"})
    assert result.confidence == PricingConfidence.PROXY_ESTIMATE
    assert result.maturity == "proxy"


def test_hot_alert_policy_blocks_proxy_maturity():
    assert "proxy" not in PRICING_MATURITY_ALERT_ALLOWED
    assert PROXY_PRICING_ALERT_ALLOWED is False
    allowed, reason = pricing_allows_hot_alert(
        {"mmr_estimated": 20000, "pricing_maturity": "proxy", "mmr_confidence_proxy": 90}
    )
    assert allowed is False
    assert reason


def test_market_comp_label_without_comp_evidence_does_not_allow_hot_alert():
    result = classify_pricing_confidence({
        "pricing_maturity": "market_comp",
        "mmr_estimated": 24000,
        "retail_comp_count": 0,
    })

    assert result.confidence == PricingConfidence.INSUFFICIENT
    assert result.maturity == "market_comp"
    assert result.allows_hot_alert is False
    assert result.blocking_reason == "market_comp_evidence_missing"

    allowed, reason = pricing_allows_hot_alert({
        "pricing_maturity": "market_comp",
        "mmr_estimated": 24000,
        "retail_comp_count": 1,
        "retail_comp_confidence": 0.9,
    })

    assert allowed is False
    assert reason == "market_comp_evidence_missing"


def test_market_comp_label_requires_comp_confidence_for_hot_alert():
    allowed, reason = pricing_allows_hot_alert({
        "pricing_maturity": "market_comp",
        "retail_comp_count": 2,
    })

    assert allowed is False
    assert reason == "market_comp_confidence_missing"
