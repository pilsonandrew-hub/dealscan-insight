import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp.routers import ingest
from backend.ingest.alert_validation import build_alert_validation_prompt


class IngestOpenRouterBridgeTests(unittest.TestCase):
    def test_resolve_openrouter_lane_model_requires_explicit_lane(self):
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_LEGACY_DEFAULTING_ENABLED": "",
                "OPENROUTER_LEGACY_DEFAULT_LANE": "",
            },
            clear=False,
        ):
            os.environ.pop("OPENROUTER_LEGACY_DEFAULTING_ENABLED", None)
            os.environ.pop("OPENROUTER_LEGACY_DEFAULT_LANE", None)
            with self.assertRaisesRegex(ValueError, "Missing designated_lane"):
                ingest._resolve_openrouter_lane_model({"title": "test deal"}, "deal-1")

    def test_resolve_openrouter_lane_model_rejects_mismatched_pair(self):
        with self.assertRaisesRegex(ValueError, "lane/model pair"):
            ingest._resolve_openrouter_lane_model(
                {
                    "designated_lane": "premium",
                    "openrouter_model": "deepseek/deepseek-v3.3",
                },
                "deal-2",
            )

    def test_resolve_openrouter_lane_model_legacy_defaulting_is_opt_in(self):
        with patch.dict(
            os.environ,
            {
                "OPENROUTER_LEGACY_DEFAULTING_ENABLED": "true",
                "OPENROUTER_LEGACY_DEFAULT_LANE": "standard",
            },
            clear=False,
        ):
            lane, model = ingest._resolve_openrouter_lane_model(
                {"openrouter_model": "deepseek/deepseek-v3.2"},
                "deal-3",
            )

        self.assertEqual(lane, "standard")
        self.assertEqual(model, "deepseek/deepseek-v3.2")

    def test_alert_validation_prompt_requires_concrete_vehicle_truth_fields(self):
        prompt = build_alert_validation_prompt(
            {
                "title": "2024 Toyota Camry",
                "dos_score": 91,
                "pricing_maturity": "market_comp",
                "pricing_source": "marketcheck",
                "vin": "4T1C11AK0RU000001",
                "mileage": 32000,
                "condition_grade": "Good",
            }
        )

        self.assertIn("non-proxy pricing", prompt)
        self.assertIn("valid 17-character VIN", prompt)
        self.assertIn("known positive mileage", prompt)
        self.assertIn("verified condition better than Poor", prompt)
        self.assertIn("VIN: 4T1C11AK0RU000001", prompt)
        self.assertIn("Mileage: 32000", prompt)
        self.assertIn("Condition: Good", prompt)


if __name__ == "__main__":
    unittest.main()
