"""The post-stream chain SETTLES what is pending: a confirmation the model left unresolved, a worker that was waiting for an answer, a stop nobody called, and the question the turn owes (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/post_stream.py::run` (951 lines) with no behaviour change. Every name the block read
from `post_stream` is read through it (`_pst.<name>`), so a patch on `post_stream` still governs it. The function
takes the chain's locals it read as keyword arguments and returns the ones the rest of `run` reads, only when
bound.
"""
from __future__ import annotations

from nucleo.flash import post_stream as _pst


async def settle_what_is_pending(*, _ans, _ask_waiting, _auth_pending, _brief, _dialog, _filler_audio, _langs, _prev_pending, _r, _resolve_confirm, _router, _shown_ids, acted, aside, brain, clarify, confirm_state, data_done, emit, escalate_req, had_pending_confirm, llm_metrics, music_req, operator_text, search_req, send, speech, spoken_text, style_fired, text, worker_acted) -> dict:
    if had_pending_confirm and not confirm_state["handled"]:
        try:
            verdict = _pst._wconfirm.answers_pending(text)
            if verdict:
                _resolve_confirm(verdict == "yes")
        except Exception:
            pass

    # …y lo mismo para una TAREA irreversible parada por el confirm-gate (V2-126). MISMO clasificador
    # determinista, distinto registro: aquel resuelve una acción de widget, este re-lanza la tarea. Va
    # DESPUÉS y solo si no había confirmación de widget, para que un único «sí» no resuelva dos cosas.
    # Sin esto el gate era un callejón sin salida: nadie ponía nunca `context["confirmed"]`, así que el sí
    # del operador no tenía a qué volver y la acción quedaba parada para siempre sin decirlo.
    # …y la TERCERA puerta con la misma llave (V2-202): el navegador parado en un clic irreversible. Aquélla
    # re-lanza una tarea; ésta desbloquea un clic que está esperando AHORA MISMO dentro del navegador.
    #
    # LAS DOS SE DECIDEN JUNTAS, y ahí estaba el defecto (medido 2026-08-24). Eran dos bloques con el MISMO
    # guarda —`not had_pending_confirm and not worker_acted["v"]`, que mira la puerta de WIDGET—, así que
    # nada registraba que la de tarea acabase de resolverse: con las dos abiertas, un solo «sí» hablado
    # autorizaba LAS DOS. El comentario que había aquí decía «solo si el «sí» no ha resuelto ya otra cosa» y
    # el código no lo hacía; el `probe` sí, o sea que el espejo derivó y la prosa lo tapó. Ahora la
    # precedencia la decide `nucleo/turn/confirm_gates.py`, una vez y para los dos canales.
    if not had_pending_confirm and not worker_acted["v"]:
        from nucleo.turn import confirm_gates as _gates
        _ans = _gates.resolve_all(text, brief=_brief)
        if _ans:   # it answers what is PARKED; an unrelated errand of the same breath still starts (three-tasks)
            _r = _ans.result if isinstance(_ans.result, dict) else {}
            _pst._eot.keep_beside_an_answer(escalate_req, str(_r.get("request") or "") if _ans.gate == "task" else None)
            if _ans.gate == "task":
                emit("brain", "✅ confirmación de tarea resuelta" if _ans.yes
                     else "🚫 tarea irreversible descartada por el operador",
                     text=str(_r.get("request", ""))[:120], role="system", extra={"cat": "flash"})
            else:
                emit("brain", "✅ clic confirmado por el operador" if _ans.yes
                     else "🚫 clic descartado por el operador",
                     text=str(_r.get("task_id", "")), role="system", extra={"cat": "flash"})

    # RED DETERMINISTA V2-038 (§v3·M): precedencia confirm > ask-activo > stop-worker. Si un worker ESPERABA
    # respuesta y el modelo NO llamó answer_worker → enruta el turno como la respuesta (el estado ya lo marcaba).
    # SOLO una "respuesta libre CORTA" (§v3·M): si el turno YA disparó otra acción (widget/búsqueda/escalada/
    # data-op), es largo, o hay un login pendiente (rango superior en la precedencia), NO se lo tragamos como
    # respuesta al worker — el modelo siempre puede enrutar explícito con answer_worker.
    # PRECEDENCIA (2026-07-17, ronda 3): si un worker ESPERA respuesta, un turno corto ES esa respuesta —
    # AUNQUE el modelo haya mis-ruteado a escalate (gpt-4o-mini escaló "sí, el jueves para dos" en vez de
    # answer_worker). Coincide con la doctrina del propio prompt (_flash_layer: "lo que diga el operador es esa
    # respuesta"). Se responde al worker Y se CANCELA la escalada espuria (no abrir una tarea nueva). No aplica
    # si el turno disparó otra acción clara (widget/data/confirm/auth) o es largo (posible tarea nueva genuina).
    if _ask_waiting and worker_acted["v"] != "answer" and not had_pending_confirm \
            and search_req["v"] is None and not acted["widget"] \
            and not data_done["v"] and not _auth_pending and len(text) <= 140:
        try:
            from nucleo import worker_api as _wapi2
            if _wapi2.answer_active_soon(text):
                worker_acted["v"] = "answer"
                escalate_req["v"] = None        # respondía al worker, no pedía tarea nueva → no escalar
                if not spoken_text:
                    spoken_text = "Vale, se lo digo."
                    send(speech.sanitize(spoken_text, drop_metadata=False))
        except Exception:
            pass
    # Backstop de PARADA: hay workers vivos, el operador pidió parar trabajo y el modelo NO llamó stop_worker.
    if worker_acted["v"] not in ("stop",) and escalate_req["v"] is None:
        try:
            from nucleo import dispatch as _disp2
            # V2-773 — «Stop it and close the video widget» is about the CARD the verdict names, never the
            # errands running behind it (two were cancelled on the demo's kickoff).
            if _disp2.has_active() and _router.looks_like_stop_work(text) and not _pst._direct_action.aims_at_a_card(_brief):
                tids = _disp2.cancel_soon(text)
                if tids:
                    worker_acted["v"] = "stop"
                    emit("brain", "🛑 stop worker (backstop determinista)", text=str(tids), role="system")
                    # Un kill SIEMPRE se anuncia por voz (demo 2026-07-14: se mató el worker del widget en
                    # silencio mientras la voz decía "no te he entendido" — incoherente). Si el modelo ya
                    # habló otra cosa, se AÑADE la frase; nunca un kill mudo.
                    _ack = "Vale, lo paro." if not spoken_text else " He parado esa tarea."
                    send(speech.sanitize(_ack, drop_metadata=False))
                    spoken_text = (spoken_text + _ack) if spoken_text else _ack.strip()
        except Exception:
            pass

    # Confirmación abierta este turno → la pregunta la decimos NOSOTROS, gane lo que gane el modelo.
    # Cubre borrado y data-op irreversible (V2-025).
    #
    # ⚠️ Esto exigía `not spoken_text` hasta V2-693, con el razonamiento de «si el modelo ya dijo algo,
    # ya formuló él la pregunta». Medido el 2026-09-14 en su propia sesión: pidió «limpia todo los items
    # de esta semana, menos lo de mañana a las 15h y el inicio de instituto»; el modelo llamó a
    # `agenda:clear_all`, el gate abrió la confirmación REAL («¿Vacío la agenda entera? Es permanente.»)
    # — y como el modelo había hablado, esa pregunta se calló. Lo único que él leyó fue «Clearing this
    # week from your calendar — keeping tomorrow at 15:00…»: una acción NARRADA como hecha que ni
    # siquiera se había despachado, y cuyo alcance real era el calendario entero, no la semana.
    # Su reacción es la medida del coste: «no ha funcionado la orden… necesitamos un sistema estable».
    #
    # Es exactamente la lección que el bloque de `clarify` de abajo ya aprendió el 2026-07-22 y que
    # este no heredó: una señal DETERMINISTA («esto no se ha hecho y necesito tu sí») no puede perder
    # contra una frase que el modelo se inventó. Y sustituye, no acompaña: la frase del modelo habla de
    # algo que no ha pasado, así que dejarla delante es dejar la mentira delante.
    if confirm_state.get("opened") and escalate_req["v"] is None and search_req["v"] is None:
        spoken_text = confirm_state["opened"]
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # Referencia a item sin resolver (V2-026) → preguntamos SIEMPRE, aunque el modelo ya haya dicho algo.
    # Bug real (maratón de testing 2026-07-22): la condición exigía `not spoken_text` — si el turno NO
    # resolvió a qué item se refería (agenda:done:"comprar pan" cuando esa tarea nunca se creó) pero el
    # modelo YA había soltado una frase confiada ("Entendido, marca la tarea como hecha"), esa frase
    # FALSA ganaba y la pregunta real ("¿cuál? no lo tengo claro") nunca llegaba a hablarse — la señal
    # determinista de "no sé a qué te refieres" quedaba silenciada por la propia alucinación del modelo,
    # justo el "nunca mudo" que el comentario original quería garantizar. `clarify["msg"]` solo se fija
    # cuando la referencia genuinamente NO resolvió — es un hecho duro, nunca debe perder frente a lo que
    # el modelo diga por su cuenta.
    if clarify["msg"] and escalate_req["v"] is None and search_req["v"] is None:
        spoken_text = clarify["msg"]
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # Data-op despachada por tool sin frase hablada (el modelo fue directo a la tool) → ack corto (no mudo).
    # V2-038 (test post-P1/P2): dos data-ops seguidas con el MISMO "Hecho." disparaban el loop-detector — se
    # elige una variante que NO repita el último ack hablado (funcional consecutivo = se dice distinto).
    # V2-633: under silent-orders (genesis default, or the operator's own rule) the SUCCESS ack stays
    # unspoken — the visible effect is the answer. Failures still speak: dispatch_and_report (V2-607)
    # and clarify/confirm above are questions and reports, not confirmations, and are not gated.
    try:
        from nucleo import style_policy as _style_ack
        _ack_allowed = _style_ack.confirm_short_actions()
    except Exception:
        _ack_allowed = True
    if data_done["v"] and not spoken_text and _ack_allowed \
            and escalate_req["v"] is None and search_req["v"] is None:
        try:
            from i18n import langs as _langs   # same object as the voice.engine.core shim
            _lg = _langs.current_language()
            _acks = list(getattr(_lg, "data_acks", None) or (_lg.data_ack,))
            _last = _dialog.sanitize_reply(brain._last_spoken or "").strip().lower()
            spoken_text = next((a for a in _acks if a.strip().lower() != _last), _acks[0])
        except Exception:
            spoken_text = "Hecho."
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # Regla de usuario fijada/retirada SIN frase hablada → ack corto (V2-046 A1, visto en el probe: la
    # RETIRADA dejaba el turno MUDO). Nunca mudo al aceptar/quitar una regla.
    if style_fired["v"] and not spoken_text and escalate_req["v"] is None and search_req["v"] is None:
        try:
            from i18n import langs as _langs   # same object as the voice.engine.core shim
            spoken_text = _langs.current_language().data_ack
        except Exception:
            spoken_text = "Vale, lo tengo."
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # SHOW/CLOSE de canvas por tag SIN frase hablada → ack corto (bug 2026-07-13: el modelo emitía [[show:agenda]]
    # sin decir nada → turno MUDO; el operador no oía NI veía nada y creía que estaba roto). Nunca mudo al abrir/
    # cerrar un widget.
    if acted["widget"] and not spoken_text and _ack_allowed \
            and escalate_req["v"] is None and search_req["v"] is None \
            and not confirm_state.get("opened") and not clarify["msg"]:
        try:
            from i18n import langs as _langs   # same object as the voice.engine.core shim
            from nucleo.flash import router_guards as _rg_show2
            _lg_ack = _langs.current_language()
            spoken_text = (_rg_show2.show_ack(_lg_ack, str(acted.get("widget_id") or ""),
                                              chose=str(acted.get("show_chose") or ""))
                           if acted.get("widget_id") else _lg_ack.data_ack)   # a close is not an open (S4)
        except Exception:
            spoken_text = "Aquí lo tienes."
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # V2-660/V2-658 — lo que el turno DEBE, en la costura compartida (`flash/harness_turn.py`, misma
    # llamada que el probe): una afirmación de entrega sobre una hoja VACÍA o una widget_data cortada por
    # el tope escalan con superficie documento, y la voz añade el seguimiento honesto (forma V2-572).
    try:
        _pst._ht.note_shown(_shown_ids, _router.operator_words(operator_text, text), trace=_pst._ht.current_trace())
        _owed = await _pst._ht.rescue(
            spoken_text, data_done=bool(data_done["v"]), turn_text=text,
            metrics=(None if (acted["widget"] or data_done["v"] or search_req["v"] is not None
                              or music_req["v"] is not None) else llm_metrics),
            may_escalate=(escalate_req["v"] is None and not aside["v"]))
        if _owed:
            escalate_req["v"] = _owed["request"]
            escalate_req["surface"][_owed["request"]] = _owed["surface"]
            if _owed["reason"] == _pst._ht.OVERSIZED:
                emit("brain", "🧾 widget_data cortada por el tope → escalada con superficie documento",
                     text=_owed["head"][:120], role="system")
            else:
                _fix = _pst._rg.follow_up_line()
                send(speech.sanitize(_fix, drop_metadata=False))
                spoken_text = (spoken_text + " " + _fix).strip()
    except Exception as _e_h:  # noqa: BLE001
        _pst.logger.warning(f"turn repairs skipped: {_e_h}")

    # Escalada sin texto hablado → frase de espera neutral (V2-029/V2-189): varía turno a turno y esquiva
    # la apertura si un filler ya sonó — en `harness_turn.holding_line`, con su historia.
    if escalate_req["v"] is not None and not spoken_text:
        spoken_text = _pst._rg.holding_line_now(brain._window, _prev_pending,
                                           after_filler=_filler_audio.played_recently())
        send(speech.sanitize(spoken_text, drop_metadata=False))
    _out = locals()
    return {k: _out[k] for k in ('spoken_text', ) if k in _out}
