from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Any


@dataclass(frozen=True)
class DriftDimension:
    name: str
    score: float
    sample_count: int
    status: str
    detail: str


@dataclass(frozen=True)
class DriftReport:
    item_id: str
    dimensions: tuple[DriftDimension, ...]

    @property
    def composite_score(self) -> float:
        if not self.dimensions:
            return 0.0
        return round(sum(dimension.score for dimension in self.dimensions) / len(self.dimensions), 6)


def _payload(event: Any) -> dict[str, Any]:
    raw = getattr(event, "payload_json", None)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _ordered_events(events: Iterable[Any], *, window: int) -> list[Any]:
    if window <= 0:
        raise ValueError("window must be positive")
    ordered = sorted(
        events,
        key=lambda event: (
            str(getattr(event, "created_at", "")),
            str(getattr(event, "event_id", "")),
        ),
    )
    return ordered[-window:]


def _score_from_excess(value: int, *, allowed: int, scale: int) -> float:
    if value <= allowed:
        return 0.0
    return round(min(1.0, (value - allowed) / scale), 6)


def _status(score: float) -> str:
    if score >= 0.75:
        return "block"
    if score >= 0.4:
        return "review"
    if score > 0:
        return "monitor"
    return "clear"


def compute_loop_depth_drift(events: Iterable[Any], *, window: int = 20) -> DriftDimension:
    max_depth = 0
    current_signature: tuple[str, str | None] | None = None
    current_depth = 0
    sample_count = 0

    for event in _ordered_events(events, window=window):
        event_type = str(getattr(event, "event_type", ""))
        payload = _payload(event)
        if event_type == "item.state_changed":
            current_signature = None
            current_depth = 0
            continue
        if event_type != "item.closeout_attempted":
            continue
        if payload.get("result") != "blocked":
            current_signature = None
            current_depth = 0
            continue
        sample_count += 1
        signature = ("blocked_closeout", str(payload.get("failure_code") or "unknown"))
        if signature == current_signature:
            current_depth += 1
        else:
            current_signature = signature
            current_depth = 1
        max_depth = max(max_depth, current_depth)

    score = _score_from_excess(max_depth, allowed=3, scale=3)
    return DriftDimension(
        name="loop_depth",
        score=score,
        sample_count=sample_count,
        status=_status(score),
        detail=f"max_repeated_blocked_closeouts_without_state_advance={max_depth}; allowed=3; window={window}",
    )


def _jensen_shannon_distance(observed: Mapping[str, int], expected: Mapping[str, float]) -> float:
    total = sum(observed.values())
    if total <= 0:
        return 0.0
    keys = set(observed) | set(expected)
    observed_dist = {key: observed.get(key, 0) / total for key in keys}
    expected_total = sum(expected.values()) or 1.0
    expected_dist = {key: expected.get(key, 0.0) / expected_total for key in keys}
    midpoint = {key: (observed_dist[key] + expected_dist[key]) / 2 for key in keys}

    def kl_divergence(left: Mapping[str, float], right: Mapping[str, float]) -> float:
        value = 0.0
        for key in keys:
            if left[key] > 0 and right[key] > 0:
                value += left[key] * math.log2(left[key] / right[key])
        return value

    divergence = (kl_divergence(observed_dist, midpoint) + kl_divergence(expected_dist, midpoint)) / 2
    return round(math.sqrt(divergence), 6)


def compute_decision_drift(events: Iterable[Any], *, window: int = 20) -> DriftDimension:
    counts: dict[str, int] = {}
    for event in _ordered_events(events, window=window):
        event_type = str(getattr(event, "event_type", ""))
        payload = _payload(event)
        if event_type == "item.closeout_attempted":
            result = str(payload.get("result") or "unknown")
            failure_code = payload.get("failure_code")
            key = "closeout:passed" if result == "passed" else f"closeout:{result}:{failure_code or 'none'}"
        elif event_type == "item.verdict_recorded":
            key = f"verdict:{payload.get('verdict') or 'unknown'}"
        else:
            continue
        counts[key] = counts.get(key, 0) + 1

    score = _jensen_shannon_distance(counts, {"closeout:passed": 1.0, "verdict:pass": 1.0}) if counts else 0.0
    detail_counts = ",".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none"
    return DriftDimension(
        name="decision_drift",
        score=score,
        sample_count=sum(counts.values()),
        status=_status(score),
        detail=f"observed={detail_counts}; baseline=pass_verdict_and_passed_closeout; window={window}",
    )


_NON_SUPPORTING_EVIDENCE_URIS = {
    "ace://telegram/intake-source",
    "ace://telegram/parser-decision",
    "ace://autonomy/eligible-direct-work",
    "ace://autonomy/explicit-direct-work-closeout",
    "ace://notification/delivery",
}


def _is_claim_supporting_evidence(payload: Mapping[str, Any]) -> bool:
    return is_claim_supporting_evidence_uri(payload.get("evidence_uri"))


def is_claim_supporting_evidence_uri(evidence_uri: Any) -> bool:
    normalized = str(evidence_uri or "").strip()
    if normalized in _NON_SUPPORTING_EVIDENCE_URIS:
        return False
    return True


def compute_claim_drift(events: Iterable[Any], *, window: int = 20) -> DriftDimension:
    evidence_seen = 0
    supporting_evidence_seen = 0
    pass_verdicts_without_evidence = 0
    passed_closeouts_without_evidence = 0
    sampled_claims = 0

    for event in _ordered_events(events, window=window):
        event_type = str(getattr(event, "event_type", ""))
        payload = _payload(event)
        if event_type == "item.evidence_added":
            evidence_seen += 1
            if _is_claim_supporting_evidence(payload):
                supporting_evidence_seen += 1
            continue
        if event_type == "item.verdict_recorded":
            verdict = str(payload.get("verdict") or "").strip().lower()
            if verdict == "pass":
                sampled_claims += 1
                if supporting_evidence_seen == 0:
                    pass_verdicts_without_evidence += 1
            continue
        if event_type == "item.closeout_attempted" and payload.get("result") == "passed":
            sampled_claims += 1
            if int(payload.get("evidence_count") or 0) <= 0 or supporting_evidence_seen == 0:
                passed_closeouts_without_evidence += 1

    unsupported_claim_count = pass_verdicts_without_evidence + passed_closeouts_without_evidence
    score = round(min(1.0, unsupported_claim_count / max(1, sampled_claims)), 6)
    return DriftDimension(
        name="claim_drift",
        score=score,
        sample_count=sampled_claims,
        status=_status(score),
        detail=(
            f"pass_verdicts_without_prior_evidence={pass_verdicts_without_evidence}; "
            f"passed_closeouts_without_evidence={passed_closeouts_without_evidence}; "
            f"supporting_evidence_events_seen={supporting_evidence_seen}; "
            f"evidence_events_seen={evidence_seen}; window={window}"
        ),
    )


def compute_item_drift(item_id: str, events: Iterable[Any], *, window: int = 20) -> DriftReport:
    event_list = list(events)
    return DriftReport(
        item_id=item_id,
        dimensions=(
            compute_loop_depth_drift(event_list, window=window),
            compute_decision_drift(event_list, window=window),
            compute_claim_drift(event_list, window=window),
        ),
    )
