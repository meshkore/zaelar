"""Compose the durable recall OFF the event loop, and bounded — the guard voice had and the text channel did not.

Reported by the harness on 2026-08-23 with the cost measured: while memory was slow (a 1.1 GB model download),
`probe.py` blocked the WHOLE engine — every endpoint timed out and the run died as `INFRA: timed out`, naming
nothing about memory. The voice path already survived it.

The defect is stated by `prompt.build_flash_system`'s own docstring: `recall_block` is the real parameter (the
caller composes it outside the loop, on demand — T115/T116) and **`recall_query` is the COMPATIBILITY path for
tests**, which composes it inline. The text channel was using the test path in production, so a slow retriever
became a stalled event loop for everything sharing the process: voice, widgets, the bridges, the API.

Same class as the mirrors F1 retires, and the reason it is worth a module rather than a copied line: this is a
protection, and a protection that exists in one channel and not the other is indistinguishable from not having
it — the failure only shows up on the channel nobody remembered, at the worst possible moment.

Degrading is the POINT, not a fallback: over budget the turn goes on WITHOUT the durable recall (state, recent
window and tools are all still there). A turn that answers with less memory is a worse answer; a turn that never
arrives is a dead agent.
"""
from __future__ import annotations

import asyncio
import logging
import os

_LOG = logging.getLogger("zaelar.turn.recall")

#: Same env var the voice path already reads, so one knob moves both channels — two budgets that drift is how
#: «it works in voice» and «it hangs in text» become two different bug reports for one cause.
_BUDGET_ENV = "ZAELAR_RECALL_BUDGET_MS"
_BUDGET_DEFAULT_MS = 800.0


def budget_s() -> float:
    try:
        return float(os.getenv(_BUDGET_ENV, str(_BUDGET_DEFAULT_MS))) / 1000.0
    except Exception:
        return _BUDGET_DEFAULT_MS / 1000.0


async def compose(query: str, timings: dict | None = None) -> tuple[str, list[int]]:
    """`(recall_block, ids)` for `build_flash_system(recall_block=...)`, or `("", [])` when there is nothing to
    ask, the budget ran out, or the retriever failed. Never raises and never blocks the loop."""
    q = (query or "").strip()
    if not q:
        return "", []
    try:
        from nucleo.flash import prompt as _prompt
        return await asyncio.wait_for(
            asyncio.to_thread(_prompt.compose_recall, q, timings), timeout=budget_s())
    except asyncio.TimeoutError:
        if timings is not None:
            timings["recall_timeout"] = True
        _LOG.info(f"recall over budget ({budget_s():.1f}s) — el turno sigue sin recall durable")
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"recall omitido (el turno sigue): {e}")
    return "", []
