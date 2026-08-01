"""Single injectable wall clock for memory lifecycle logic.

Production reads real Unix time. Tests and simulations can travel through months
without sleeping or monkeypatching Python's global ``time`` module.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import time
from collections.abc import Iterator


_OVERRIDE: ContextVar[int | None] = ContextVar("memory_clock_override", default=None)


def now() -> int:
    override = _OVERRIDE.get()
    return int(time.time()) if override is None else int(override)


@contextmanager
def travel(timestamp: int) -> Iterator[None]:
    """Temporarily expose ``timestamp`` to every memory lifecycle component."""
    token = _OVERRIDE.set(int(timestamp))
    try:
        yield
    finally:
        _OVERRIDE.reset(token)
