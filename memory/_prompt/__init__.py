"""memory/_prompt — what memory RENDERS for a model, apart from what it STORES (audit 2026-08-23, H3).

The facade (`memory.api`) is still THE door — `tests/memory/unit/memory_contract.py` and its ratchet say so — and
re-exports these. `compose_state` (`compose.py`) builds the shared state block; `reads.py` holds the direct reads it
and the turn use. The four surfaces that paint pills to a brain converge in `api.query()`, which applies the
key-shape rule ONCE — that is a RETRIEVAL rule and lives with it, not here.
"""
from .. import state as _state  # noqa: F401 — tests reach the state read through here
from .compose import _ERRAND_KINDS, _RAIL_STATUS, _STATE_RENDERED, compose_state  # noqa: F401
from .reads import (  # noqa: F401
    critical_facts, recent_short, recent_window, salient_long, seconds_since_last_conv, tastes)
