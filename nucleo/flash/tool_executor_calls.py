"""The executor's `_on_tool_call`, lifted out of `tool_executor.build` (V2-778 F1, 2026-10-01).

`build` was a closure factory of 550 lines and this closure was 517 of them. It is the same code: what it closed
over (the turn's state, the injected motor helpers, its sibling closures) is passed as keyword arguments by the
thin closure that stays in `build`, at CALL time — the same late binding a closure has. Module-level names of
`tool_executor` are read through it (`_tx.<name>`), so patches still govern.
"""
from __future__ import annotations

from nucleo.flash import tool_executor as _tx


def _on_tool_call(name: str, args: dict, *, _apply_widget_data, _brief, _closed_by_tool, _data_ops_hechas, _finish_web_auth, _handle_widget_data_tool, _norm_nfkd, _request_cluster_confirm, _request_delete_confirm, _request_restore_confirm, _resolve_confirm, _router, _say, _says_stop, _show_guard_target, _show_target_instance, _spawn, _start_web_auth, _tag_emit, _tool_fired, _word_overlap, acted, brain, clarify, confirm_state, deduped, emit, escalate_req, images_req, listing_req, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, self, style_fired, text, worker_acted) -> None:
    # NINGUNA tool se ejecuta desde un fragmento superado: mientras el modelo generaba, el operador siguió
    # hablando, así que esta decisión se tomó sobre media frase. Abrir un widget o lanzar un worker con
    # criterios a medias es peor que no hacer nada — el turno completo llega enseguida.
    if self._superseded():
        emit("brain", "🧩 tool ignorada — la frase seguía", text=name, role="system",
             extra={"cat": "flash", "fragment": (getattr(self, "_turn_text", "") or "")[:120]})
        return

    # Recorded AFTER the superseded gate on purpose: a tool that never ran is not something this turn did,
    # so it must not weigh on the end-of-turn flow-merge decision (V2-123, `_merge_target`).
    try:
        brain._turn_tools.add(name)
        brain._turn_calls.append({"name": name, "args": dict(args or {})})
    except Exception:
        pass

    # ESCOTILLA de la selección progresiva (V2-096 F2): el modelo dice que le falta una familia. Se apunta
    # para que el turno la RECOMPONGA con esa familia cargada — un viaje extra MEDIBLE en vez de una
    # capacidad negada en silencio, que es el fallo que de verdad rompe una conversación. No es una tool
    # real: no hace nada, solo marca.
    if name == "need_capability":
        _fam = str((args or {}).get("family") or "").strip()
        if _fam:
            self._need_family = _fam
        emit("brain", "🔓 el modelo pide una familia que se había recortado", text=_fam, role="system",
             extra={"cat": "flash", "family": _fam, "retry": True})
        return

    # Alimenta la capa `recent` del turno siguiente: una conversación que ya iba de widgets no debería
    # perderlos porque el turno siguiente no los nombre.
    try:
        from nucleo.flash import tool_selection as _tsel2
        _fams = _tsel2.families_used([name])
        if _fams:
            prev = list(getattr(brain, "_recent_tool_families", None) or ())
            brain._recent_tool_families = list(dict.fromkeys(list(_fams) + prev))[:3]
    except Exception:
        pass
    if name == "widget_data":
        # Demo pass 82, I1: `imagenes:show` with no pictures is the picture SEARCH (card_commission), not a data-op.
        if images_req["v"] is None:
            from nucleo.flash import card_commission as _cc
            _pic = _cc.picture_search_for_empty_show(str(args.get("widget_id") or ""), str(args.get("action") or ""),
                                                     args.get("payload"), operator_text or text)
            if _pic:
                _tool_fired.add("show_images")
                images_req["v"] = _pic
                _tx._cvis.present("imagenes", reason="turn-order", src="flash", emit=emit)
                emit("brain", "🖼️ fotos → visor imagenes (un show vacío del visor es la búsqueda)",
                     text=_pic["query"][:80], role="system")
                return
        # V2-391 — VARIAS, no una: lo decide `data_ops` (ahí está el porqué y qué sigue bloqueado).
        if not _tx._data_ops.admite_data_op(args, _data_ops_hechas):
            return
        _data_ops_hechas.append(args)     # y `_tool_fired` ya no lo lee nadie: la cuenta es esta
        _handle_widget_data_tool(args)
    elif name == "escalate_to_slowbrain":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_escalate_to_slowbrain(args=args, escalate_req=escalate_req, text=text)
    elif name == "web_search":
        q = (args.get("query") or "").strip() or text
        # TURN-BLEED: el modelo a veces re-emite la búsqueda del turno ANTERIOR junto a la de este (visto:
        # "precio bitcoin" colado en el turno "¿cuándo es el eclipse?"). Nos quedamos con la query que MÁS
        # se parece al turno ACTUAL, no con la primera (que puede ser la vieja) → no buscamos lo que no es.
        if search_req["v"] is None or _word_overlap(q, text) > _word_overlap(search_req["v"], text):
            search_req["v"] = q
    elif name == "search_listings":
        # V2-556 — UNA por turno; la forma de la petición es del módulo (`listing_turn.request_from`).
        listing_req["v"] = listing_req["v"] or _tx._lt.request_from(args, text)
    elif name == "recall":
        # V2-056: el MODELO decide recordar (V2-022 aplicado a la memoria). Se resuelve tras el stream,
        # fuera del event loop; la heurística needs_recall queda como prefetch.
        if recall_req["v"] is None:
            recall_req["v"] = (args.get("query") or "").strip() or text
    elif name == "read_widget":
        # V2-668: el MODELO decide LEER lo que guarda un widget (la hora de una cita con la agenda
        # cerrada). Se resuelve tras el stream, en el turno, sin abrir nada — hermana de recall.
        if read_req["v"] is None:
            read_req["v"] = {"widget_id": (args.get("widget_id") or "").strip(),
                             "question": (args.get("question") or "").strip()}
    elif name == "reopen_task":
        # V2-728: «lo del piso que te dije» — SQLite + un viaje a Jev, así que tras el stream.
        if reopen_req["v"] is None:
            reopen_req["v"] = (args.get("query") or "").strip() or text
    elif name == "reveal_secret":
        # V2-060: el operador pide un SECRETO guardado. Se resuelve tras el stream; el valor NUNCA entra en
        # un prompt del modelo → el provider lo entrega OUT-OF-BAND (voz/pantalla). Aquí solo se captura QUÉ.
        if reveal_req["v"] is None:
            reveal_req["v"] = (args.get("label") or "").strip() or text
    elif name == "play_music":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_play_music(args=args, music_req=music_req)
    elif name == "play_video":
        # V2-045: VÍDEO = widget youtube (VER); una por turno. Cuerpo + LICENCIA V2-635 («Muy bien,
        # señora.» recargaba el que sonaba) en `video_turn.voice_execute` — una impl, ambos canales.
        if "play_video" not in _tool_fired:
            _tool_fired.add("play_video")
            _tx._video_turn.voice_execute(args, text, emit, _apply_widget_data, deduped,
                                      last_reply=brain._last_reply or "", brief=_brief)
    elif name == "show_images":
        # V2-457: FOTOS = visor `imagenes` (VER), tercera hermana de play_music/play_video. Una por
        # turno; se EJECUTA tras el stream (buscar es red) y se dice allí si el modelo calló.
        if "show_images" not in _tool_fired:
            _tool_fired.add("show_images")
            images_req["v"] = _tx._image_turn.request_from([{"name": name, "args": args}])
            _tx._cvis.present("imagenes", reason="turn-order", src="flash", emit=emit)
            emit("brain", "🖼️ fotos → visor imagenes", text=images_req["v"]["query"][:80], role="system")
    elif name == "show_widget":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_show_widget(
            args=args, _brief=_brief, _router=_router, _say=_say, _show_guard_target=_show_guard_target,
            _show_target_instance=_show_target_instance, _tag_emit=_tag_emit, _tool_fired=_tool_fired, acted=acted,
            brain=brain, clarify=clarify, deduped=deduped, emit=emit, escalate_req=escalate_req, text=text)
    elif name == "show_panel":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_show_panel(
            args=args, _router=_router, _tool_fired=_tool_fired, acted=acted, emit=emit, operator_text=operator_text,
            text=text)
    elif name == "manage_widget_alias":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_manage_widget_alias(
            args=args, _say=_say, _tool_fired=_tool_fired, acted=acted, clarify=clarify, emit=emit, text=text)
    elif name == "close_widget":
        # Each CARD once, not the tool once: «close the calendar and the messages» may be two calls.
        if _tx._show_target.close_dispatch(args, _tag_emit, emit, text=_tx._bnotes.operator_half(text),
                                       done=_closed_by_tool):
            _tool_fired.add("close_widget")
            acted["widget"] = True
    elif name == "fullscreen_widget":
        # BUG 2026-07-23: sin tool, el modelo confabulaba éxito. Cuerpo (resolución V2-609 + licencia y
        # dirección V2-635: «pausa el vídeo» disparaba fullscreen; «minimiza» ya no cae en el toggle al
        # revés) en `show_target.fullscreen_dispatch` — una decisión, ambos canales.
        if "fullscreen_widget" not in _tool_fired:
            _tool_fired.add("fullscreen_widget")
            _tx._show_target.fullscreen_dispatch(args, text, _tag_emit, emit, deduped)
    elif name == "arrange_canvas":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_arrange_canvas(_tool_fired=_tool_fired, acted=acted, emit=emit)
    elif name == "reply_message":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_reply_message(
            args=args, _apply_widget_data=_apply_widget_data, _say=_say, _tool_fired=_tool_fired, clarify=clarify)
    elif name == "delete_widget":
        _request_delete_confirm((args.get("widget_id") or "").strip(), text)
    elif name == "restore_widget":
        _request_restore_confirm((args.get("widget_id") or "").strip(), text)
    elif name == "confirm_widget_delete":
        confirm_state["handled"] = _resolve_confirm(bool(args.get("confirmed")))
    elif name == "set_style_directive":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_set_style_directive(
            args=args, _spawn=_spawn, brain=brain, emit=emit, style_fired=style_fired, text=text)
    elif name == "authenticate_web":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_authenticate_web(
            args=args, _start_web_auth=_start_web_auth, emit=emit, escalate_req=escalate_req, text=text)
    elif name == "login_done":
        _finish_web_auth()
    elif name == "connect_cluster":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_connect_cluster(args=args, _request_cluster_confirm=_request_cluster_confirm)
    elif name == "cluster_send":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_cluster_send(args=args, _spawn=_spawn, emit=emit)
    elif name == "set_cluster_objective":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_set_cluster_objective(args=args, _say=_say, _spawn=_spawn, clarify=clarify, emit=emit)
    elif name == "send_to_worker":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_send_to_worker(args=args, emit=emit, worker_acted=worker_acted)
    elif name == "stop_worker":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_stop_worker(
            args=args, _norm_nfkd=_norm_nfkd, _say=_say, _says_stop=_says_stop, clarify=clarify, emit=emit, text=text,
            worker_acted=worker_acted)
    elif name == "answer_worker":
        # V2-778 F1 — the body lives in `nucleo/flash/tool_executor_calls.py`; this branch passes what it reads.
        return _t_answer_worker(args=args, emit=emit, worker_acted=worker_acted)


