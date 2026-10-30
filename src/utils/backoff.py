"""Exponential backoff and randomized delay helpers."""

import asyncio
import random

import structlog

logger = structlog.get_logger(__name__)


def calculate_jittered_backoff(
    attempt: int,
    base_sec: float = 2.0,
    factor: float = 2.0,
    max_sec: float = 60.0,
) -> float:
    """Calculate exponential backoff with full jitter to avoid thundering herd."""
    calculated = base_sec * (factor**attempt)
    ceiling = min(max_sec, calculated)
    # Full jitter: random uniform between base_sec and ceiling
    delay = random.uniform(base_sec, ceiling)
    return round(delay, 2)


async def polite_sleep(min_sec: float, max_sec: float) -> float:
    """Sleep for a random float duration between min_sec and max_sec."""
    duration = random.uniform(min_sec, max_sec)
    await asyncio.sleep(duration)
    return duration
