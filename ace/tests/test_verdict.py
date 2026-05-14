from __future__ import annotations

import unittest

from ace.drift import DriftDimension, DriftReport
from ace.verdict import compute_verdict


def report(score: float) -> DriftReport:
    return DriftReport(
        item_id="item_test",
        dimensions=(DriftDimension("synthetic", score, 1, "clear", "test"),),
    )


class VerdictEngineTests(unittest.TestCase):
    def test_compute_verdict_boundaries_are_strictly_greater_than_thresholds(self) -> None:
        self.assertEqual(compute_verdict(report(0.0)), "ship")
        self.assertEqual(compute_verdict(report(0.15)), "ship")
        self.assertEqual(compute_verdict(report(0.150001)), "monitor")
        self.assertEqual(compute_verdict(report(0.28)), "monitor")
        self.assertEqual(compute_verdict(report(0.280001)), "review")
        self.assertEqual(compute_verdict(report(0.42)), "review")
        self.assertEqual(compute_verdict(report(0.420001)), "block")

    def test_compute_verdict_is_deterministic_for_fixed_report(self) -> None:
        drift_report = report(0.280001)
        self.assertEqual([compute_verdict(drift_report) for _ in range(5)], ["review"] * 5)


if __name__ == "__main__":
    unittest.main()
