from __future__ import annotations

import json
import unittest
from dataclasses import dataclass

from ace.drift import (
    compute_decision_drift,
    compute_claim_drift,
    compute_item_drift,
    compute_loop_depth_drift,
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

    def test_decision_drift_scores_repeated_blocked_claims(self) -> None:
        events = [
            event(index, "item.closeout_attempted", {"result": "blocked", "failure_code": "missing_verdict"})
            for index in range(4)
        ]

        dimension = compute_decision_drift(events)

        self.assertEqual(dimension.name, "decision_drift")
        self.assertEqual(dimension.sample_count, 4)
        self.assertIn(dimension.status, {"review", "block"})
        self.assertGreaterEqual(dimension.score, 0.4)
        self.assertIn("closeout:blocked:missing_verdict=4", dimension.detail)

    def test_claim_drift_flags_ship_verdict_without_evidence(self) -> None:
        events = [
            event(1, "item.verdict_recorded", {"verdict": "ship"}),
            event(2, "item.closeout_attempted", {"result": "passed", "evidence_count": 0}),
        ]

        dimension = compute_claim_drift(events)

        self.assertEqual(dimension.name, "claim_drift")
        self.assertEqual(dimension.sample_count, 2)
        self.assertEqual(dimension.status, "block")
        self.assertIn("unsupported_verdicts_without_prior_evidence=1", dimension.detail)
        self.assertIn("passed_closeouts_without_evidence=1", dimension.detail)

    def test_claim_drift_clears_when_ship_claim_has_evidence(self) -> None:
        events = [
            event(1, "item.evidence_added", {"evidence_text": "proof", "evidence_uri": "ace://proof/business-rule-verification"}),
            event(2, "item.verdict_recorded", {"verdict": "ship"}),
            event(3, "item.closeout_attempted", {"result": "passed", "evidence_count": 1}),
        ]

        dimension = compute_claim_drift(events)

        self.assertEqual(dimension.status, "clear")
        self.assertEqual(dimension.score, 0.0)

    def test_claim_drift_ignores_intake_parser_and_generic_autonomy_metadata_as_pass_support(self) -> None:
        events = [
            event(1, "item.evidence_added", {"evidence_text": "inbound", "evidence_uri": "ace://telegram/intake-source"}),
            event(2, "item.evidence_added", {"evidence_text": "parser", "evidence_uri": "ace://telegram/parser-decision"}),
            event(3, "item.evidence_added", {"evidence_text": "eligible", "evidence_uri": "ace://autonomy/eligible-direct-work"}),
            event(4, "item.evidence_added", {"evidence_text": "generic closeout", "evidence_uri": "ace://autonomy/explicit-direct-work-closeout"}),
            event(5, "item.verdict_recorded", {"verdict": "ship"}),
            event(6, "item.closeout_attempted", {"result": "passed", "evidence_count": 4}),
        ]

        dimension = compute_claim_drift(events)

        self.assertEqual(dimension.name, "claim_drift")
        self.assertEqual(dimension.status, "block")
        self.assertIn("supporting_evidence_events_seen=0", dimension.detail)

    def test_compute_item_drift_returns_three_visible_dimensions(self) -> None:
        events = [
            event(1, "item.evidence_added", {"evidence_text": "proof", "evidence_uri": "ace://proof/business-rule-verification"}),
            event(2, "item.verdict_recorded", {"verdict": "ship"}),
            event(3, "item.closeout_attempted", {"result": "passed", "failure_code": None, "evidence_count": 1}),
        ]

        report = compute_item_drift("item_123", events)

        self.assertEqual(report.item_id, "item_123")
        self.assertEqual([dimension.name for dimension in report.dimensions], [
            "loop_depth",
            "decision_drift",
            "claim_drift",
        ])
        self.assertEqual(report.composite_score, 0.0)


if __name__ == "__main__":
    unittest.main()
