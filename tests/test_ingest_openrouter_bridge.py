import os
import sys

import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from webapp.routers import ingest


def test_resolve_openrouter_lane_model_requires_explicit_lane(monkeypatch):
    monkeypatch.delenv("OPENROUTER_LEGACY_DEFAULTING_ENABLED", raising=False)
    monkeypatch.delenv("OPENROUTER_LEGACY_DEFAULT_LANE", raising=False)

    with pytest.raises(ValueError, match="Missing designated_lane"):
        ingest._resolve_openrouter_lane_model({"title": "test deal"}, "deal-1")


def test_resolve_openrouter_lane_model_rejects_mismatched_pair():
    with pytest.raises(ValueError, match="lane/model pair"):
        ingest._resolve_openrouter_lane_model(
            {
                "designated_lane": "premium",
                "openrouter_model": "deepseek/deepseek-v3.3",
            },
            "deal-2",
        )


def test_resolve_openrouter_lane_model_legacy_defaulting_is_opt_in(monkeypatch):
    monkeypatch.setenv("OPENROUTER_LEGACY_DEFAULTING_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_LEGACY_DEFAULT_LANE", "standard")

    lane, model = ingest._resolve_openrouter_lane_model(
        {"openrouter_model": "deepseek/deepseek-v3.2"},
        "deal-3",
    )

    assert lane == "standard"
    assert model == "deepseek/deepseek-v3.2"
