"""AI validation prompt helpers for hot-deal alert review.

Pure helper module: no network calls, no model routing, no logging.
"""

from __future__ import annotations

from typing import Any


def alert_validation_mmr_estimate(deal: dict[str, Any]) -> Any:
    breakdown = deal.get("score_breakdown") if isinstance(deal.get("score_breakdown"), dict) else {}
    for value in (
        deal.get("mmr_estimated"),
        breakdown.get("mmr_estimated"),
        deal.get("estimated_sale_price"),
        breakdown.get("estimated_sale_price"),
        deal.get("manheim_mmr_mid"),
        breakdown.get("manheim_mmr_mid"),
        deal.get("mmr_mid"),
        breakdown.get("mmr_mid"),
    ):
        if value not in (None, ""):
            return value
    return None


def build_alert_validation_prompt(deal: dict[str, Any]) -> str:
    mmr_estimated = alert_validation_mmr_estimate(deal)
    breakdown = deal.get("score_breakdown") if isinstance(deal.get("score_breakdown"), dict) else {}
    expected_close = deal.get("expected_close_bid") or breakdown.get("expected_close_bid")
    max_bid = deal.get("max_bid") or breakdown.get("max_bid")
    gross_margin = deal.get("gross_margin") or breakdown.get("gross_margin")
    bid_headroom = deal.get("bid_headroom") or breakdown.get("bid_headroom")
    pricing_maturity = deal.get("pricing_maturity") or breakdown.get("pricing_maturity")
    pricing_source = deal.get("pricing_source") or breakdown.get("pricing_source")
    trust_score = deal.get("current_bid_trust_score") or breakdown.get("current_bid_trust_score")
    confidence = deal.get("manheim_confidence") or breakdown.get("confidence")
    return (
        "You are a conservative vehicle arbitrage expert validating whether a DealerScope "
        "hot-deal alert is safe to send. In DealerScope, a higher DOS score is better "
        "(80+ means high-priority arbitrage candidate), not a damage score. The current bid "
        "may be an early live auction bid, so do not reject solely because current bid is far "
        "below MMR; validate against expected close, max bid discipline, margin, pricing "
        "maturity, location, age, and data confidence. Validate this deal: "
        f"{deal.get('title')}, Year: {deal.get('year')}, Make: {deal.get('make')}, "
        f"Model: {deal.get('model')}, Current bid: ${deal.get('current_bid')}, "
        f"Expected close bid: ${expected_close}, Max bid: ${max_bid}, "
        f"MMR estimate: ${mmr_estimated}, Gross margin: ${gross_margin}, "
        f"Bid headroom: ${bid_headroom}, DOS score: {deal.get('dos_score')}, "
        f"Pricing: {pricing_maturity} via {pricing_source}, "
        f"Trust score: {trust_score}, Confidence: {confidence}, "
        f"Location: {deal.get('state')}. Is this a genuine arbitrage opportunity? "
        "Reply with VALID or INVALID and one sentence reason."
    )
