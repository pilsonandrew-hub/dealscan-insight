import pytest

from backend.ingest.openrouter_routing import (
    DEFAULT_OPENROUTER_LANE_MODEL_PAIRS,
    legacy_deepseek_fallback_enabled,
    legacy_defaulting_enabled,
    normalize_openrouter_route_value,
    resolve_openrouter_lane_model,
)


def test_normalize_openrouter_route_value_strips_and_lowercases():
    assert normalize_openrouter_route_value(" Premium ") == "premium"
    assert normalize_openrouter_route_value(None) == ""


def test_legacy_flags_are_true_only_for_true_string():
    assert legacy_defaulting_enabled({"OPENROUTER_LEGACY_DEFAULTING_ENABLED": "true"})
    assert not legacy_defaulting_enabled({"OPENROUTER_LEGACY_DEFAULTING_ENABLED": "1"})
    assert legacy_deepseek_fallback_enabled({"OPENROUTER_LEGACY_DEEPSEEK_FALLBACK_ENABLED": "TRUE"})


def test_resolve_openrouter_lane_model_requires_explicit_lane_by_default():
    with pytest.raises(ValueError, match="Missing designated_lane"):
        resolve_openrouter_lane_model({"title": "test deal"})


def test_resolve_openrouter_lane_model_rejects_unsupported_lane():
    with pytest.raises(ValueError, match="Unsupported OpenRouter lane"):
        resolve_openrouter_lane_model({"designated_lane": "experimental"})


def test_resolve_openrouter_lane_model_rejects_mismatched_pair():
    with pytest.raises(ValueError, match="lane/model pair"):
        resolve_openrouter_lane_model(
            {
                "designated_lane": "premium",
                "openrouter_model": "deepseek/deepseek-v3.3",
            }
        )


def test_resolve_openrouter_lane_model_legacy_defaulting_is_explicit():
    lane, model = resolve_openrouter_lane_model(
        {"openrouter_model": "deepseek/deepseek-v3.2"},
        legacy_defaulting=True,
        legacy_default_lane="standard",
    )

    assert lane == "standard"
    assert model == DEFAULT_OPENROUTER_LANE_MODEL_PAIRS["standard"]
