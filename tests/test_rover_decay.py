"""Unit tests for rover scoring helpers."""
import asyncio

import pytest

from backend.rover.heuristic_scorer import DECAY_HALF_LIFE_MS, apply_decay, score_item
from webapp.routers import rover


def test_decay_at_zero():
    """No time elapsed -> weight unchanged."""
    result = apply_decay(1.0, 0, 0)
    assert result == pytest.approx(1.0, rel=1e-6)


def test_decay_at_one_half_life():
    """After one half-life (72h) -> weight ~= 0.5."""
    now_ms = DECAY_HALF_LIFE_MS  # 72h in ms
    result = apply_decay(1.0, 0, now_ms)
    assert result == pytest.approx(0.5, rel=1e-4)


def test_decay_at_two_half_lives():
    """After two half-lives (144h) -> weight ~= 0.25."""
    now_ms = 2 * DECAY_HALF_LIFE_MS  # 144h in ms
    result = apply_decay(1.0, 0, now_ms)
    assert result == pytest.approx(0.25, rel=1e-4)


def test_score_item_accepts_string_numeric_fields():
    """Raw Supabase string numerics should not crash the rover ranker."""
    prefs = {"price_bucket:10-20k": 1.0, "mileage_bucket:30-60k": 1.0}
    row = {
        "current_bid": "15000",
        "mileage": "45000",
        "dos_score": 80,
        "make": "Ford",
        "model": "F-150",
    }

    assert score_item(prefs, row) == pytest.approx(5.7, rel=1e-4)


def test_rover_debug_endpoint_reports_runtime_status(monkeypatch):
    """Debug snapshot should surface the runtime posture that production needs."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("VITE_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("VITE_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setattr(rover, "_redis_client", object(), raising=False)

    result = asyncio.run(rover.rover_debug())

    assert result == {
        "SUPABASE_URL set": "no",
        "SUPABASE_ANON_KEY set": "no",
        "heuristic_scorer import": "ok",
        "redis available": "yes",
    }
