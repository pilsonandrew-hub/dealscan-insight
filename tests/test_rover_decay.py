"""Unit tests for rover scoring helpers."""
import os
import unittest
from unittest.mock import patch

from backend.rover.heuristic_scorer import DECAY_HALF_LIFE_MS, apply_decay, score_item
from webapp.routers import rover


class RoverDecayTests(unittest.TestCase):
    def test_decay_at_zero(self):
        """No time elapsed -> weight unchanged."""
        result = apply_decay(1.0, 0, 0)
        self.assertAlmostEqual(result, 1.0, places=6)

    def test_decay_at_one_half_life(self):
        """After one half-life (72h) -> weight ~= 0.5."""
        now_ms = DECAY_HALF_LIFE_MS  # 72h in ms
        result = apply_decay(1.0, 0, now_ms)
        self.assertAlmostEqual(result, 0.5, places=4)

    def test_decay_at_two_half_lives(self):
        """After two half-lives (144h) -> weight ~= 0.25."""
        now_ms = 2 * DECAY_HALF_LIFE_MS  # 144h in ms
        result = apply_decay(1.0, 0, now_ms)
        self.assertAlmostEqual(result, 0.25, places=4)

    def test_score_item_accepts_string_numeric_fields(self):
        """Raw Supabase string numerics should not crash the rover ranker."""
        prefs = {"price_bucket:10-20k": 1.0, "mileage_bucket:30-60k": 1.0}
        row = {
            "current_bid": "15000",
            "mileage": "45000",
            "dos_score": 80,
            "make": "Ford",
            "model": "F-150",
        }

        self.assertAlmostEqual(score_item(prefs, row), 5.7, places=4)

    def test_rover_debug_endpoint_reports_runtime_status(self):
        """Debug snapshot should surface the runtime posture that production needs."""
        with patch.dict(os.environ, {}, clear=False):
            for key in (
                "SUPABASE_URL",
                "VITE_SUPABASE_URL",
                "SUPABASE_ANON_KEY",
                "VITE_SUPABASE_ANON_KEY",
            ):
                os.environ.pop(key, None)
            with patch.object(rover, "_redis_client", object()):
                result = rover._rover_debug_snapshot()

        self.assertEqual(
            result,
            {
                "SUPABASE_URL set": "no",
                "SUPABASE_ANON_KEY set": "no",
                "heuristic_scorer import": "ok",
                "redis available": "yes",
            },
        )


if __name__ == "__main__":
    unittest.main()