# V2-778 F1 — the `escalate_to_slowbrain` arm of `_on_tool_call`, moved verbatim.
def _t_escalate_to_slowbrain(*, args, escalate_req, text):
    req = (args.get("request") or "").strip() or text
    # V2-227: la superficie declarada se guarda POR petición. Solo se puebla desde la llamada real
    # del modelo; los caminos de respaldo de este fichero (el tag filtrado, los backstops) no la
    # conocen y dejan que `surfaces.resolve()` la derive del kind — que es para lo que existe.
    _sf = str(args.get("surface") or "").strip()
    if _sf:
        escalate_req["surface"][req] = _sf
    escalate_req.setdefault("done_when", {})[req] = args.get("done_when")   # V2-776 L1: the spec rides
    if escalate_req["v"] is None:
        escalate_req["v"] = req
    elif (args.get("request") or "").strip():
        # Una 2ª (3ª…) llamada del MODELO en el mismo turno = otra tarea. Se exige `request` propio:
        # sin él la llamada cae a `text`, que es la MISMA frase, y duplicaríamos la tarea principal.
        # El tope existe porque el destinatario es un pool de workers reales (`dispatch._max_parallel`,
        # 3 por defecto): un modelo que se atasque enumerando no debe poder abrir una tarea por ítem.
        if len(escalate_req["more"]) < 2 and req not in escalate_req["more"] and req != escalate_req["v"]:
            escalate_req["more"].append(req)


