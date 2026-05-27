"""Pricing-confidence ladder for scoring, alerts, and UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Optional

from backend.business_rules.constants import (
    PROXY_ALERT_MIN_CONFIDENCE,
    PROXY_PRICING_ALERT_ALLOWED,
)


class PricingConfidence(str, Enum):
    LIVE_MANHEIM = "live_manheim"
    MARKET_COMP = "market_comp"
    RETAIL_COMP = "retail_comp"
    PROXY_ESTIMATE = "proxy_estimate"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class PricingClassification:
    confidence: PricingConfidence
    maturity: str
    allows_hot_alert: bool
    blocking_reason: Optional[str] = None


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_pricing_confidence(record: Mapping[str, Any]) -> PricingClassification:
    """Classify pricing evidence from an opportunity or score breakdown."""
    breakdown = record.get("score_breakdown")
    if isinstance(breakdown, Mapping):
        merged = {**breakdown, **record}
    else:
        merged = dict(record)

    manheim = _to_float(merged.get("manheim_mmr_mid"))
    if manheim and manheim > 0:
        return PricingClassification(
            confidence=PricingConfidence.LIVE_MANHEIM,
            maturity="live_market",
            allows_hot_alert=True,
        )

    maturity = str(merged.get("pricing_maturity") or "").lower()
    if maturity == "live_market":
        return PricingClassification(
            confidence=PricingConfidence.LIVE_MANHEIM,
            maturity="live_market",
            allows_hot_alert=True,
        )
    if maturity == "market_comp":
        return PricingClassification(
            confidence=PricingConfidence.MARKET_COMP,
            maturity="market_comp",
            allows_hot_alert=True,
        )

    comp_count = int(merged.get("retail_comp_count") or 0)
    comp_conf = _to_float(merged.get("retail_comp_confidence"))
    if comp_count >= 2 and comp_conf and comp_conf >= 0.6:
        return PricingClassification(
            confidence=PricingConfidence.RETAIL_COMP,
            maturity="market_comp",
            allows_hot_alert=True,
        )

    mmr = _to_float(merged.get("mmr_estimated") or merged.get("mmr_ca") or merged.get("mmr"))
    proxy_conf = _to_float(merged.get("mmr_confidence_proxy"))
    if mmr and mmr > 0:
        conf_pct = (proxy_conf * 100.0) if proxy_conf is not None and proxy_conf <= 1.0 else proxy_conf
        allows = PROXY_PRICING_ALERT_ALLOWED and (
            conf_pct is None or conf_pct >= PROXY_ALERT_MIN_CONFIDENCE
        )
        return PricingClassification(
            confidence=PricingConfidence.PROXY_ESTIMATE,
            maturity="proxy",
            allows_hot_alert=allows,
            blocking_reason=None if allows else f"proxy_confidence<{PROXY_ALERT_MIN_CONFIDENCE:.0f}",
        )

    return PricingClassification(
        confidence=PricingConfidence.INSUFFICIENT,
        maturity="unknown",
        allows_hot_alert=False,
        blocking_reason="insufficient_pricing",
    )


def pricing_allows_hot_alert(record: Mapping[str, Any]) -> tuple[bool, Optional[str]]:
    classification = classify_pricing_confidence(record)
    if classification.allows_hot_alert:
        return True, None
    return False, classification.blocking_reason or f"pricing={classification.confidence.value}"
