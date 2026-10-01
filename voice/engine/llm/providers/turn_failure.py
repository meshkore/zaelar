"""The voice turn when the model did not answer: whose fault it was, the relay, the health record and the one
line the operator hears instead of silence (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no behaviour change. Every name the block
read from the provider module is read through it (`_p.<name>`), so a patch on the provider still governs it.
A bare `return` of the turn comes back as `{"__return__": True}`, and the caller returns.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p


async def say_the_turn_failed(*, emit, err_exc, err_text, errored, llm_metrics, send, spec, stalled) -> dict:
    if errored:
        # DEGRADED: sin Hermes al que caer — frase de reserva segura (nunca el error crudo, nunca mudo).
        # CLASIFICA el error (V2-043): SIN SALDO/cuota (credit) · credencial (auth) · caída (outage) — así el
        # diálogo de estado muestra la alerta REAL en vez de un genérico "no responde". Fail-open a "error".
        # UN TURNO ATASCADO NO ES «EL CEREBRO ESTÁ CAÍDO» (fix 2026-08-12). El plazo de silencio reutilizaba esta
        # rama entera, así que un corte aislado —del que la sesión se recupera al turno siguiente— pintaba el ◉ en
        # rojo con «no responde» y gritaba «Cerebro rápido caído». Visto en vivo: el modelo contestaba bien antes y
        # después, y el operador se queda mirando un LLM en rojo que funciona. Se distingue el HECHO (este turno no
        # salió, y eso hay que decirlo) del DIAGNÓSTICO (el proveedor está caído, que es otra cosa y más grave).
        # V2-252 — la DECISIÓN (¿atasco o fallo duro? ¿a qué escalón se releva? ¿queda alguno?) vive ahora en
        # `nucleo/flash/provider_failure.py`, compartida con el canal de TEXTO. Estaba escrita dos veces y esa
        # duplicación mordió tres veces: la última dejó al arnés ocho horas sin poder medir, con el texto
        # devolviendo un 402 en el mismo segundo en que el log decía «relevo a aimlapi-failover». Lo que NO se
        # comparte, a propósito, es lo que cada canal DICE: esta habla, el otro devuelve un objeto.
        # ── V2-758 · WHOSE FAULT IS THIS? ─────────────────────────────────────────────────────────────
        # Asked FIRST, because everything below assumes the provider failed. On 2026-09-23 nine turns were
        # reported to him as «Cerebro rápido caído» while DeepSeek answered perfectly: the real cause was an
        # `UnboundLocalError` of ours. Treating it as the provider's opened a cooldown on a healthy tier,
        # painted the model light, and promoted the stand-in to serve traffic the titular could have
        # served — and no failover can cure a bug of ours, because the same exception fires on the
        # stand-in too. So a fault of ours takes its own exit: no ladder, no light, and the timeline NAMES
        # the defect instead of blaming a provider that was up.
        _mine = ""
        try:
            from nucleo.flash import provider_failure as _pfail
            if _pfail.is_engine_fault(err_exc):
                _mine = _pfail.engine_fault_line(err_exc)
        except Exception:  # noqa: BLE001
            _mine = ""
        if _mine:
            _p.logger.error(f"FALLO INTERNO del turno rápido (el proveedor NO tiene la culpa): {err_text}")
            emit("alert", "Fallo del motor — este turno no salió. El modelo no tiene la culpa.",
                 text=_mine, extra={"cat": "flash", "engine_fault": type(err_exc).__name__})
            emit("error", "nucleo flash brain engine fault", text=_mine)
            try:
                from voice import health_state as _hs_mine
                _hs_mine.record("engine", "bug", _mine)
            except Exception:  # noqa: BLE001
                pass
            send("Uf, se me ha ido un momento. ¿Me lo repites?")
            return {"__return__": True}

        _v = {}
        try:
            from nucleo.flash import provider_chain as _pchain1
            # `fast_client` may ALREADY have relayed inside this very turn and marked both tiers on the
            # way (V2-758). Marking again from here would punish the titular for a failure the stand-in
            # produced — the class of silent mis-attribution V2-307 paid for.
            if not (llm_metrics or {}).get("relayed_to"):
                _v = _pfail.handle(err_text, role=_pchain1.ROLE_VOICE, stalled=bool(stalled), spec=spec)
            else:
                _v = {"relay": None, "dry": _pchain1.pick(_pchain1.ROLE_VOICE) is None}
        except Exception:
            pass
        # RELAY on a HARD failure, not just a slow one (2026-08-15 addendum to V2-094): `note_slow` below
        # already relays a titular that's merely lagging, but a real provider error — no balance, bad
        # credential, an outage — used to just repeat against the same broken tier turn after turn, because
        # `note_failure` was hardcoded to the CLUSTER role. Cooldown is sticky (`pick()` is O(1)), so this
        # only needs to fire once per failure — the NEXT turn already starts on the relay.
        # V2-243/246: el cooldown, el relevo y el «¿queda alguien?» los acaba de resolver `provider_failure`
        # (un atasco REPETIDO cuenta —`note_stall`—; uno aislado es ruido). Aquí solo se lee el veredicto.
        _dry = bool(_v.get("dry")) and not stalled
        if stalled:
            emit("alert", "Un turno se atascó y lo corté — sigo operativo.", text="flash turn stalled")
        elif _dry:
            # V2-676 — the alert carries FACTS, not only prose: `blocking` tells the frontend to put a
            # full-screen notice in the operator's own language with a button into the settings. His
            # ruling: «la voz hay que pararla y bloquear a la gente… que salga en grande… y un botón que
            # abra la configuración». Composition and facts both live in `provider_chain`.
            from nucleo.flash import provider_chain as _pchain2   # ONE import, used twice in this branch
            emit("alert", "Sin proveedor de modelo — no es un tropiezo, no hay a quién preguntar.",
                 text=err_text[:200] or "provider chain exhausted", extra=_pchain2.dry_alert_extra())
        else:
            # V2-758 — the alert CARRIES the cause. It used to travel as the literal string «flash layer
            # error», so the timeline could not say why the brain fell and every diagnosis had to go
            # digging in `server.log`. His first question is always the same: «tengo que saber qué pasa…
            # identificarlo». `_relayed` says whether the stand-in was tried and failed too, which is a
            # different sentence from «the titular failed».
            _relayed_to = (llm_metrics or {}).get("relayed_to") or ""
            emit("alert", "Cerebro rápido caído — turno degradado.",
                 text=(err_text or "flash layer error")[:200],
                 extra={"cat": "flash", "relayed_to": _relayed_to,
                        "relayed_from": (llm_metrics or {}).get("relayed_from") or "",
                        "exc": type(err_exc).__name__ if err_exc is not None else ""})
        emit("error", "nucleo flash brain error")
        # V2-243 — «¿ME LO REPITES?» ES UNA MENTIRA CUANDO NO QUEDA NINGÚN PROVEEDOR. Esa frase es la
        # correcta ante un tropiezo: el siguiente intento puede ir bien. Con la cadena entera seca, el
        # siguiente intento falla igual, y el operador se queda repitiéndose a una máquina que no puede
        # contestarle — sin enterarse de lo único que lo arregla, que es suyo y no del motor.
        # Medido en producción el 2026-08-21: `Insufficient Balance` (DeepSeek, 402) dos veces, «SIN RELEVO
        # disponible», y el canario del arnés MUDO en todos los turnos hasta que él paró de medir.
        # V2-244: la composición (nombrar lo callado + su clave) vive en provider_chain.dry_chain_line.
        _line = "Uf, se me ha ido un momento. ¿Me lo repites?"
        if _dry:
            try:
                _line = _pchain2.dry_chain_line(_pchain2.suppressed_relays())
            except Exception:
                from i18n import langs as _lg_dry
                _line = _lg_dry.current_language().no_model_provider
        send(_line)
        return {"__return__": True}
    _out = locals()
    return {k: _out[k] for k in () if k in _out}