# V2-778 F1 — the `play_music` arm of `_on_tool_call`, moved verbatim.
def _t_play_music(*, args, music_req):
    # V2-041: una acción de música por turno. Ruta LIGERA como web_search: se resuelve tras el stream,
    # FUERA del event loop.
    _mq = {"query": (args.get("query") or "").strip(),
           "action": (args.get("action") or "play").strip().lower()}
    if music_req["v"] is None:
        music_req["v"] = _mq
    else:
        # COLAPSO determinista de VARIAS play_music en un turno (V2-047 F4, sesión 23:15: el modelo
        # no-razonador emite play Y queue a la vez para «luego pon X» → si gana el 'play' reproduce en
        # vez de encolar). Con música YA sonando, un `queue` MANDA sobre un `play` (añades, no
        # reemplazas); sin nada sonando, se queda la primera. Sobre el ESTADO del rail + la acción que
        # el propio modelo eligió — no una tabla de palabras.
        try:
            from nucleo import rails as _rails_m
            _playing = _rails_m.get("music.playing") is not None
        except Exception:
            _playing = False
        if _playing and _mq["action"] == "queue" and music_req["v"].get("action") != "queue":
            music_req["v"] = _mq
        # BUG real 2026-07-23: "pon música de Queen y súbele el volumen al máximo" — el modelo emite
        # play(Queen) + volume_up en el MISMO turno; antes la 2ª se tiraba en silencio mientras el
        # modelo SÍ decía "subo el volumen" (confabulación: la voz prometía algo que el código no
        # hacía). Una 2ª llamada de CONTROL puro (sin query, verbo de ajuste) tras un play/queue NO se
        # descarta: se guarda como `followup` y se ejecuta EN SECUENCIA tras el play (abajo).
        elif (not _mq["query"] and _mq["action"] in
              ("volume_up", "volume_down", "pause", "resume", "stop", "next", "previous")):
            music_req["followup"] = _mq


