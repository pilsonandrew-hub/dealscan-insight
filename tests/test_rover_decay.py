"""Unit tests for apply_decay in heuristic_scorer."""
import pytest
from backend.rover.heuristic_scorer import apply_decay, DECAY_HALF_LIFE_MS


def test_decay_at_zero():
    """No time elapsed → weight unchanged."""
    result = apply_decay(1.0, 0, 0)
    assert result == pytest.approx(1.0, rel=1e-6)


def test_decay_at_one_half_life():
    """After one half-life (72h) → weight ≈ 0.5."""
    now_ms = DECAY_HALF_LIFE_MS  # 72h in ms
    result = apply_decay(1.0, 0, now_ms)
    assert result == pytest.approx(0.5, rel=1e-4)


def test_decay_at_two_half_lives():
    """After two half-lives (144h) → weight ≈ 0.25."""
    now_ms = 2 * DECAY_HALF_LIFE_MS  # 144h in ms
    result = apply_decay(1.0, 0, now_ms)
    assert result == pytest.approx(0.25, rel=1e-4)
