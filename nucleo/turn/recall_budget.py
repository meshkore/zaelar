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


def _publish(reason: str, detail: str, query: str) -> None:
    """A recall the turn gave up on has to be VISIBLE — otherwise it reads as «memory had nothing».

    MEASURED 2026-08-25 over the 223 live session timelines under `.meshkore/logs/sessions/`: of the 27 turns
    that asked for durable recall, **21 came back with `mem_ms: null` and «→ 0 tarjetas del largo plazo»** —
    byte for byte what a turn whose memory genuinely held nothing looks like. The six that did finish took
    556-797 ms against an 800 ms budget, so the distribution sits ON the cutoff instead of comfortably under it.

    `timings['recall_timeout']` was already being set, and node 2.28 asserts it — but NOTHING ever read it. A
    flag with no reader is not a trace: the loss was recorded inside a dict the turn then threw away, and its
    only other witness was a stdlib `logging` line with no timestamp in the middle of the boot noise. So the
    turn lost its durable memory and every surface said «0 cards», which is the reassuring answer.

    Both halves of the observability rule are covered on purpose: the timeline row (what the operator reads
    afterwards) and the amber light (what they see while it is happening). `health_state` is NOT cleared on the
    way out — the key is shared with `memory/` (vector-space mismatch, degraded embeddings) and clearing it here
    would wipe an unrelated warning; it ages out on its own TTL, which is how the rest of `memory/` uses it too.
    """
    try:
        from voice.observer import emit
        emit("memory", "recall sin entregar", role="system", text=detail,
             extra={"module": "nucleo.turn.recall_budget", "reason": reason,
                    "budget_ms": round(budget_s() * 1000), "query": (query or "")[:80]})
    except Exception:  # noqa: BLE001
        pass                                  # observability NEVER breaks a turn
    try:
        from voice import health_state
        health_state.record("memory", "degraded", detail)
    except Exception:  # noqa: BLE001
        pass


async def compose(query: str, timings: dict | None = None) -> tuple[str, list[int]]:
    """`(recall_block, ids)` for `build_flash_system(recall_block=...)`, or `("", [])` when there is nothing to
    ask, the budget ran out, or the retriever failed. Never raises and never blocks the loop."""
    q = (query or "").strip()
    if not q:
        return "", []
    # The abandoned thread gets its OWN dict, and it is merged only if the recall ARRIVED. `wait_for` cancels
    # the WAIT, not the thread: `to_thread` keeps running to completion in the executor and then writes its
    # `mem_query_ms` into whatever dict it was handed — after the turn already gave up on it. Measured
    # 2026-08-25 over the live session timelines: the reply event carried `mem_query_ms` of 2.1 s, 3.5 s and
    # **21 s** with a budget of 800 ms. Those are ghosts: the cost of a recall no turn ever used, reported as
    # if it were the turn's memory latency. Anyone asking «how slow is memory in a live turn» — which is
    # exactly the question that opened V2-311 — was reading the abandoned thread's number.
    propias: dict = {}
    try:
        from nucleo.flash import prompt as _prompt
        got = await asyncio.wait_for(
            asyncio.to_thread(_prompt.compose_recall, q, propias), timeout=budget_s())
        if timings is not None:
            timings.update(propias)       # llegó a tiempo → su coste ES el coste del turno
        return got
    except asyncio.TimeoutError:
        if timings is not None:
            timings["recall_timeout"] = True
        detalle = f"el recall no cerró en {budget_s():.1f}s — el turno sigue SIN memoria durable"
        _publish("timeout", detalle, q)
        _LOG.info(f"recall over budget ({budget_s():.1f}s) — el turno sigue sin recall durable")
    except Exception as e:  # noqa: BLE001
        detalle = f"el recall falló: {str(e)[:120]} — el turno sigue SIN memoria durable"
        _publish("error", detalle, q)
        _LOG.warning(f"recall omitido (el turno sigue): {e}")
    return "", []
