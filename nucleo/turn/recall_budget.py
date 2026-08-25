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
import threading

_LOG = logging.getLogger("zaelar.turn.recall")

# The freshness yardstick for a SALVAGED recall, and deliberately not a clock: «no turn has asked since».
# Every `compose()` call is a turn asking, so if the generation moved while the abandoned thread was still
# grinding, the conversation moved — and V2-254 measured what stale memory does to a moved conversation
# (`background_slot_off_topic`: a weather question in Soria hijacked into a plumber in Soria). Seconds would
# be a proxy for that; turns ARE it. Process-global on purpose: one operator, one live conversation per
# process — a turn on any channel means the brain moved on. Stated, not hidden.
_GEN_LOCK = threading.Lock()
_GEN = 0

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
    """El refuerzo sigue a la ENTREGA, nunca al cálculo (V2-311, 2026-08-25).

    `memory.query` reforzaba al componer, y componer no es usar: de los 27 recalls vivos medidos, 21 se
    abandonaban al vencer el presupuesto **y el hilo terminaba igualmente**, así que subían el peso y reseteaban
    la caducidad (`access_count++`, `last_access=now`, `weight+step` — escritura durable) de píldoras por
    preguntas que nunca se contestaron con ellas. La señal de «esto se usa» la alimentaba el trabajo tirado.

    Los ids vienen de `memory.api.reinforce_ids_for`, calculados dentro de `memory/`: aquí viaja el MOMENTO, no
    la política. Reforzar `ids` a pelo sería reforzar el paquete entero (40 píldoras en vez de 1) y el refuerzo
    selectivo desaparecería sin que fallara nada — que es la forma en que estas cosas se pierden."""
    ids = propias.pop("recall_reinforce_ids", None) or []
    if not ids:
        return
    try:
        from memory import api as _memory
        _memory.reinforce(list(ids))
    except Exception:  # noqa: BLE001
        pass                                  # el refuerzo es una señal, no una garantía: nunca rompe un turno


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
    global _GEN
    with _GEN_LOCK:
        _GEN += 1
        mi_gen = _GEN
    propias: dict = {}
    try:
        from nucleo.flash import prompt as _prompt
        # `run_in_executor` + `shield`, not `to_thread` + bare `wait_for`: the timeout must abandon the WAIT
        # without cancelling the FUTURE, or the salvage below never sees a result. (`wait_for` cancels what it
        # wraps; a cancelled task drops the thread's result on the floor — measured while building this.)
        fut = asyncio.get_running_loop().run_in_executor(None, _prompt.compose_recall, q, propias)
        got = await asyncio.wait_for(asyncio.shield(fut), timeout=budget_s())
        _reinforce_delivered(propias)     # entregado al turno → ESO es usar la memoria
        if timings is not None:
            timings.update(propias)       # llegó a tiempo → su coste ES el coste del turno
        return got
    except asyncio.TimeoutError:
        if timings is not None:
            timings["recall_timeout"] = True
        detalle = f"el recall no cerró en {budget_s():.1f}s — el turno sigue SIN memoria durable"
        _publish("timeout", detalle, q)
        _LOG.info(f"recall over budget ({budget_s():.1f}s) — el turno sigue sin recall durable")
        fut.add_done_callback(lambda f: _salvage(f, q, mi_gen, propias))
    except Exception as e:  # noqa: BLE001
        detalle = f"el recall falló: {str(e)[:120]} — el turno sigue SIN memoria durable"
        _publish("error", detalle, q)
        _LOG.warning(f"recall omitido (el turno sigue): {e}")
    return "", []


def _salvage(fut, query: str, asked_gen: int, propias: dict | None = None) -> None:
    """A recall that finished late is the NEXT turn's memory — or nobody's. Never raises.

    V2-311: 21 of 27 live recalls were abandoned at the 800 ms budget, and every one of them FINISHED anyway —
    the thread runs to completion and the composed block used to die in a future nobody watched. The turn paid
    the full cost of the recall 100% of the time and received the result 22% of the time.

    The production tail (measured by memoria-dev on the reply events): 2.1 s, 3.5 s, 21 s. So «the next turn's
    memory» needs a cut, and the cut is «no turn has asked since» — not a clock. If the generation moved, the
    conversation moved, and V2-254 is what stale memory does to a moved conversation.

    TEXT ONLY in the note, and the note JUDGES nothing — findings.py doctrine: it says what arrived and
    explicitly allows ignoring it; whether it still serves the conversation is the brain's call.

    The REINFORCEMENT, on the other hand, does fire here (V2-311 step 3) and only on the branch that actually
    pushes: a late block the next turn carries IS a use. The three exits divide cleanly — delivered in budget,
    delivered late, discarded as stale — and only the two deliveries reinforce. That is the whole point of
    moving the trigger out of `memory.query`: it used to fire on the branch that delivers nothing.
    """
    try:
        if fut.cancelled() or fut.exception():
            return
        block, _ids = fut.result() or ("", [])
        block = (block or "").strip()
        if not block:
            return
        with _GEN_LOCK:
            fresh = (_GEN == asked_gen)
        if not fresh:
            _LOG.info("recall tardío descartado: la conversación ya avanzó (otro turno preguntó)")
            return
        from voice import brain_notes
        brain_notes.push(
            f"[SISTEMA] La memoria durable llegó tarde para la pregunta «{(query or '')[:80]}» del turno "
            f"anterior. Esto es lo que tenía: {block[:600]} — úsalo solo si aún viene al caso; si la "
            f"conversación ya va por otro sitio, ignóralo.")
        _reinforce_delivered(propias or {})   # una entrega tardía que el turno siguiente SÍ lleva es un uso
        _LOG.info("recall tardío entregado como nota para el turno siguiente")
    except Exception:  # noqa: BLE001
        pass                                  # el salvamento es best-effort; nunca rompe nada
