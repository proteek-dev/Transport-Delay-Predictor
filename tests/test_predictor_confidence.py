from __future__ import annotations

from app.services.predictor import _confidence


def test_confidence_is_zero_for_no_samples() -> None:
    assert _confidence(0) == 0.0


def test_confidence_saturates_below_one() -> None:
    high = _confidence(1000)
    assert 0.99 <= high <= 1.0


def test_confidence_is_monotonic_in_sample_size() -> None:
    values = [_confidence(n) for n in (1, 5, 10, 50, 100, 500)]
    assert values == sorted(values)
