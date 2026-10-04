"""The widget half's big closures — `_tag_emit`, `_apply_widget_data`, `_handle_widget_data_tool` — lifted out of
`tool_executor_widget.build` (V2-778 F1, 2026-10-01).

The same code: what each closed over (the turn's state, the injected motor helpers, its sibling closures) is
passed as keyword arguments by the thin closure that stays in `build`, at CALL time — the same late binding a
closure has. Module-level names of `tool_executor_widget` are read through it (`_txw.<name>`).
"""
from __future__ import annotations

from nucleo.flash import tool_executor_widget as _txw


def _tag_emit(action: str, extra: dict, *, _apply_widget_data, _brief, _is_meta_widget_question, _norm_nfkd, _on_tool_call, _request_delete_confirm, _show_guard_target, _show_target_instance, _shown_ids, _spawn, acted, aside, brain, canvas_h, cron_seen, deduped, emit, escalate_req, text) -> None:
    if action in ("deep",):
        # legacy Hermes escalation tag — el cerebro v2 no lo enseña; si aparece, se trata como escalada.
        if escalate_req["v"] is None:
            escalate_req["v"] = (extra.get("request") or "").strip() or text
        return
    if action in ("json_leak_dropped",):
        from voice.tag_protocol import parse_json
        leaked = parse_json(extra.get("text") or "")
        if isinstance(leaked, dict) and isinstance(leaked.get("name"), str):
            a = leaked.get("arguments")
            if isinstance(a, str):
                a = parse_json(a) or {}
            _on_tool_call(leaked["name"], a if isinstance(a, dict) else {})
        elif isinstance(leaked, dict) and leaked.get("request"):
            _on_tool_call("escalate_to_slowbrain", leaked)
        elif isinstance(leaked, dict) and leaked.get("directive"):
            _on_tool_call("set_style_directive", leaked)
        else:
            if escalate_req["v"] is None:
                escalate_req["v"] = text
        return
    if action in ("unknown_tag_dropped",):
        _txw.logger.warning(f"unknown_tag_dropped: {(extra.get('text') or '')[:120]!r}")
        return
    if action == "aparte":
        # V2-657 — sanctioned silence: an in-window turn addressed to somebody else in the room.
        # Handled (no mute backstop, no hollow repair); resolved after the stream.
        aside["v"] = True
        return
    if action == "widget.data":
        # Camino de RESERVA (V2-026): el tag inline sigue soportado, pero el camino PRINCIPAL de las
        # data-ops es la tool `widget_data` (function-calling, fiable). Ambos convergen en _apply_widget_data.
        data = extra.get("data") or {}
        _apply_widget_data(str(extra.get("id") or ""), str(data.get("action") or ""),
                           data.get("payload") or {})
        return
    if action == "delete":
        # BORRAR es cosa del FlashBrain (rápido, determinista) PERO con confirmación (V2-017). Si el
        # modelo emitió el tag en vez de la tool, lo tratamos igual: abre la confirmación (overlay Sí/No
        # en la tarjeta), nunca borra directo.
        _request_delete_confirm(extra.get("id") or "", text)
        acted["widget"] = True
        return
    if action in ("create", "modify", "push"):
        # Boundary duro: crear/modificar/entregar datos a un widget → SlowBrain (escribe código), nunca el
        # Flash. Borrar NO entra aquí (es determinista y lo hace el Flash tras confirmar, arriba).
        _txw.logger.warning(f"nucleo(flash) intentó [[{action}]] — bloqueado, escalando")
        if escalate_req["v"] is None:
            escalate_req["v"] = text
        return
    if action.startswith("cluster."):
        try:
            from connectors import meshkore
            _spawn(meshkore.dispatch_tag(action, extra), "cluster")
        except Exception:
            pass
        return
    if action.startswith("architect."):
        try:
            from connectors import architect
            _spawn(architect.dispatch_tag(action, extra), "architect")
        except Exception:
            pass
        return
    if action.startswith("msg."):
        try:
            from connectors import messaging
            _spawn(messaging.dispatch_tag(action, extra), "messaging")
        except Exception:
            pass
        return
    if action in ("cron.create", "cron.cancel"):
        # Proactividad PROPIA (V2-005): re-cableado al scheduler del loop orquestador (NO al cron de
        # Hermes, que muere en V2-009). Persistido en memory.journal; lo dispara nucleo/loop.py.
        if action == "cron.create":
            cron_seen["v"] = True          # V2-146: el backstop de abajo no duplica lo que ya se pidió
        try:
            from nucleo import scheduler as _sched
            d = extra.get("data") or {}
            if action == "cron.create":
                # V2-214 (impl PARALELA — cablear en AMBOS): las palabras del OPERADOR sobre su propia
                # obligación se envuelven en un «AVÍSALE»; una orden ya dirigida al agente se deja igual.
                from nucleo.flash import router_guards as _rg_cron
                r = _sched.create(
                    _rg_cron.safe_reminder_prompt((d.get("prompt") or d.get("task") or "").strip()),
                    _rg_cron.safe_reminder_schedule((d.get("schedule") or d.get("when") or "").strip(), "", text),  # V2-356
                    name=(d.get("name") or "").strip(), repeat=str(d.get("repeat") or ""))
                emit("cron", "⏰ tarea programada" if r.get("ok") else "⚠️ schedule no reconocido",
                     text=r.get("display") or r.get("error") or "", role="system",
                     extra={"ok": bool(r.get("ok")), "op": action})
            else:
                _sched.cancel(extra.get("name") or d.get("name") or "")
                emit("cron", "🗑️ tarea cancelada", role="system", extra={"ok": True, "op": action})
        except Exception as e:  # noqa: BLE001
            _txw.logger.warning(f"nucleo cron {action} failed: {e}")
        return
    # show / close / move → acción de canvas.
    # GUARD close sin orden (V2-635, espejo del GUARD 2 de stop_worker): «Johnny eres tonto» acabó en
    # un [[close]] que NADIE pidió (34386d8f). Gramática (looks_like_close ya excluye negaciones y
    # narraciones): sin verbo de cerrar EN el turno del operador, el close del modelo es arrastre.
    # `named` = `closes_the_named_card` already told the op inside the card from the card named to close
    # (full18 V7: this guard dropped exactly that close, and the video card stayed over everything).
    # …and neither is any close of a card his words CALL by its name (full18 C6: «close the calendar and the
    # messages» — the verdict read `mensajeria:close`, the chat inside, and this guard kept the card open).
    if (action == "close" and not (extra or {}).get("named")
            and not _txw._direct_action._says_the_name(_txw._bnotes.operator_half(text), str((extra or {}).get("id") or ""))
            and _txw._direct_action.order_is_inside(_brief, str((extra or {}).get("id") or ""))):
        # V2-770 — the order is an action INSIDE the card («ciérrala» over a detail card): not this tag.
        emit("brain", "🛡️ close ignorado — la orden es una acción DENTRO de la tarjeta",
             text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_inside_card"})
        deduped["v"] = True
        return
    if action == "close" and not _txw._closeg.looks_like_close(text):
        # ...unless the shared reader licenses it: Jev independently reads a close order with
        # confidence (T-jev-show-close) — two readers agreeing forgives a grammar miss. A "neither"
        # or unsure verdict keeps the discard below, bit-for-bit.
        _has_order, _order_src = _txw._show_target.close_has_order(text, canvas_h)
        if not _has_order:
            emit("brain", "🛡️ close ignorado — el operador no ha pedido cerrar nada (context-bleed)",
                 text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_without_order"})
            deduped["v"] = True
            return
        emit("brain", "🔓 close licenciado por Jev (la gramática no veía orden, dos lectores de acuerdo)",
             text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_jev_licensed"})
    if action == "show":
        contextual = _show_guard_target(text, brain._window, brain._last_action)
        if contextual:
            extra = {**(extra or {}), "id": contextual}
        # V2-776 — the CARD, as the tool path resolves it: `[[show:results]]` with the monitor sheet open
        # put the bare, empty base beside it (verification 2026-09-27, «Compare them visually»).
        _tid = str((extra or {}).get("id") or "").strip()
        if _tid and "::" not in _tid:
            try:
                _r_tag = _show_target_instance(_tid, _txw._bnotes.operator_half(text), brain._last_spoken or "")
                if not _r_tag.get("ask") and _r_tag.get("id"):
                    extra = {**(extra or {}), "id": _r_tag["id"]}
            except Exception:  # noqa: BLE001
                pass
    # GUARD anti-clutter (2026-07-12): el modelo tiende a emitir [[show:navegador]] al pedir una búsqueda,
    # abriendo el navegador VACÍO ("Nuevo navegador") ADEMÁS de la tarjeta de la tarea → dos/tres cajas de
    # navegador en pantalla. La búsqueda se ve en SU tarjeta (navegador::tN, la abre la tarea sola); el
    # navegador "a pelo" no es una superficie que el operador pida. Lo ignoramos (no rompe: la tarjeta manda).
    if action == "show" and str(extra.get("id") or "").strip().lower() == "navegador":
        emit("brain", "🚫 [[show:navegador]] ignorado (la tarjeta de la tarea es la superficie)", role="system")
        return
    # El modelo a veces emite [[show:X]] cuando el operador solo PREGUNTA por un widget ("¿por qué abriste
    # proyectos?") → abría un widget espurio en mitad de otra conversación (bug 2026-07-12). Una pregunta
    # META sobre una acción pasada NO es una orden de mostrar → ignora el show del modelo.
    # V2-776 — HIS words only (V2-678): the composed turn carries our `[SISTEMA]` notes, and a note about a
    # closed errand read as a meta question and dropped «Show me the monitors» (verification 2026-09-27).
    if action == "show" and _is_meta_widget_question(_norm_nfkd(_txw._bnotes.operator_half(text))):
        emit("brain", "🚫 show ignorado (pregunta META sobre un widget, no una orden)",
             text=str(extra.get("id") or ""), role="system")
        return
    # DEDUP de show por id en el MISMO turno (test post-P1/P2: el modelo emitía [[show:X]] dos veces →
    # doble evento). desktop.show ya es idempotente (reusa la tarjeta), pero no floodeamos el bus/SSE.
    if action == "show":
        _sid = str(extra.get("id") or "").strip().lower()
        if _sid and _sid in _shown_ids:
            return
        _shown_ids.add(_sid)
        extra["reason"] = "turn-order"       # V2-723: the guards above ARE the turn's license
        # V2-770 — showing a card that is ALREADY open, on a turn whose verdict names an action INSIDE it
        # («ábreme la ficha del dentista» → `agenda:open_meeting`), is not the act: the turn stays open to
        # the verdict's completion and the promise repair below.
        if _txw._direct_action.order_is_inside(_brief, _sid):
            emit("brain", "🪟 show de una tarjeta ya abierta — la orden es una acción DENTRO",
                 text=_sid, role="system", extra={"cat": "flash", "kind_diag": "show_inside_card"})
            extra["src"] = "flash"
            emit("widget", action, extra=extra)
            return
    acted["widget"] = True
    if action == "show" and extra.get("id"):
        # V2-776 — WHICH card, as the tool path records it: without the id the after-show repair never ran
        # for a tag show, and «Show me a chart of Apple stock today» left the Markets card EMPTY (demo v7).
        acted["widget_id"] = acted.get("widget_id") or str(extra.get("id"))
    if action == "close":
        acted["closed"] = True                   # el backstop de cierre corto no re-cierra (ver post-stream)
        _txw._canvas_lic.note_operator_close(str(extra.get("id") or ""))   # V2-650b: reopen needs his words
    extra["src"] = "flash"                       # V2-039: procedencia — esta orden viene del FlashBrain
    # REGISTRO DE ÓRDENES DE CANVAS (2026-08-09, petición del operador): el evento se lleva la FRASE que
    # lo provocó. Cuando se abre el widget EQUIVOCADO, la pregunta siempre es «¿de qué texto salió esto?»
    # — y hasta ahora había que reconstruirla saltando al evento `transcript` anterior o abriendo la vista
    # de trazas. Con el texto pegado al propio evento, la fila ya dice orden + objetivo + origen.
    emit("widget", action, text=(text or "").strip()[:160], extra=extra)


def _apply_widget_data(wid: str, action_name: str, payload: dict, ref: str='', *, _apply_widget_data, _brief, _frontend, _request_data_confirm, _spawn, _tag_emit, _turn_op_tasks, acted, brain, data_done, deduped, emit, escalate_req, text) -> None:
    """Ejecuta una data-op según su modo (V2-025): FAST → despacha ya (apply_action / mailbox del owner);
    CONFIRM → abre confirmación con la mutación guardada (se ejecuta al decir "sí"); ESCALATE/None (acción
    no declarada o vía de escape) → escala al SlowBrain. Punto de convergencia de la tool y el tag."""
    from widgets import actions as _wactions
    wid = _txw._data_ops.one_open_instance((wid or "").strip().lower())   # V2-773: a base id → its one open instance
    action_name = (action_name or "").strip()
    # E5 (demo passes 36/42, 2026-09-29): «close my mail» → the model called the card's own `close` VIEW
    # action (back to the chat list) over a SURE close verdict, and the card stayed. The card's close, once.
    if _txw._direct_action.close_op_is_the_card(_brief, action_name):
        _tag_emit("close", {"id": _txw._show_target.close_target(wid)})
        acted["widget"] = True
        emit("brain", "🔁 data-op «close» sobre un cierre seguro — cierra la tarjeta", text=wid, role="system",
             extra={"cat": "flash", "widget": wid, "action": "close"})
        return
    # V2-757 — THE TAIL OF A SENTENCE IS NOT AN ORDER. Here because this is where the tool and the
    # tag converge: a rule installed in one of two branches is this repo's own named way of fixing
    # half a defect. The why and the measurement: `direct_action.a_fragment_moves_nothing`.
    if (_frag_why := _txw._direct_action.a_fragment_moves_nothing(
            _txw._bnotes.operator_half(text), brief=_brief,
            last_reply=getattr(brain, "_last_reply", "") or "")):
        emit("brain", "🧩 trozo de frase — no mueve nada en pantalla",
             text=f"{_txw._bnotes.operator_half(text).strip()[:80]} → {wid}:{action_name}",
             role="system", extra={"cat": "flash", "why": _frag_why,
                                   "id": wid, "action": action_name})
        return
    mode = _frontend.action_mode_now(wid, action_name, payload)   # V2-712: decidido para ESTA llamada
    # TWO READERS DISAGREE ON AN ACT THAT LEAVES (demo pass 2026-09-28, full12 E3): «draft a short reply
    # saying i'll send the meet link…» — the verdict read `mensajeria:draft` at 1.00, the model called
    # `reply`, V2-712 ran it without a question (clear order, resolved target) and a real email went to a
    # third party. V2-754 lets a valid model call beat a disagreeing verdict because a wrong verdict costs
    # a reversible view; for an act of level ≥ sensitive the costs are reversed, so the verdict's action
    # runs instead — and if it cannot, he is asked. Agreement, or no verdict at all, changes nothing.
    if mode == _wactions.FAST and _frontend.at_least_sensitive(wid, action_name):
        _vdis = _txw._direct_action.completes(_brief, wid, model_action=action_name)
        if _vdis:
            emit("brain", "🛑 acto que sale fuera y el veredicto dice otra cosa — corre el veredicto",
                 text=f"{wid}: modelo={action_name} · veredicto={_vdis}", role="system",
                 extra={"cat": "flash", "id": wid, "model": action_name, "verdict": _vdis})
            # the model already wrote the content: it travels to the verdict's action, filtered to what
            # that action declares (a reply's `text` is a draft's `text`)
            _vkeys = set(_txw._direct_action._payload_spec(wid, _vdis))
            _vpay = {k: v for k, v in (payload or {}).items() if k in _vkeys and str(v or "").strip()}
            # …and the recipient his sentence names, which the model's call for the OTHER action did not
            # carry (full18 E3: `reply` has no recipient; the verdict's `forward` needs one)
            _vpay.update(_txw._direct_action.person_fill(wid, _vdis, _vpay, _txw._bnotes.operator_half(text)))
            if _vpay:
                acted["widget"] = True
                _gate_card = wid          # this gate's own, already-decided card
                _apply_widget_data(_gate_card, _vdis, _vpay)
                return
            if _txw._direct_action.complete(_brief, operator_text=_txw._bnotes.operator_half(text), emit=emit,
                                       present=_txw._cvis.present, apply_widget_data=_apply_widget_data,
                                       widget_id=wid, instead_of=action_name, require_order=False):
                acted["widget"] = True
                return
            mode = _wactions.CONFIRM
        elif _txw._direct_action.verdict_elsewhere(_brief, wid):
            # …and an act that leaves which the verdict does not back at all — it surely names an action on
            # ANOTHER card (full19 C2: «find me a free 45 minutes… to talk with rowan» → agenda:find_free,
            # and the model also wrote to Rowan). DROPPED, and the model told: asked instead, the pending
            # question was what «ok book it» answered one turn later — two Telegrams to Rowan he never
            # ordered (demo pass 45, 2026-09-29, C2→C5). An act he did not ask for is not offered either.
            emit("brain", "🛑 acto que sale fuera sin respaldo del veredicto — no se ejecuta",
                 text=f"{wid}:{action_name} · veredicto en otra tarjeta", role="system",
                 extra={"cat": "flash", "id": wid, "model": action_name})
            try:
                from voice import brain_notes as _bn_drop
                _bn_drop.push(f"[SISTEMA] La acción «{action_name}» sobre «{wid}» NO se ejecutó: el operador "
                              f"no la pidió (su orden era otra). No digas que se ha enviado ni lo ofrezcas; "
                              f"si él te lo pide explícitamente, llama entonces a «{action_name}».")
            except Exception:  # noqa: BLE001
                pass
            return

    def _log_dataop(m: str) -> None:
        """REGISTRO DE ACCIONES DE WIDGET (2026-08-09, petición del operador). Hasta ahora una data-op
        («sube el volumen», «maximiza», «marca hecha la tarea») solo dejaba rastro cuando el widget
        GUARDABA (`widget/data` desde `widgets/store.py`), una fila genérica con el id y nada más — sin
        el nombre de la acción, sin quién la pidió y sin la frase. Y encima está clasificada como ruido,
        así que por defecto ni se ve. Aquí se registra la ORDEN en sí: qué acción, sobre qué widget, en
        qué modo (fast/confirm/escalate) y con la FRASE que la originó, para poder atar una acción
        equivocada con el texto exacto que la produjo. La fila del store se queda como está (es el efecto,
        no la orden)."""
        # V2-678 — HIS words, not the composed turn: this row is the audit trail that ties a wrong
        # action to the sentence that produced it, and with the notes glued on it named ours.
        emit("widget", f"data:{action_name}", text=_txw._bnotes.operator_half(text).strip()[:160],
             extra={"id": wid, "action": action_name, "mode": m, "src": "flash", "item": ref,
                    "payload": payload if isinstance(payload, dict) else {}})   # V2-653: the order's content

    mode = _txw._leave_gate.asked_if_leaving(mode, _brief, wid, action_name, emit=emit, payload=payload, said=_txw._bnotes.operator_half(text))
    if mode == _wactions.FAST:
        # GUARD anti context-bleed (round headless V2-038 #1): el modelo a veces RE-emite la data-op del
        # turno ANTERIOR junto a la acción de ESTE ("borra el reloj" arrastró el add_meeting del dentista
        # → cita DUPLICADA). Una mutación IDÉNTICA a la recién ejecutada (<120s), cuyo contenido el turno
        # actual NI MENCIONA, es arrastre → se ignora. Determinista: "apunta otra vez lo del dentista" SÍ
        # menciona el contenido → pasa.
        # V2-650: unless the turn ITSELF orders the production again — «reproduce la lista» /
        # «dale al play» share zero words with {"playlist": "true-blue"}, so payload overlap
        # alone ate three explicit replays of a playback that had failed in silence.
        # V2-707 F0 — and it only guards a mutation that REALLY HAPPENED: the seal is stamped from the
        # RESULT (see `_seal` below), never before dispatching. Until F0 a refused op was remembered as
        # executed and its corrected retry was eaten here — deterministically, because an empty payload
        # joins no values and `_word_overlap` is then 0 against any sentence, so the hatch never opens.
        # The incident, turn by turn: `test_a_refused_action_is_not_remembered_as_done.py`.
        # V2-717: the predicate lives in `data_ops.is_context_bleed` — and a VIEW-op is never a drag.
        if _txw._data_ops.is_context_bleed(brain._last_dataop, wid, action_name, payload, _txw._bnotes.operator_half(text)):
            emit("brain", "🛡️ data-op del turno anterior re-emitida — ignorada (context-bleed)",
                 # …and it SAYS what it threw away. The sibling guards in `_handle_widget_data_tool`
                 # carry the discarded payload; this one carried only «agenda:cancel_meeting», so the
                 # live incident could not be diagnosed from the timeline at all.
                 text=f"{wid}:{action_name}", role="system",
                 extra={"id": wid, "action": action_name, "payload": payload or {}})
            deduped["v"] = True
            return
        # V2-773 — the SAME op the widget just refused, with the SAME payload, is the model re-reading the
        # failure note, not a corrected call: it cannot succeed where it just failed, and it dragged a photo
        # `select` through two chart turns. A corrected retry carries a different payload and runs.
        if _txw._data_ops.is_identical_retry_of_refused(wid, action_name, payload):
            emit("brain", "🛡️ reintento idéntico de una op rechazada — ignorado", text=f"{wid}:{action_name}",
                 role="system", extra={"id": wid, "action": action_name, "payload": payload or {}})
            deduped["v"] = True
            return
        acted["widget"] = True
        data_done["v"] = True
        data_done.setdefault("ops", []).append((wid, action_name))
        _log_dataop("fast")
        try:
            from widgets import provenance as _prov
            _prov.note(wid, "flash")             # V2-039: el cambio de datos que viene = ordenado por FlashBrain
        except Exception:
            pass

        def _seal(ok: bool, _w=wid, _a=action_name, _p=dict(payload or {})) -> None:
            """Remember this mutation ONLY if it happened. A refusal leaves no trace to drag — but it is
            remembered as REFUSED, so the identical re-emit cannot run again (V2-773)."""
            if ok:
                brain._last_dataop = (_w, _a, _p, _txw.time.time())
            else:
                _txw._data_ops.remember_refusal(_w, _a, _p)

        # V2-778 F0-4 — an op that could not start is NOT done: `start_op` says so, and the turn forgets
        # it, so «Done.» never stands over an op that never ran.
        _op_task = _txw._data_ops.start_op(
            wid, action_name, payload or {}, seal=_seal, text=lambda: _txw._bnotes.operator_half(text),
            said=lambda: getattr(brain, "_last_spoken", ""), spawn=_spawn)
        if _op_task is not None:
            _turn_op_tasks.append((wid, _op_task))
        else:
            _ops_left = data_done.get("ops", [])
            if (wid, action_name) in _ops_left:
                _ops_left.remove((wid, action_name))
            data_done["v"] = bool(_ops_left)
        # An action whose output only exists ON SCREEN (`present.mount`, declared or derived) brings its
        # card, through the one door. «Show me a chart of Apple stock» ran markets:show and the card never
        # opened — «Apple's chart is on screen» over an empty canvas (demo run, 2026-09-26). The door
        # refuses an open card, so this never raises one he is reading.
        try:
            from widgets import effects as _fx
            if _fx.carries(wid, action_name, _fx.PRESENT_MOUNT):
                _txw._cvis.present(wid, reason="producer-mount", action=action_name, src="flash", emit=emit)
            # A LENS on a closed card brings the card (V2-773 final pass, C2): «Show me that time in my
            # calendar» ran `agenda:show_day` — a view-op, writes nothing — over a canvas with no agenda
            # on it, and the day changed on a card nobody could see. The model chose to change what
            # THIS card displays, on his order: that is a turn-order for the card. A write is not this
            # (it may run behind the screen on purpose); a lens nobody can see is a silent nothing.
            elif (_fx.carries(wid, action_name, _fx.DATA_READ) and not _txw._cvis.is_open(wid)
                  and not _txw._canvas_lic.closing_turn(_brief, wid)):   # V2-773 E5: a close never brings the card
                _txw._cvis.present(wid, reason="turn-order", action=action_name, src="flash", emit=emit)
        except Exception:
            pass
    elif mode == _wactions.CONFIRM:
        acted["widget"] = True
        _log_dataop("confirm")
        _request_data_confirm(wid, action_name, payload or {})
    else:
        _txw.logger.warning(f"nucleo(flash) widget.data {mode or 'no-declarada'} ({wid}:{action_name}) — escalando")
        _log_dataop("escalate")
        if escalate_req["v"] is None:
            escalate_req["v"] = text


def a_question_the_verdict_keeps_unwritten(wid: str, action: str, operator_text: str, brief) -> bool:
    """A WRITE the model made on a QUESTION (his own «?») while the verdict read, surely, that the turn asks no action
    on the screen. Never raises; anything unreadable runs the model's call as before (CRIT-K2)."""
    try:
        if "?" not in (operator_text or "") and "¿" not in (operator_text or ""):
            return False
        from widgets import effects as _fx
        if not _fx.carries(wid, action, _fx.DATA_WRITE):
            return False
        from nucleo.flash import turn_brief as _tb
        choice, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.8)
        return bool((info or {}).get("used")) and str(choice or "") == "none"
    except Exception:  # noqa: BLE001
        return False


def _handle_widget_data_tool(args: dict, *, _apply_widget_data, _brief, _frontend, _identify, _repeat_repair, _say, _tag_emit, acted, brain, clarify, deduped, emit, escalate_req, text) -> None:
    """Tool `widget_data` (V2-026, camino PRINCIPAL de las data-ops): resuelve el widget y la REFERENCIA a
    item en lenguaje natural a un id REAL (nunca inventado), y despacha por `_apply_widget_data`. Si la
    referencia es ambigua o no existe, PREGUNTA en vez de actuar sobre el item equivocado."""
    from widgets import refs, runtime
    wid = (args.get("widget_id") or "").strip().lower()
    action_name = (args.get("action") or "").strip()
    ref = (args.get("item") or "").strip()
    payload = args.get("payload") if isinstance(args.get("payload"), dict) else {}
    if wid and runtime.get(wid) is None:            # id flojito del modelo → resuélvelo contra el catálogo
        wid = _identify(wid) or _identify(ref) or _identify(text) or wid
    if not wid or not action_name:
        return
    ref = ref or _frontend.payload_ref(wid, action_name, payload, named_only=True)   # demo pass 102 (V2-708)
    # GUARD (2026-07-16): un "abre/muéstrame el widget X" PURO (sin verbo de cambio) NUNCA debe ejecutar un
    # data-op — el modelo cuela una acción inventada ('unhide') o incluso ALUCINA un add_meeting ("abre la agenda" → añadía "Reunión con Axa Seguros"). Se redirige a MOSTRAR la tarjeta (misma ruta que [[show]]).
    from nucleo.flash import router as _router
    # V2-545 — what a pure show order may run is decided by the ACTION, not by the words. The widget
    # declares which of its actions are display-only (`"view": true`); one of those IS the right answer
    # to «ábreme el Telegram» (show_view) or «abre el mensaje de Francisco» (open), so it runs — and the
    # card is shown too, which is the other half of what was asked and removes the card-vs-inside
    # guess. Anything else on a pure show is the invented mutation this guard exists for.
    # The discarded action goes in the event: the previous version logged only the widget id, so three
    # live turns of «ábreme el Telegram» → «Aquí lo tienes» over an unmoved card left no trace of WHAT
    # had been thrown away, and the model was suspected before the guard was.
    if _router.is_pure_show_request(text) and runtime.get(wid) is not None:
        # …salvo que el veredicto nombre esta acción: lo elegido del manifiesto no es inventado (V2-753).
        if _router.show_request_blocks_data_action(text, wid, action_name, payload) \
                and not _txw._direct_action.endorses(_brief, wid, action_name):
            emit("brain", "🪟 'abrir/mostrar' puro → show (no data-op inventada)",
                 text=f"{wid} (descartada {action_name})", role="system",
                 extra={"id": wid, "action": action_name, "payload": payload or {}})
            _tag_emit("show", {"id": wid})
            return
        emit("brain", "🪟 'abrir/mostrar' puro + acción de VISTA → la tarjeta Y la vista",
             text=f"{wid}:{action_name}", role="system",
             extra={"id": wid, "action": action_name, "payload": payload or {}})
        _tag_emit("show", {"id": wid})
    # GUARD cerrar≠data-op (sesión 22:40 2026-07-16, espejo del guard cerrar≠borrar): «Vale, ciérralo» →
    # el modelo ejecutó `widget_data(youtube, mute)` (una data-op DECLARADA) en vez de emitir [[close]] →
    # el vídeo quedó MUTEADO, no cerrado, y el operador tuvo que corregir. Una orden CORTA que es
    # claramente CERRAR (verbo de cerrar, sin verbo de borrar, ≤5 palabras — sin más sustancia que el
    # pronombre/el widget) se redirige DETERMINISTA a la tag de canvas. Una frase larga con "cierra"
    # dentro ("cierra la sesión de spotify del widget") NO entra aquí (pasa a su data-op normal).
    if (_txw._closeg.is_short_close_order(text) and runtime.get(wid) is not None   # V2-713 R3: extraída
            and _txw._direct_action.from_brief(_brief) != (wid, action_name)):   # V2-770: both readers agree
        emit("brain", "🙈 orden corta de CERRAR → close (no data-op)", text=f"{wid} (era {action_name})",
             role="system")
        _tag_emit("close", {"id": wid})
        return
    # GUARD V2-635 (espejo del de [[close]] en _tag_emit): la data-op «close» VACÍA contenido. Sin verbo
    # de cerrar = arrastre, salvo que el veredicto de pantalla nombre esta acción (V2-753, 46dcfcb4).
    if action_name == "close" and not _txw._closeg.dataop_close_licensed(text, wid, brief=_brief, emit=emit):
        deduped["v"] = True
        return
    if _frontend.action_mode(wid, action_name) is None:   # acción no declarada → canvas, reparación Jev o escala
        # GUARD frontera CANVAS vs DATOS (diag sesiones-largas 2026-07-15): a profundidad, el modelo a
        # veces cuela el SHOW/CLOSE como pseudo data-op (`widget_data(clock, action="show")` ante
        # "muéstrame un reloj"). Antes se curaba por el DESVÍO no-declarada→escalate→show-guard (frágil y
        # caro); ahora se mapea DIRECTO a la tag de canvas — misma ruta que [[show]]/[[close]] (dedup,
        # guards anti-clutter/meta, ack "nunca mudo"). Solo si el widget existe de verdad.
        # La DECISIÓN vive en `frontend.resolve_undeclared_action` (compartida con el espejo del probe):
        # verbo de canvas → tag; si no, Jev elige entre las acciones DECLARADAS y la llamada sigue su
        # flujo normal (modos FAST/CONFIRM/ESCALATE intactos); sin veredicto → escala como hoy.
        _kind, _val = _frontend.resolve_undeclared_action(
            wid, action_name, text, brief=_brief, blocking_ok=False)
        if _kind == "canvas":
            emit("brain", "🪟 widget_data con verbo de CANVAS → tag determinista",
                 text=f"{wid}:{action_name}→{_val}", role="system")
            _tag_emit(_val, {"id": wid})
            return
        if _kind == "repair":
            emit("brain", "🔧 acción inventada reparada por Jev → declarada",
                 text=f"{wid}:{action_name}→{_val}", role="system",
                 extra={"id": wid, "action": _val, "invented": action_name})
            action_name = _val
        else:
            if escalate_req["v"] is None:
                escalate_req["v"] = text
            return
    if a_question_the_verdict_keeps_unwritten(wid, action_name, _txw._bnotes.operator_half(text), _brief):
        # Demo pass 93, R2: «When does Anna's vacation start? Show it to me on the calendar.» — screen_action
        # «none» (0.83), a question, and the model WROTE a second «Anna vacation» over the one the INIT made. A
        # write is the costly reading of a question: it is not run, and the card he asked to see is shown.
        emit("brain", "❓ una pregunta no escribe — el veredicto no pedía acción", role="system",
             text=f"{wid}:{action_name}", extra={"cat": "flash", "id": wid, "action": action_name})
        acted["widget"] = True
        _tag_emit("show", {"id": wid})
        return
    res = refs.resolve(wid, action_name, ref, payload, order=_txw._bnotes.operator_half(text))
    # El mis-ruteo por PRONOMBRE SUELTO (o una referencia que no resuelve) sobre un widget que ni
    # está en pantalla ni se nombra: el incidente, la trampa de las acciones de CREAR y la razón de
    # escalar el turno CRUDO están en `frontend.absent_widget_misroute` — la MISMA función que usa
    # el probe, donde vivía copiada y hubo que arreglarla dos veces por separado.
    # An AMBIGUOUS reference found this card's own rows — it is a «which one?», never a worker's job
    # (demo run: «Move it 30 minutes later» over two same-named meetings started a Brain Worker).
    if _frontend.absent_widget_misroute(wid, action_name, ref, resolved=res.ok or res.needs == "ambiguous",
                                        named_widget=_identify(text), payload=payload):
        emit("brain", "🧭 data-op en widget ausente/no-nombrado (pronombre/ítem sin anclar) → escala con contexto",
             role="system", text=f"{wid}:{action_name}:{ref or '∅'}", extra={"needs": res.needs})
        acted["widget"] = True
        if escalate_req["v"] is None:
            escalate_req["v"] = text
        return
    if not res.ok:
        acted["widget"] = True                      # lo ATENDIMOS (preguntando) — no caer a escalate/fallback
        # V2-754 — antes de preguntar «¿cuál?»: si el veredicto nombra OTRA acción de esta tarjeta, la duda
        # era la acción, no el ítem (`play_item` sobre «volver al catálogo» con `show_tab` a 0,96 en el brief).
        if _txw._direct_action.complete(_brief, operator_text=_txw._bnotes.operator_half(text), emit=emit,
                                   present=_txw._cvis.present, apply_widget_data=_apply_widget_data,
                                   widget_id=wid, instead_of=action_name, require_order=False):
            return
        cands = ", ".join(res.candidates[:3])
        clarify["msg"] = (_say().ask_which_item.format(cands=cands) if cands
                          else _say().ask_which_item_bare)
        emit("brain", "❓ referencia de item sin resolver", role="system",
             text=f"{wid}:{action_name}:{ref or '∅'}", extra={"needs": res.needs, "cands": res.candidates[:4]})
        return
    # V2-740 — ¿de QUIÉN era la orden, con dos tarjetas que saben hacer lo mismo? El porqué y la
    # forma del plan, en `frontend.card_decision`; el probe toma la misma por la misma función.
    _cd = _frontend.card_decision(wid, action_name, brief=_brief, ask_phrase=_say().ask_which_item,
                                  payload=payload)
    if _cd["label"]:
        emit("brain", _cd["label"], role="system", text=_cd["text"], extra=_cd["extra"])
    if _cd["ask"]:
        acted["widget"] = True; clarify["msg"] = _cd["ask"]; return
    # V2-754 — una llamada VÁLIDA del modelo corre aunque el veredicto discrepe (a 0,99 habría REINICIADO el
    # vídeo); la discrepancia se registra, que es lo que permitirá medir a quién creer.
    if (_dis := _txw._direct_action.completes(_brief, _cd["card"], model_action=action_name)):
        from nucleo.flash import turn_brief as _tb_vw
        _vw_words = str(_tb_vw.read(_brief, _tb_vw.WORDS_KEY, "")[0] or "")
        if ((_txw._data_ops.repeats_last_view(brain._last_dataop, _cd["card"], action_name, res.payload)
             or _txw._data_ops.a_view_where_the_verdict_acts(_cd["card"], action_name, _dis, _vw_words))
                and _txw._direct_action.complete(_brief, operator_text=_txw._bnotes.operator_half(text), emit=emit,
                                            present=_txw._cvis.present, apply_widget_data=_apply_widget_data,
                                            widget_id=_cd["card"], instead_of=action_name,
                                            require_order=False)):
            emit("brain", "⚖️ el modelo solo miró (o repitió la vista) — completa el veredicto", role="system",
                 text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                 extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
            acted["widget"] = True
            return
        # A QUESTION the verdict is sure of, over a WRITE the model made on the same card (full19 C2: «find me
        # a free 45 minutes…» → verdict find_free 0.91, model add_meeting): the write is the costly mistake
        # — it lands in his calendar — so the answer runs instead. `output.answer` is declared, never guessed.
        # full52 V5: «go back to the list of videos» → verdict youtube:show_tab 0.97, model clear_search (which
        # ERASES the results band), and «put on number five» then had no list. A LENS the verdict is sure
        # of changes nothing; a model call that changes the card's state, over it, is the costly reading.
        if (_txw._data_ops.is_view_op(_cd["card"], _dis) and not _txw._data_ops.is_view_op(_cd["card"], action_name)
                and _txw._direct_action._action_sure(_brief, floor=0.9)
                and _txw._direct_action.complete(_brief, operator_text=_txw._bnotes.operator_half(text), emit=emit,
                                            present=_txw._cvis.present, apply_widget_data=_apply_widget_data,
                                            widget_id=_cd["card"], instead_of=action_name,
                                            require_order=False)):
            emit("brain", "👁 la vista segura gana a un cambio de estado — corre el veredicto", role="system",
                 text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                 extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
            acted["widget"] = True
            return
        from widgets import effects as _fx_q
        if (_fx_q.carries(_cd["card"], _dis, _fx_q.OUTPUT_ANSWER)
                and _fx_q.carries(_cd["card"], action_name, _fx_q.DATA_WRITE)
                and _txw._direct_action._action_sure(_brief)):
            # full51 C2: when the verdict cannot be completed alone (`find_free` needs the length and the
            # afternoon only a model reads), the WRITE still ran — «Call with Rowan» booked at 15:45 over
            # the 15:00 meeting, nobody having asked to book. The write never runs; the verdict's call is
            # asked of the model after the turn (the repeated-view repair pass).
            if not _txw._direct_action.complete(_brief, operator_text=_txw._bnotes.operator_half(text), emit=emit,
                                           present=_txw._cvis.present, apply_widget_data=_apply_widget_data,
                                           widget_id=_cd["card"], instead_of=action_name,
                                           require_order=False):
                _repeat_repair["v"] = (_cd["card"], action_name, _dis)
            emit("brain", "❓ la pregunta gana a la escritura — corre el veredicto", role="system",
                 text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
                 extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
            acted["widget"] = True
            return
        # …and a REPEATED view with a verdict that needs a written payload (full20 E3: `open` again, verdict
        # `forward`): the view runs, and one repair pass after the turn asks for the verdict's call.
        if (_txw._data_ops.repeats_last_view(brain._last_dataop, _cd["card"], action_name, res.payload)   # full37 E2:
                or _txw._data_ops.a_view_where_the_verdict_acts(_cd["card"], action_name, _dis, _vw_words)):  # a lens
            _repeat_repair["v"] = (_cd["card"], action_name, _dis)
        emit("brain", "⚖️ el modelo y el veredicto discrepan — corre el modelo", role="system",
             text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
             extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
    # V2-756 — y lo que el modelo dejó VACÍO se rellena con sus palabras antes de que el widget lo
    # rechace: «Pausa el vídeo. Vuelve al catálogo.» llamó a `show_tab` sin `tab` y volvió
    # `unknown_tab`. Solo AÑADE una clave ausente, y solo por un alias declarado o un número dicho.
    if (_fill := _txw._direct_action.fill_missing(_cd["card"], action_name, res.payload,
                                             _txw._bnotes.operator_half(text))):
        res.payload.update(_fill)
        emit("brain", "🧩 el modelo dejó la clave vacía — la rellenan sus palabras", role="system",
             text=f"{_cd['card']}:{action_name} {_fill}", extra={"cat": "flash", "id": _cd["card"],
             "action": action_name, "fill": _fill})
    _apply_widget_data(_cd["card"], action_name, res.payload, ref)
