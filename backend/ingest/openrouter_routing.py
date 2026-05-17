"""OpenRouter lane/model routing helpers for alert validation."""

from __future__ import annotations

from typing import Any, Mapping


DEFAULT_OPENROUTER_LANE_MODEL_PAIRS = {
    "premium": "deepseek/deepseek-v3.2",
    "standard": "deepseek/deepseek-v3.2",
}


def normalize_openrouter_route_value(value: Any) -> str:
    return str(value or "").strip().lower()


def env_flag_enabled(env: Mapping[str, str], name: str) -> bool:
    return normalize_openrouter_route_value(env.get(name)) == "true"


def legacy_defaulting_enabled(env: Mapping[str, str]) -> bool:
    return env_flag_enabled(env, "OPENROUTER_LEGACY_DEFAULTING_ENABLED")


def legacy_deepseek_fallback_enabled(env: Mapping[str, str]) -> bool:
    return env_flag_enabled(env, "OPENROUTER_LEGACY_DEEPSEEK_FALLBACK_ENABLED")


def resolve_openrouter_lane_model(
    deal: dict[str, Any],
    *,
    lane_model_pairs: Mapping[str, str] | None = None,
    legacy_defaulting: bool = False,
    legacy_default_lane: str = "premium",
) -> tuple[str, str]:
    lane_model_pairs = lane_model_pairs or DEFAULT_OPENROUTER_LANE_MODEL_PAIRS
    lane = normalize_openrouter_route_value(deal.get("designated_lane"))
    if not lane:
        if not legacy_defaulting:
            raise ValueError("Missing designated_lane for OpenRouter validation")
        lane = normalize_openrouter_route_value(legacy_default_lane or "premium")

    model = normalize_openrouter_route_value(deal.get("openrouter_model"))
    expected_model = lane_model_pairs.get(lane)
    if not expected_model:
        raise ValueError(f"Unsupported OpenRouter lane: {lane}")
    if model and model != expected_model:
        raise ValueError(f"Unsupported OpenRouter lane/model pair: {lane}/{model}")
    return lane, expected_model