# V2-778 F1 — the `show_widget` arm of `_on_tool_call`, moved verbatim.
def _t_show_widget(*, args, _brief, _router, _say, _show_guard_target, _show_target_instance, _tag_emit, _tool_fired, acted, brain, clarify, deduped, emit, escalate_req, text):
    # MOSTRAR un widget (incl. JUEGOS) como TOOL de 1ª clase — más fiable que el tag [[show]] cuando la
    # palabra colisiona con play_music/play_video ('juega al snake'). Converge en la MISMA ruta de canvas
    # ([[show:id]], dedup/idempotente). Resuelve el id: exacto del catálogo o fuzzy con runtime.identify.
    if "show_widget" not in _tool_fired:
        _tool_fired.add("show_widget")
        _wid = (args.get("widget_id") or "").strip()
        # GUARD (V2-567): una orden de CERRAR no se contesta con un show. Medido en vivo: «Cierra los
        # contactos» → el modelo llamó show_widget(mensajeria); contactos lo cerró el backstop, así que
        # UNA orden produjo DOS mutaciones. El probe ya tenía la regla escrita («un canvas:show ESPURIO
        # en un turno de cerrar SÍ debe corregirse») y este canal no la aplicaba. El show se descarta y
        # el backstop de cierre de más abajo hace el cierre — una orden, una mutación. V2-750 — AND THE GRAMMAR ONLY PROPOSES BELOW. Measured (session b41925f6): «vamos a HACER una cosa, ábreme el WIDGET de vídeo» matched `hacer una cosa, abreme el widget` and built a duplicate video player called `entonces-vamos-cosa`, while this same turn's verdict said `catalog_widget=youtube` at 1.00 and nobody read it. `build_decision` composes that verdict with `build_or_use`: it VETOES a create over a card we already have, and REACHES the generator where no table of ours can read the script (zh/ja/hi 6/9 → 9/9, node 2.68).
        if _router.show_contradicts_the_order(text) or _tx._canvas_lic.closing_turn(_brief, _wid):
            emit("brain", "🚧 show_widget descartado: la orden dice CERRAR, no abrir",
                 text=(_wid or "?")[:40], role="system")
        # GUARD: CREAR un widget nuevo NO es show → escala al generador (el modelo elige show_widget para
        # 'créame un widget de X' e `identify` devuelve un widget EXISTENTE equivocado). Backstop determinista.
        elif (_bd := _tx._build_decision.decide(text, brief=_brief, proposed=_router.looks_like_create_widget(text)))[0]:
            if escalate_req["v"] is None:
                escalate_req["v"] = text
            emit("brain", "🏗️ show_widget→CREATE: se escala al generador (no es un show)", text=_bd[1][:60], role="system")
        else:
            from widgets import runtime
            # Resolver CON CERTEZA (V2-082) — the whole resolution lives in
            # show_target.resolve_show since V2-650b (ratchet extraction, guard passed in).
            _res, _open, _recent = _tx._show_target.resolve_show(
                _wid, text, brain._window, brain._last_action, _show_guard_target)
            _rid = _res.get("match") or ""
            _rid = _rid if (_rid and runtime.get(_rid.split("::", 1)[0]) is not None) else ""
            _sys = _res.get("system")
            # V2-650b: a widget the operator JUST closed does not reopen over chatter — the
            # model re-emitted its DISCARDED show and the card came back over nobody's order.
            if _rid and not _tx._canvas_lic.reopen_license(_rid, text, _open, _recent):
                emit("brain", "🛡️ show de un widget recién cerrado sin pedirlo — ignorado "
                     "(context-bleed)", text=_rid, role="system")
                deduped["v"] = True
            elif _rid:
                # V2-300 — la BASE con una instancia viva delante resuelve a la INSTANCIA: en la
                # ronda 24 el modelo mostró `results` con la hoja del encargo abierta al lado y el
                # canvas abrió la caja PELADA, vacía. Misma decisión y mismo dueño que el cierre
                # (`_close_target` → `instances.resolve_close`); con varias abiertas se pregunta.
                _r2 = _show_target_instance(_rid, text, brain._last_spoken or "")
                if _r2.get("ask"):
                    clarify["msg"] = _r2["ask"]
                    emit("brain", "🤔 show_widget con varias hojas → pregunto", text=_rid,
                         role="system")
                else:
                    _rid = _r2.get("id") or _rid
                    # V2-605: the choice was FORCED (we had already asked and he did not pick) → the
                    # ack has to name it, or an undisclosed decision costs the next three turns.
                    acted["show_chose"] = str(_r2.get("chose") or "")
                    _tag_emit("show", {"id": _rid})
                    # V2-209: QUÉ se abrió, no solo QUE se abrió. Sin el id, el ack de más abajo no
                    # puede distinguir «aquí lo tienes» de «te lo abro y sigo con ello», que es la
                    # diferencia entre informar y afirmar una entrega que no ha ocurrido.
                    acted["widget_id"] = _rid
                    emit("brain", "🪟 show_widget → canvas", text=_rid, role="system",
                         extra={"empty": _tx._surface_is_empty(_rid)})
            elif _tx._wall_tab_for(_sys, text):
                # It named the CHAT, or the widget catalogue (V2-761: «ábreme las apps») — two
                # tabs of the native wall, not widgets → open the wall on that tab.
                emit("panel", "open", extra={"tab": _tx._wall_tab_for(_sys, text), "src": "flash"})
                emit("brain", f"🗂️ show_widget→{_sys} (superficie de sistema)", role="system")
                acted["widget"] = True
            else:
                # V2-082: NO se fabrica un widget cuando no hay match. Si nombró una pieza de sistema o
                # nada reconocible → se PREGUNTA con naturalidad, jamás se escala al generador ni se abre
                # el "más parecido". (Crear solo con crea/genera/hazme/modifica, ya filtrado arriba.)
                clarify["msg"] = (_say().open_no_such_piece if _sys is None
                                  else _say().open_system_piece)
                emit("brain", "🤔 show_widget sin match → pregunto (no fabrico widget)",
                     text=str(_sys or "—"), role="system")


