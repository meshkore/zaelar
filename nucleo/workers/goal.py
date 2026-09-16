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
    """Measure the declared end state and act on it. Mutates `rec`; never raises."""
    # ── V2-707 F2 · THE HARNESS: a task does not end because the worker SAYS it ended ───────────────
    # The operator, 2026-09-16: «tiene que saber identificar la tarea que ha propuesto el usuario y
    # determinar cuál es la manera de medir el éxito. Y así, después de todo el proceso, podemos ver si
    # hemos llegado a ese punto. Si no hemos llegado, entiendo que es capaz de iterar hasta que lo
    # consiga. Y si hiciéramos ese bucle, probablemente muchas tareas no quedarían huérfanas o a medias.»
    #
    # Until now this seam closed on `rec.ok`, which the worker sets itself, while `_METHOD_BLOCK` asked
    # it in PROSE to verify and iterate — a rail on judgement, and the class of thing `principles.md`
    # says to replace with a mechanism. The condition is still the model's to write (`hbnote goal`: it
    # is the one that understood the errand); the CHECK is the engine's, against the product's own truth.
    #
    # Three answers and only one of them retries. `None` — nothing declared, or unreadable — is NEVER a
    # failure: that is the V2-660 rule kept verbatim, because a wrong «you did not deliver» over a
    # delivered errand is worse than silence, and an unreadable widget must not open a retry loop.
    if rec.status != "cancelled" and not rec.handoff and getattr(rec, "done_when", None):
        try:
            from nucleo import verify as _verify
            met = _verify.check(rec.done_when)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"worker[{rec.task_id}]: el arnés no pudo leer el objetivo ({e!r})")
            met = None
        if met is False:
            falta = "; ".join(_verify.missing(rec.done_when)) or "el objetivo declarado no se cumple"
            if not rec.goal_retried and rec.relay_gen < relay_cap:
                # ITERATE — once, and carrying WHAT IS MISSING, so the relaunch starts from the gap
                # instead of from zero. Same machinery as the context and provider relays above; the
                # cap is what stops «iterate until it works» becoming a worker that never stops.
                rec.goal_retried = True
                try:
                    from nucleo.flash import escalate as _esc
                    _esc.escalate_to_slowbrain(
                        f"{rec.goal}\n\n[ARNÉS] Esto quedó SIN cumplir y es lo que hay que terminar: "
                        f"{falta}. Lo demás ya está hecho: no lo repitas.",
                        context={"src": "goal_unmet", "kind": rec.kind, "trace": rec.trace_id,
                                 "sheet": str(getattr(rec, "sheet", "") or ""),
                                 "surface": str(getattr(rec, "surface", "") or ""),
                                 "done_when": dict(rec.done_when),
                                 "depth": int(rec.depth or 0),
                                 "relay_gen": int(rec.relay_gen or 0) + 1})
                    rec.result_summary = ""       # sin entrega: la retoma el relevo, sin ruido
                    rec.ok = False
                    rec.handoff = f"objetivo sin cumplir → retomada ({falta[:80]})"
                    logger.warning(f"worker[{rec.task_id}]: objetivo SIN cumplir → relanzada · {falta}")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"worker[{rec.task_id}]: no pude relanzar por objetivo: {e}")
                    rec.ok = False
            else:
                # No budget left. Then the operator hears the TRUTH, which is the other half of the
                # same rule: an errand nobody could finish must never be delivered as a finished one.
                rec.ok = False
                rec.result_summary = (f"No he podido dejarlo terminado. Queda: {falta}."
                                      + (f" {rec.result_summary.strip()}" if rec.result_summary.strip() else ""))
        try:
            from voice.observer import emit as _emit
            _emit("task", {True: "✅ arnés: objetivo CUMPLIDO y verificado",
                           False: "❌ arnés: objetivo SIN cumplir",
                           None: "🤷 arnés: objetivo no verificable — no se afirma nada"}[met],
                  text=_verify.describe(rec.done_when),
                  extra={"id": rec.task_id, "met": met, "retried": bool(rec.goal_retried)})
        except Exception:  # noqa: BLE001
            pass


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
