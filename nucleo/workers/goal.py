"""nucleo/workers/goal.py — a task does not end because the worker SAYS it ended (V2-707 F2).

The operator, 2026-09-16:

> «Tiene que saber identificar la tarea que ha propuesto el usuario y determinar cuál es la manera de medir
> el éxito. Y así, después de todo el proceso, podemos ver si hemos llegado a ese punto. Si no hemos
> llegado, entiendo que es capaz de iterar hasta que lo consiga. Y si hiciéramos ese bucle, probablemente
> muchas tareas no quedarían huérfanas o a medias.»

Until this existed, `session._finish` closed on `rec.ok` — which the worker sets itself — while
`dispatch_prompts._METHOD_BLOCK` step 5 asked it in PROSE to «VERIFICA… ITERA». That is a rail on judgement,
the exact class `.meshkore/context/principles.md` says to replace with a mechanism.

The split: **the model writes the condition** (`hbnote goal`; it is the one that understood the errand) and
**the engine checks it** (`nucleo/verify.py`) against the product's own truth. Freedom of reasoning, zero
freedom of consequence — the `party.py` shape again, this time over endings.

Extracted from `_finish` rather than left inline for two reasons that are the same reason: `session.py` sits
under an architecture ceiling, and a rule this load-bearing has to be reachable by a test without standing up
a whole worker session.
"""
from __future__ import annotations

import time as _time

from loguru import logger


def check_and_relay(rec, relay_cap: int) -> None:
    """Measure the declared end state and act on it. Mutates `rec`; never raises.

    V2-776 L3 — the judgement moved to `nucleo/circuit.py`, one place for every ending: the bound is the
    operator's (`genesis.circuit.retries`), its count lives on the spec (persisted on the task row), unreadable
    is a verdict of its own, and a gave-up ending parks ONE retry on his answer. This name stays because
    `session._finish` and the tests drive it."""
    from nucleo import circuit as _circuit
    _circuit.close(rec, relay_cap)


def session_goal(tid, done_when: dict) -> None:
    """HOW SUCCESS IS MEASURED, declared by the worker at the start (`hbnote goal`) — V2-707 F2.

    The operator's own framing: «tiene que saber identificar la tarea que ha propuesto el usuario y
    determinar cuál es la manera de medir el éxito… si no hemos llegado, es capaz de iterar hasta que lo
    consiga». The model writes the condition (it is the one that understood the errand); the ENGINE checks
    it against the product's truth in `_finish`, and that asymmetry is the whole point — a task can no
    longer end because a worker SAID it ended.

    Only ever SET, never cleared by a later report: a worker that re-declares mid-run may refine its
    condition, but a `goal` call with nothing in it must not quietly retire the bar it set for itself."""
    from nucleo import dispatch          # tarde a propósito: el ciclo, y `_SESSIONS` se
    r = dispatch._SESSIONS.get(str(tid))  # re-liga en 26 tests — hay que leer el VIVO
    if r is None or not isinstance(done_when, dict) or not done_when:
        return
    r.done_when = dict(done_when)
    r.last_event_at = _time.time()
    try:
        from nucleo import verify as _verify
        from voice.observer import emit
        extra = {"id": str(tid), "done_when": r.done_when}
        if r.trace_id:
            extra.update(trace=r.trace_id, span=f"worker:{tid}")
        emit("task", "🎯 objetivo declarado — así se medirá si está hecho",
             text=_verify.describe(r.done_when), extra=extra)
    except Exception:
        pass