# V2-778 F1 — the `show_panel` arm of `_on_tool_call`, moved verbatim.
def _t_show_panel(*, args, _router, _tool_fired, acted, emit, operator_text, text):
    # V2-079: abre el PANEL nativo lateral (ChatWall) en una pestaña por voz — 'enséñame los procesos',
    # 'los crons', 'ábreme el chat'. NO es un widget del canvas: se emite un evento `panel` que el
    # frontend (sse.js) traduce a store.setChatTab + setChatOpen. UI nativa e intocable.
    if "show_panel" not in _tool_fired:
        _tool_fired.add("show_panel")
        _tab = _router._canon_panel(args.get("panel"))
        if _tab == "apps":      # V2-761: «¿qué apps tengo CUSTOMIZADAS?» → the Custom sub-tab
            _tab = _tx._wall_tab_for("apps", _router.operator_words(operator_text, text))
        # 2026-08-10: también CIERRA. Antes solo abría, así que «cierra el chat» no tenía a dónde ir y
        # el turno acababa en un «vale, cerrado» que era falso.
        _act = _router._canon_panel_action(args.get("action"))
        emit("panel", _act, extra={"tab": _tab, "src": "flash"})
        emit("brain", f"🗂️ show_panel → panel nativo ({_act})", text=_tab, role="system")
        acted["widget"] = True     # cuenta como acción de UI (ack "nunca mudo" + no escala espurio)


# V2-778 F1 — the `manage_widget_alias` arm of `_on_tool_call`, moved verbatim.
def _t_manage_widget_alias(*, args, _say, _tool_fired, acted, clarify, emit, text):
    # V2-082: añade/quita un NOMBRE/ALIAS de un widget por voz ("añade el alias WhatsApp a mensajería").
    # Escritura QUIRÚRGICA del manifest (no regenera código), con guard de colisión. Resuelve el widget
    # por id exacto o por nombre/alias (mismo resolver de certeza). Este bucle de tool-calls es SÍNCRONO
    # (como _apply_widget_data) → la escritura va inline (I/O de fichero de ms, no un await).
    if "manage_widget_alias" not in _tool_fired:
        _tool_fired.add("manage_widget_alias")
        from widgets import aliases as _al, runtime as _rt_al
        _awid = (args.get("widget_id") or "").strip()
        _alias = (args.get("alias") or "").strip()
        _op = "remove" if str(args.get("op") or "add").lower().startswith(("rem", "quit", "borr")) else "add"
        _rid = _awid if (_awid and _rt_al.get(_awid) is not None) else \
            ((_rt_al.identify(_awid or text) or {}).get("match") or "")
        if not _rid:
            clarify["msg"] = _say().alias_which_widget
        elif not _alias:
            clarify["msg"] = _say().alias_which_name
        else:
            _res = (_al.remove if _op == "remove" else _al.add)(_rid, _alias)
            acted["widget"] = True
            if _res.get("ok") and not _res.get("unchanged"):
                clarify["msg"] = (_say().alias_removed.format(alias=_alias) if _op == "remove"
                                  else _say().alias_added.format(wid=_rid, alias=_alias))
            elif _res.get("unchanged"):
                clarify["msg"] = (_say().alias_unchanged_had_not if _op == "remove"
                                  else _say().alias_unchanged_had).format(wid=_rid)
            else:
                clarify["msg"] = _res.get("error") or _say().alias_failed
            emit("brain", f"🏷️ manage_widget_alias {_op} → {_rid}", text=_alias, role="system")


# V2-778 F1 — the `arrange_canvas` arm of `_on_tool_call`, moved verbatim.
def _t_arrange_canvas(*, _tool_fired, acted, emit):
    # V2-588: «ordena los widgets» tenía TODO el tramo de abajo construido (botón ⤢, Desktop.arrange,
    # POST /api/canvas/arrange, handler SSE) y NINGUNA cara hacia el modelo — que llegó a afirmar en
    # vivo «no hay un botón en el front-end para eso» (falso) y a improvisar re-abriendo tarjetas.
    # Acción del CANVAS entero: sin id que resolver, el mismo emit que el endpoint REST.
    if "arrange_canvas" not in _tool_fired:
        _tool_fired.add("arrange_canvas")
        emit("widget", "arrange", extra={"src": "flash"})
        emit("brain", "▦ arrange_canvas → canvas", role="system")
        acted["widget"] = True


# V2-778 F1 — the `reply_message` arm of `_on_tool_call`, moved verbatim.
def _t_reply_message(*, args, _apply_widget_data, _say, _tool_fired, clarify):
    # V2-051: responder un mensaje del buzón. Converge en la data-op `reply` de `mensajeria`
    # (confirm:true) → el gate CONFIRM lee el borrador y pide OK antes de ENVIAR. Una por turno.
    if "reply_message" not in _tool_fired:
        _tool_fired.add("reply_message")
        try:
            _n = int(args.get("n"))
        except (TypeError, ValueError):
            _n = None
        _rtext = (args.get("text") or "").strip()
        if _n is not None and _rtext:
            _apply_widget_data("mensajeria", "reply", {"n": _n, "text": _rtext})
        else:
            clarify["msg"] = _say().reply_which_message


