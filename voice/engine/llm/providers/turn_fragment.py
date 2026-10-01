"""The voice turn's PHRASE ACCUMULATOR (V2-096): a fragment that waits for the rest of the sentence instead of
being acted on, and the turn that ends here because of it (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no behaviour change. Every name the block
read from the provider module is read through it (`_p.<name>`), so a patch on the provider still governs it.
A bare `return` of the turn comes back as `{"__return__": True}`, and the caller returns.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p


async def hold_a_fragment(*, brain, emit, first_turn, text) -> dict:
    if not first_turn:
        from nucleo.flash import accumulator as _acc
        if getattr(brain, "_acc", None) is None:
            brain._acc = _acc.Accumulator()
        _n_before = len(brain._acc.fragments)
        _ta = _p.time.time()
        _action, _merged, _why, _dropped = await brain._acc.offer(text)
        _acc_ms = round((_p.time.time() - _ta) * 1000, 1)

        # BUG FIX (2026-08-15, session d4b2bc35): a stale chain that got silently discarded (gap > MAX_GAP_S)
        # used to only ever surface — muted, in `extra`, never spoken — when the CALL AFTER the drop happened
        # to land on "act". The far more common case is that the fragment causing the drop is itself
        # incomplete and falls to "hold" a few lines below, which carried no drop info at all: the operator's
        # words vanished with zero trace anywhere, timeline included. `Accumulator.offer()` now reports
        # `_dropped` on EITHER branch, so this fires every time regardless of what this call goes on to do.
        _speak_drop, _fresh_chain = _p._acc_notice_plan(_action, _dropped, _n_before)
        if _dropped:
            emit("brain", "🕳️ frase anterior descartada por el hueco", text=_dropped[:200], role="system",
                 extra={"cat": "flash", "gap_s": _acc.MAX_GAP_S})
        if _speak_drop:
            _p._spawn(_p._speak_acc_drop(_dropped), "acc_drop_notice")

        if _action == "hold":
            # Callar es la conducta CORRECTA aquí, no un efecto colateral que haya que compensar con un
            # temporizador. Norma del operador, con su propio ejemplo: «si digo "oye, ¿qué tal? ahora vamos
            # a…" y me paro ahí, obviamente esa frase no genera absolutamente nada NI DEBE GENERARLO».
            # Por eso no hay flush por tiempo: un fragmento abandonado se queda sin respuesta a propósito, y
            # las válvulas del acumulador (hueco máximo, nº de trozos, tamaño) son solo para que el buffer no
            # crezca ni contamine una petición posterior que no tiene nada que ver.
            # Y se VE: el trozo retenido y el motivo salen al timeline (⏸), que es la diferencia entre «está
            # esperando a que acabes» y «se ha quedado colgado».
            # 2026-08-15: and if the wait drags on, it's now also HEARD (`_schedule_acc_nudge` below) — the
            # real session's 64s gap had neither signal.
            if _fresh_chain:
                brain._acc_gen += 1
                _p._schedule_acc_nudge(brain, brain._acc_gen)
            emit("brain", "⏸ frase a medias — espero a que termines", text=text[:200], role="system",
                 extra={"cat": "flash", "why": _why, "trozos": len(brain._acc.fragments),
                        "acumulado": brain._acc.text()[:300]})
            return {"__return__": True}

        if _action == "ask":
            # V2-102: layer 2 (the LLM judge) says this looks actionable but is missing something concrete
            # enough that a real assistant would ASK rather than guess or wait in silence. `_why` carries the
            # question text here (repurposed — see `Accumulator.offer`'s docstring). Speaks it exactly like
            # the drop-notice/nudge do (`voice.proactive.speaker()`, never over the operator mid-sentence)
            # and RETURNS — the question IS this turn's response, no FlashBrain dispatch, no memory ingest.
            brain._acc_gen += 1
            brain._acc_trace_id = ""
            emit("brain", "❓ pidiendo aclaración", text=_why[:200], role="system",
                 extra={"cat": "flash", "acumulado": _merged[:300]})
            try:
                from voice import proactive
                speak = proactive.speaker()
                if speak is not None and not proactive.user_speaking():
                    r = speak(_why)
                    if _p.asyncio.iscoroutine(r):
                        await r
            except Exception:
                pass
            return {"__return__": True}

        if _n_before and not _dropped:
            emit("brain", "🧩 frase completada en varios tiempos", text=_merged[:300], role="user",
                 extra={"cat": "flash", "trozos": _n_before + 1, "motivo": _why})
        brain._acc_gen += 1          # cadena resuelta — un aviso pendiente para ella queda obsoleto
        _p._resolve_acc_chain(brain)    # el trace pasa a GRACIA, no se tira (V2-116)
        text = _merged
    _out = locals()
    return {k: _out[k] for k in ('_acc_ms', 'speak', 'text', ) if k in _out}
