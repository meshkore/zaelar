"""search/hooks.py — the service's few outward calls, as SEAMS the host wires at boot (V2-782 T5.1).

`search/` never imports `nucleo/flash` or `voice`: the turn calls the service, the service never calls the turn
(`tests/search/unit/test_the_search_service_owes_the_turn_nothing.py` is the ratchet). Two things the old
modules did reach for are kept as callables the server sets in its lifespan (`server/boot_halves.py`):

  · `on_chain_failure(kind, detail)` — lights the operator's status light (`voice.health_state.record("search", …)`
    in the engine; nothing in a standalone process).
  · `emit(family, label, **extra)` — the observability bus (`voice.observer.emit`), so the service's own rows
    (route chosen, provider answered) land on the timeline when it runs inside the engine.

Unset, both are no-ops: the service works alone, which is the point of making it a service.
"""
from __future__ import annotations

from typing import Callable

on_chain_failure: Callable[[str, str], None] | None = None
emit: Callable[..., None] | None = None


def chain_failed(kind: str, detail: str) -> None:
    if on_chain_failure is None:
        return
    try:
        on_chain_failure(kind, detail)
    except Exception:  # noqa: BLE001 — a status light must never take a search down
        pass


def note(family: str, label: str, **extra) -> None:
    if emit is None:
        return
    try:
        emit(family, label, **extra)
    except Exception:  # noqa: BLE001
        pass