# V2-778 F1 — the `set_style_directive` arm of `_on_tool_call`, moved verbatim.
def _t_set_style_directive(*, args, _spawn, brain, emit, style_fired, text):
    # V2-046 A1 + V2-633 — the whole path (identity actions first, style FLAGS for the engine's
    # mouths applied synchronously, rule text persisted off-loop) lives in
    # `nucleo/flash/style_directive.py`, extracted paying the ratchet. True = identity consumed it.
    directive = (args.get("directive") or "").strip()
    if directive:
        style_fired["v"] = True
        from nucleo.flash import style_directive as _styled
        if _styled.handle(directive, text, brain, emit, _spawn): return


# V2-778 F1 — the `authenticate_web` arm of `_on_tool_call`, moved verbatim.
def _t_authenticate_web(*, args, _start_web_auth, emit, escalate_req, text):
    # Guard DETERMINISTA (V2-022): si además de entrar hay una TAREA ("entra en mi Gmail y BÓRRAME…"),
    # no es un login → es una tarea con sesión → escala al navegador (que resuelve el login como parte
    # de la tarea). authenticate_web es SOLO para login puro ("conéctame a Wallapop").
    # V2-176: la DECISIÓN (cuál de los cuatro caminos es) vive en `nucleo/flash/web_auth.decide`,
    # compartida con el canal de texto — la cadena estaba solo aquí, así que el otro canal no tenía
    # ninguna. Los EFECTOS se quedan donde estaban: cada canal emite lo suyo y este además es el que
    # tiene `escalate_req`.
    from nucleo.flash import web_auth as _wa_v
    _site = (args.get("site") or "").strip()
    _kind_v, _site_resolved = _wa_v.decide(_site, text)
    if _kind_v == _wa_v.KIND_MUSIC:
        # INVARIANTE (2026-07-16): un servicio de MÚSICA (Spotify) se conecta en el widget `musica`
        # (su tarjeta OAuth), NUNCA por el navegador. El routing del titular anterior insistía en authenticate_web
        # para "conéctame a mi cuenta de Spotify" pese a la descripción → el guard lo redirige aquí.
        _tx._cvis.present("musica", reason="turn-order", src="flash", emit=emit)
        emit("brain", "🎵 conectar música → tarjeta del widget musica (no navegador)", text=_site or text[:60], role="system")
    elif _kind_v == _wa_v.KIND_MESSAGING:
        # INVARIANTE (V2-045, espejo del guard de música): WhatsApp/Telegram se VINCULAN por QR DENTRO
        # del widget `mensajeria`, NUNCA por login de navegador. 'conéctame/abre WhatsApp' → mostrar el
        # widget (ahí está el QR), no abrir un Chromium en whatsapp.com.
        _tx._cvis.present("mensajeria", reason="turn-order", src="flash", emit=emit)
        emit("brain", "💬 conectar mensajería → QR del widget mensajeria (no navegador)", text=_site or text[:60], role="system")
    elif _kind_v == _wa_v.KIND_TASK:
        if escalate_req["v"] is None:
            escalate_req["v"] = text
        emit("brain", "🔐→🧭 login+tarea → escalado (no solo auth)", role="system")
    else:
        _start_web_auth(_site_resolved)


# V2-778 F1 — the `connect_cluster` arm of `_on_tool_call`, moved verbatim.
def _t_connect_cluster(*, args, _request_cluster_confirm):
    # V2-064: la tubería real (bridge.dispatch/dispatch_tag) ya existía — lo que faltaba era esta tool
    # PARA que el FlashBrain pudiera invocarla. No conecta directo: pide confirmación determinista
    # primero (ver _request_cluster_confirm) — la descripción de la tool sola no bastó para que el
    # modelo distinguiera una orden real de un texto pegado que solo mencionaba un cluster_id/token.
    _ccid = (args.get("cluster_id") or "").strip()
    _ctok = (args.get("token") or "").strip()
    # V2-086 — DOS clases de cluster. Antes la condición era `_ccid and _ctok`, así que un cluster
    # PÚBLICO (MeshKore Commons: tokenless por diseño) se descartaba en silencio: la tool se llamaba,
    # no pasaba nada y el operador no recibía ni un "no puedo". Ahora basta el cluster_id cuando el
    # cluster es público; el token solo es obligatorio en los privados.
    # ⚠️ THE NAME IS `_cluster_vis`, NOT `_cvis`, AND THAT IS THE WHOLE POINT (V2-758).
    # `_cvis` is this module's alias for `nucleo.flash.canvas_visibility` (top of the file). Assigning
    # to that name ANYWHERE in this function makes it LOCAL for the WHOLE function — so the three
    # branches above that call `_cvis.present(...)` (show_images, the music guard, the messaging
    # guard) raised `UnboundLocalError` before this line ever ran. Measured on his engine
    # 2026-09-23: nine turns, every one of them reported to him as «Cerebro rápido caído — turno
    # degradado» while DeepSeek was answering perfectly. A local that shadows a module alias is not
    # a style problem: it silently kills every earlier use of that module in the same scope.
    _cluster_vis = (args.get("vis") or "").strip().lower()
    if _cluster_vis not in ("public", "private", ""):
        _cluster_vis = ""
    if _ccid and not _ctok and not _cluster_vis:
        _cluster_vis = "public"   # id sin token = solo puede ser un cluster abierto
    if _ccid and (_ctok or _cluster_vis == "public"):
        _cname = (args.get("name") or "meshcore").strip() or "meshcore"
        _chandle = (args.get("handle") or "").strip() or None
        # PERMISOS al conectar (V2-076): si el operador concede código, se persiste con la conexión.
        _cperms = None
        if bool(args.get("code")):
            _cperms = {"workers": True, "code": True, "repo": (args.get("repo") or "").strip() or None}
        _request_cluster_confirm(_cname, _ccid, _ctok, _chandle, perms=_cperms,
                                 vis=("public" if _cluster_vis == "public" else ""))


