"""nucleo/llm/loop_clients.py — a cache of async HTTP clients, one per EVENT LOOP.

The connection pool inside an async client is bound to the loop that first used it. A process-wide cache keyed
only by endpoint handed a later session — running on another loop, e.g. after the voice moved to another device
and the job restarted — a client whose pool belonged to the previous loop, and every turn failed with
«Event … is bound to a different event loop». Keys here carry the loop, and clients of a loop that has closed are
dropped: their pools can never be used again.
"""
from __future__ import annotations

import asyncio
from typing import Any


def _running_loop():
    """The running loop, or None for a sync caller building a client ahead of any loop."""
    return asyncio.events._get_running_loop()


def _key(key: tuple, loop) -> tuple:
    return key + (id(loop) if loop is not None else 0,)


def get(cache: dict, key: tuple) -> Any | None:
    """The client cached for `key` on the RUNNING loop, or None. Prunes clients of closed loops."""
    for k in [k for k, (_c, lp) in cache.items() if lp is not None and lp.is_closed()]:
        cache.pop(k, None)
    hit = cache.get(_key(key, _running_loop()))
    return hit[0] if hit else None


def put(cache: dict, key: tuple, client: Any) -> None:
    loop = _running_loop()
    cache[_key(key, loop)] = (client, loop)
