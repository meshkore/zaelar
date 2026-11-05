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


def _reinforce_delivered(propias: dict) -> None:
    """Reinforcement follows DELIVERY, never computation (V2-311, 2026-08-25).

    `memory.query` reinforced while composing, and composing is not using: of the 27 live recalls measured, 21
    were abandoned when the budget expired **and the thread still finished**, so they increased the weight and
    reset the expiration (`access_count++`, `last_access=now`, `weight+step` — durable write) of pills for
    questions that were never answered with them. The signal that “this is used” was being fed by discarded work.

    The IDs come from `memory.api.reinforce_ids_for`, calculated inside `memory/`: what travels here is the
    MOMENT, not the policy. Reinforcing `ids` wholesale would reinforce the entire package (40 pills instead of
    1), and selective reinforcement would disappear without anything failing — which is how these things get
    lost."""
    ids = propias.pop("recall_reinforce_ids", None) or []
    if not ids:
        return
    try:
        from memory import api as _memory
        _memory.reinforce(list(ids))
    except Exception:  # noqa: BLE001
        pass                                  # reinforcement is a signal, not a guarantee: it never breaks a turn


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
    lex_propias: dict = {}
    lex = None
    try:
        from nucleo.turn.prompt import recall as _prompt
        loop = asyncio.get_running_loop()
        fut = loop.run_in_executor(None, _prompt.compose_recall, q, propias)
        # V2-762 — THE LOCAL HALF, BESIDE IT. The full recall needs an embedding from a remote provider; live it
        # took 1-3.5 s on the operator's engine (2026-09-24) against 0.3-0.5 s measured alone, and every miss
        # left the turn with NO durable memory at all. The lexical channel (FTS5) lives on this machine: 3-27 ms
        # measured. It starts now, and it is what the turn carries when the full one is late — degraded recall,
        # never erased recall. A full one that finishes after the budget is nobody's memory: no turn reads it.
        lex = loop.run_in_executor(None, _lexical, _prompt, q, lex_propias)
        got = await asyncio.wait_for(asyncio.shield(fut), timeout=budget_s())
        _reinforce_delivered(propias)     # delivered to the turn → THAT is using the memory
        if timings is not None:
            timings.update(propias)       # arrived on time → its cost IS the turn's cost
        return got
    except asyncio.TimeoutError:
        if timings is not None:
            timings["recall_timeout"] = True
        got_lex = await _lexical_result(lex)
        if got_lex and got_lex[0]:
            if timings is not None:
                timings["recall_lexical"] = True
            _reinforce_delivered(lex_propias)
            _publish_lexical(q)
            _LOG.info(f"recall over budget ({budget_s():.1f}s) — el turno lleva el recall LÉXICO")
            return got_lex
        detalle = f"el recall no cerró en {budget_s():.1f}s — el turno sigue SIN memoria durable"
        _publish("timeout", detalle, q)
        _LOG.info(f"recall over budget ({budget_s():.1f}s) — el turno sigue sin recall durable")
    except Exception as e:  # noqa: BLE001
        detalle = f"el recall falló: {str(e)[:120]} — el turno sigue SIN memoria durable"
        _publish("error", detalle, q)
        _LOG.warning(f"recall omitido (el turno sigue): {e}")
    return "", []


def _lexical(prompt_mod, query: str, propias: dict) -> tuple[str, list[int]]:
    """The FTS5-only recall (V2-762). Never raises: the local half must not be the thing that fails."""
    try:
        return prompt_mod.compose_recall(query, propias, lexical_only=True)
    except Exception:  # noqa: BLE001
        return "", []


#: How long the turn waits for the LOCAL half once the full one is late. It started at the same moment and
#: measured 3-27 ms, so this is a ceiling for a pathological disk, not a second budget.
_LEXICAL_GRACE_S = 0.15


async def _lexical_result(lex) -> tuple[str, list[int]] | None:
    if lex is None:
        return None
    try:
        return await asyncio.wait_for(asyncio.shield(lex), timeout=_LEXICAL_GRACE_S)
    except Exception:  # noqa: BLE001 — late or failed: the turn goes on with what it has (state + window)
        return None


def _publish_lexical(query: str) -> None:
    """A DEGRADED delivery, not a lost one: a timeline row, and no light. The light is for the turn that went
    without durable memory — that one still records amber in `_publish`. Painting a lexical delivery amber too
    is how the memory box read «no responde» all afternoon over a heart that was writing normally."""
    try:
        from voice.observer import emit
        emit("memory", "recall léxico entregado", role="system",
             text=f"el vectorial no cerró en {budget_s():.1f}s — el turno lleva el recall léxico (local); "
                  "el completo, si llega tarde, se descarta",
             extra={"module": "nucleo.turn.recall_budget", "reason": "lexical",
                    "budget_ms": round(budget_s() * 1000), "query": (query or "")[:80]})
    except Exception:  # noqa: BLE001
        pass
