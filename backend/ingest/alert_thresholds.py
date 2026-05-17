"""Environment-backed alert threshold configuration."""

from __future__ import annotations

from logging import Logger
from typing import Mapping, Optional

from backend.ingest.alert_gating import AlertThresholds
from backend.ingest.env_utils import env_float


def build_alert_thresholds(
    env: Mapping[str, str],
    *,
    log: Optional[Logger] = None,
) -> AlertThresholds:
    return AlertThresholds(
        min_score=env_float(env, "HOT_DEAL_MIN_SCORE", 70.0, log=log, context="ALERT_GATE"),
        platinum_min_roi_day=env_float(env, "PLATINUM_MIN_ROI_DAY", 75.0, log=log, context="ALERT_GATE"),
        min_bid_headroom=env_float(env, "ALERT_MIN_BID_HEADROOM", 0.0, log=log, context="ALERT_GATE"),
        min_trust_score=env_float(env, "ALERT_MIN_TRUST_SCORE", 0.25, log=log, context="ALERT_GATE"),
        min_confidence=env_float(env, "ALERT_MIN_CONFIDENCE", 55.0, log=log, context="ALERT_GATE"),
    )


def hot_deal_min_score(
    env: Mapping[str, str],
    *,
    log: Optional[Logger] = None,
) -> float:
    return env_float(env, "HOT_DEAL_MIN_SCORE", 70.0, log=log, context="ALERT_GATE")
