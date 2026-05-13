import os
import sys
import unittest
from unittest.mock import patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp.routers import ingest


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


if __name__ == "__main__":
    unittest.main()
