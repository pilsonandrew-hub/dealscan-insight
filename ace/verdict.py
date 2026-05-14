from __future__ import annotations

from .drift import DriftReport


VERDICT_SHIP_THRESHOLD = 0.15
VERDICT_MONITOR_THRESHOLD = 0.28
VERDICT_REVIEW_THRESHOLD = 0.42


def compute_verdict(drift_report: DriftReport) -> str:
    """Return the bounded verdict for an item drift report.

    The thresholds are intentionally strict greater-than boundaries:
    scores equal to a boundary remain in the lower-risk verdict bucket.
    """
    composite = drift_report.composite_score
    if composite > VERDICT_REVIEW_THRESHOLD:
        return "block"
    if composite > VERDICT_MONITOR_THRESHOLD:
        return "review"
    if composite > VERDICT_SHIP_THRESHOLD:
        return "monitor"
    return "ship"