# V2-778 F1 — the `cluster_send` arm of `_on_tool_call`, moved verbatim.
def _t_cluster_send(*, args, _spawn, emit):
    # V2-086: enviar al cluster, ahora como tool de 1ª clase (antes iba por widget_data sobre el
    # widget `cluster-registro`, que ya no existe). Sale por el MISMO camino que el tag
    # [[cluster.send]] → `bridge.dispatch_tag`, así que hereda el guard de salida (un secreto duro
    # bloquea el envío) y el journal. No pide confirmación: es una comunicación normal que el
    # operador acaba de pedir, como escribir en un chat.
    _stext = (args.get("text") or "").strip()
    if _stext:
        _sto = (args.get("to") or "").strip()
        _scl = (args.get("cluster") or "").strip()
        if not _scl:
            try:
                from connectors import meshkore as _mk2
                _live = [c for c in _mk2.get_manager().clusters() if c.get("connected")]
                _scl = _live[0]["name"] if len(_live) == 1 else ""
            except Exception:
                _scl = ""
        if _scl:
            _data = {"text": _stext}
            if _sto:
                _data["to"] = _sto
            try:
                from connectors import meshkore as _mk3
                _spawn(_mk3.dispatch_tag(f"cluster.send:{_scl}", {"data": _data}), "cluster-send")
                emit("brain", "🛰 mensaje enviado al cluster", role="system",
                     text=f"{_scl}{('→' + _sto) if _sto else ''}")
            except Exception as _e:  # noqa: BLE001
                _tx.logger.warning(f"cluster_send falló: {_e}")
        else:
            emit("brain", "🛰 cluster_send sin cluster resuelto (¿varios o ninguno?)", role="system")


# V2-778 F1 — the `set_cluster_objective` arm of `_on_tool_call`, moved verbatim.
def _t_set_cluster_objective(*, args, _say, _spawn, clarify, emit):
    # T-02 (auditoría 2026-07-26): antes NADA escribía nunca capsule.objective — el guard
    # `perms.gate_dev_by_objective` (V2-076) dejaba el dev-worker de CUALQUIER cluster con permiso
    # 'code' permanentemente inerte por falta de una vía para fijarlo. Sin confirm-gate (a diferencia
    # de connect_cluster): esto es solo bookkeeping declarativo del operador, no toca la red ni
    # ejecuta nada — reversible llamando de nuevo con objective vacío.
    _ocluster = (args.get("cluster") or "").strip()
    _opeer = (args.get("peer") or "").strip()
    _oobjective = (args.get("objective") or "").strip()
    if _ocluster and _opeer:
        async def _persist_objective(cluster: str, peer: str, objective: str) -> None:
            try:
                from connectors.meshkore import capsule as _capsule
                await _tx.asyncio.to_thread(_capsule.patch, cluster, peer, objective=objective)
                emit("brain", ("🎯 objetivo de cluster fijado" if objective else
                              "🎯 objetivo de cluster borrado"),
                     text=f"{cluster}·{peer}: {objective}"[:160], role="system")
            except Exception as e:  # noqa: BLE001
                _tx.logger.warning(f"set_cluster_objective no persistido (voz sigue): {e}")
        _spawn(_persist_objective(_ocluster, _opeer, _oobjective), "cluster-objective")
    else:
        clarify["msg"] = _say().objective_which_peer


# V2-778 F1 — the `send_to_worker` arm of `_on_tool_call`, moved verbatim.
def _t_send_to_worker(*, args, emit, worker_acted):
    # V2-038 (↓): refina/amplía un worker vivo → INYECTA (no relanza). Fire-and-forget marshalado al
    # loop del server (§v3·O: nunca await de una op de worker en el turno).
    which = (args.get("which") or "").strip()
    msg = (args.get("message") or "").strip()
    if msg:
        try:
            from nucleo import dispatch as _d
            _d.inject_soon(which or "todo", msg)
            worker_acted["v"] = "inject"
            emit("brain", "↪️ inyección a worker", text=f"{which}: {msg}"[:120], role="system")
            # Observability (V2-090 gap): this correction continues a LIVE task — its own dialogue
            # exchange should show up INSIDE that task's flow instead of opening a fresh one. Only
            # when the target is unambiguous (resolve_sessions picks exactly one): with several live
            # sessions, forcing a merge would be guessing which one this belongs to.
            try:
                # ⚠️ Found by ruff F821 (2026-09-05): `_trace` was never in scope here, so this
                # whole merge — documented as working since V2-090 — died as a NameError inside
                # this very except, every time. The audited fail-open class, live in the hot path.
                from voice import trace as _trace
                _targets = _d.resolve_sessions(which or "todo")
                if len(_targets) == 1:
                    _target_trace = _d.trace_of(_targets[0])
                    if _target_trace:
                        _trace.adopt(_target_trace)
            except Exception:
                pass
        except Exception as e:  # noqa: BLE001
            _tx.logger.warning(f"send_to_worker falló: {e}")


