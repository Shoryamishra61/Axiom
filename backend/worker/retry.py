"""
Retry delay math — fixed, linear, exponential with capped jitter.
Source: AWS Builders' Library (backoff + jitter).

Intentionally zero imports from app code so this module can be unit-tested
without a database connection.
"""
import random


def compute_delay_ms(strategy: str, attempt: int, base_delay_ms: int, max_delay_ms: int) -> int:
    """Return delay in milliseconds before the next retry attempt.

    attempt: 1-indexed (first failure = attempt 1).
    strategy: 'fixed' | 'linear' | 'exponential'

    Fixed and linear delays are exact. Exponential uses capped full-jitter —
    random(0, min(max, base * factor)) — to prevent retry storms.
    """
    if strategy == "fixed":
        raw = base_delay_ms
    elif strategy == "linear":
        raw = base_delay_ms * attempt
    else:  # exponential (default)
        raw = base_delay_ms * (2 ** (attempt - 1))

    capped = min(raw, max_delay_ms)
    if strategy != "exponential":
        return capped
    return random.randint(0, capped) if capped > 0 else 0
