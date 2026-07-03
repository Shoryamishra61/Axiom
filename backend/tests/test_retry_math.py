"""Unit tests for retry math — no DB, no fixtures needed."""
import pytest
from worker.retry import compute_delay_ms


def test_fixed_always_same():
    delays = [compute_delay_ms("fixed", i, 1000, 60000) for i in range(1, 6)]
    assert delays == [1000] * 5


def test_linear_grows():
    for attempt in range(1, 6):
        d = compute_delay_ms("linear", attempt, 1000, 60000)
        assert d == attempt * 1000


def test_exponential_capped():
    # Attempt 10: base * 2^9 = 512000ms > max 60000ms → must be capped at max
    d = compute_delay_ms("exponential", 10, 1000, 60000)
    assert d <= 60000


def test_zero_base_returns_zero():
    assert compute_delay_ms("exponential", 3, 0, 60000) == 0


def test_max_delay_zero():
    assert compute_delay_ms("exponential", 3, 1000, 0) == 0
