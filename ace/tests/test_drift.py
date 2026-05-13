from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from ace.drift import (
    compute_decision_distribution_drift,
    compute_item_drift,
    compute_loop_depth_drift,
    compute_state_churn_drift,
)


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    created_at: str
    payload_json: str


def event(index: int, event_type: str, payload: dict[str, object]) -> Event:
    return Event(
        event_id=f"evt_{index:03d}",
        event_type=event_type,
        created_at=f"2026-05-13T00:{index:02d}:00Z",
        payload_json=json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )


class DriftDimensionTests(unittest.TestCase):
    def test_loop_depth_drift_flags_repeated_blocked_closeouts_without_state_advance(self) -> None:
        events = [
            event(index, "item.closeout_attempted", {"result": "blocked", "failure_code": "open_obligations"})
            for index in range(5)
        ]

        dimension = compute_loop_depth_drift(events)

        self.assertEqual(dimension.name, "loop_depth")
        self.assertEqual(dimension.sample_count, 5)
        self.assertIn(dimension.status, {"monitor", "review"})
        self.assertGreater(dimension.score, 0)
        self.assertIn("max_repeated_blocked_closeouts_without_state_advance=5", dimension.detail)

    def test_loop_depth_resets_on_state_advance(self) -> None:
        events = [
            event(1, "item.closeout_attempted", {"result": "blocked", "failure_code": "open_obligations"}),
            event(2, "item.closeout_attempted", {"result": "blocked", "failure_code": "open_obligations"}),
            event(3, "item.state_changed", {"from_state": "APPROVED", "to_state": "CLAIMED_DONE"}),
            event(4, "item.closeout_attempted", {"result": "blocked", "failure_code": "open_obligations"}),
            event(5, "item.closeout_attempted", {"result": "blocked", "failure_code": "open_obligations"}),
        ]

        dimension = compute_loop_depth_drift(events)

        self.assertEqual(dimension.status, "clear")
        self.assertEqual(dimension.score, 0.0)

    def test_decision_distribution_drift_scores_repeated_blocked_claims(self) -> None:
        events = [
            event(index, "item.closeout_attempted", {"result": "blocked", "failure_code": "missing_verdict"})
            for index in range(4)
        ]

        dimension = compute_decision_distribution_drift(events)

        self.assertEqual(dimension.name, "decision_distribution")
        self.assertEqual(dimension.sample_count, 4)
        self.assertIn(dimension.status, {"review", "block"})
        self.assertGreaterEqual(dimension.score, 0.4)
        self.assertIn("closeout:blocked:missing_verdict=4", dimension.detail)

    def test_state_churn_drift_flags_repeated_target_states(self) -> None:
        events = [
            event(1, "item.state_changed", {"from_state": "TRIAGE", "to_state": "APPROVED"}),
            event(2, "item.state_changed", {"from_state": "APPROVED", "to_state": "BLOCKED"}),
            event(3, "item.state_changed", {"from_state": "BLOCKED", "to_state": "APPROVED"}),
        ]

        dimension = compute_state_churn_drift(events)

        self.assertEqual(dimension.name, "state_churn")
        self.assertEqual(dimension.sample_count, 3)
        self.assertEqual(dimension.status, "monitor")
        self.assertIn("repeated_target_state_count=1", dimension.detail)

    def test_compute_item_drift_returns_three_visible_dimensions(self) -> None:
        events = [
            event(1, "item.verdict_recorded", {"verdict": "pass"}),
            event(2, "item.closeout_attempted", {"result": "passed", "failure_code": None}),
        ]

        report = compute_item_drift("item_123", events)

        self.assertEqual(report.item_id, "item_123")
        self.assertEqual([dimension.name for dimension in report.dimensions], [
            "loop_depth",
            "decision_distribution",
            "state_churn",
        ])
        self.assertEqual(report.composite_score, 0.0)


if __name__ == "__main__":
    unittest.main()