# V2-778 F1 — the `stop_worker` arm of `_on_tool_call`, moved verbatim.
def _t_stop_worker(*, args, _norm_nfkd, _say, _says_stop, clarify, emit, text, worker_acted):
    which = (args.get("which") or "").strip()
    # ── GUARD 1: NO SE MATA A QUIEN ACABAS DE CONTESTAR (2026-08-14, sesión b70a45d0) ──────────────
    # El turno emitió `answer_worker` con la autorización que el worker llevaba 30 s esperando («Sí,
    # autorizado: borra TODA la agenda») Y `stop_worker` detrás → la tarea murió `ok:False` con la
    # respuesta ya entregada, y le dijo al operador «Vale, se lo digo» — falso al decirlo; la agenda
    # nunca se vació. Contestar y matar en el MISMO turno es incoherente: gana la respuesta (no destructiva).
    if worker_acted["v"] == "answer":
        emit("brain", "🛡️ stop_worker ignorado — este turno ACABA de responder al worker",
             text=f"{which or 'todo'}", role="system",
             extra={"cat": "flash", "kind_diag": "stop_after_answer"})
        return
    # ── GUARD 2: MATAR EXIGE QUE EL OPERADOR LO HAYA DICHO ────────────────────────────────────────
    # Mismo espíritu que el guarda de context-bleed de las data-ops (~L797), para lo irreversible:
    # sin orden de parar EN el turno del operador, el `stop_worker` es arrastre del anterior. En la
    # sesión, el stop nació de una queja de DOS TURNOS ANTES sobre widgets («los dos navegadores no se
    # tenían que haber abierto»), cancelada por barge-in — el modelo la arrastró y la hizo un hachazo.
    # OJO con «para»: en castellano es preposición mucho más a menudo que verbo («para nada», «para
    # ti»), y por eso no entra suelto — de hecho «para» a secas solo calla la voz, nunca para tareas
    # (regla del operador). Se piden formas inequívocas.
    if not _says_stop(text):
        emit("brain", "🛡️ stop_worker ignorado — el operador no ha pedido parar nada (context-bleed)",
             text=(text or "")[:120], role="system",
             extra={"cat": "flash", "kind_diag": "stop_without_order", "which": which or "todo"})
        return
    try:
        from nucleo import dispatch as _d
        # GUARD matar-TODO (sesión 23:15 2026-07-16, T49): ante «si solo es una tarea» el modelo llamó
        # stop_worker(todo) y mató las DOS sesiones vivas — incluida la de la ITV que SÍ trabajaba
        # (el operador se quejaba de VENTANAS duplicadas, no de procesos). Matar es irreversible →
        # "todo" con VARIAS tareas de objetivos DISTINTOS exige que el operador lo haya dicho de
        # verdad (todo/todas/ambos… en su turno, es/en); si no, se resuelve a la sesión que CASE con
        # el texto (`resolve_sessions`) y, sin match claro, NO se mata nada (se pregunta).
        import re as _re_stop
        _w = which or "todo"
        if _w == "todo":
            _live = _d.pending_summaries()
            _goals = {(s.get("request") or "")[:60] for s in _live}
            _says_all = bool(_re_stop.search(r"\b(todo|todos|todas|ambos|ambas|all|both|everything)\b",
                                             _norm_nfkd(text)))
            if len(_goals) > 1 and not _says_all:
                _match = _d.resolve_sessions(text)
                if len(_match) == 1:
                    _w = _match[0]
                else:
                    clarify["msg"] = _say().stop_which_worker
                    worker_acted["v"] = "stop"      # atendido (preguntando), sin matar a ciegas
                    emit("brain", "🛑 stop_worker(todo) RETENIDO (varias tareas distintas, sin 'todo' "
                         "explícito)", text=text[:100], role="system")
                    return
        tids = _d.cancel_soon(_w)
        if _w == "todo":     # «para todo y quédate tranquilo» → además LIMPIA las marcas de trabajo
            from nucleo import reset as _reset_mod
            _reset_mod.abandon_work_soon(source="voz")     # mismo núcleo que Reset; ver su docstring
        worker_acted["v"] = "stop"
        emit("brain", "🛑 stop worker", text=f"{_w} → {tids}"[:120], role="system")
    except Exception as e:  # noqa: BLE001
        _tx.logger.warning(f"stop_worker falló: {e}")


# V2-778 F1 — the `answer_worker` arm of `_on_tool_call`, moved verbatim.
def _t_answer_worker(*, args, emit, worker_acted):
    ans = (args.get("answer") or "").strip()
    if ans:
        try:
            from nucleo import worker_api as _wapi
            if _wapi.answer_active_soon(ans):
                worker_acted["v"] = "answer"
                emit("brain", "💬 respuesta a worker", text=ans[:120], role="system")
        except Exception as e:  # noqa: BLE001
            _tx.logger.warning(f"answer_worker falló: {e}")
