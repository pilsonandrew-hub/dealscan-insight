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


def compute_decision_distribution_drift(events: Iterable[Any], *, window: int = 20) -> DriftDimension:
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
        name="decision_distribution",
        score=score,
        sample_count=sum(counts.values()),
        status=_status(score),
        detail=f"observed={detail_counts}; baseline=pass_verdict_and_passed_closeout; window={window}",
    )


def compute_state_churn_drift(events: Iterable[Any], *, window: int = 20) -> DriftDimension:
    transitions: list[tuple[str | None, str | None]] = []
    visited_targets: list[str | None] = []
    backtrack_count = 0
    for event in _ordered_events(events, window=window):
        if str(getattr(event, "event_type", "")) != "item.state_changed":
            continue
        payload = _payload(event)
        from_state = payload.get("from_state")
        to_state = payload.get("to_state")
        transitions.append((str(from_state) if from_state is not None else None, str(to_state) if to_state is not None else None))
        if to_state in visited_targets:
            backtrack_count += 1
        visited_targets.append(to_state)

    transition_count = len(transitions)
    excess_transition_score = _score_from_excess(transition_count, allowed=4, scale=4)
    backtrack_score = _score_from_excess(backtrack_count, allowed=0, scale=3)
    score = round(min(1.0, max(excess_transition_score, backtrack_score)), 6)
    return DriftDimension(
        name="state_churn",
        score=score,
        sample_count=transition_count,
        status=_status(score),
        detail=(
            f"state_transition_count={transition_count}; repeated_target_state_count={backtrack_count}; "
            f"allowed_transitions=4; window={window}"
        ),
    )


def compute_item_drift(item_id: str, events: Iterable[Any], *, window: int = 20) -> DriftReport:
    event_list = list(events)
    return DriftReport(
        item_id=item_id,
        dimensions=(
            compute_loop_depth_drift(event_list, window=window),
            compute_decision_distribution_drift(event_list, window=window),
            compute_state_churn_drift(event_list, window=window),
        ),
    )
