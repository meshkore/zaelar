"""The post-stream chain runs the LIGHT LANES the model chose: playback it promised, work it handed back, a close or a fullscreen exit it said and did not do, a secret, a recall, a widget read, a finished errand, a web search, a listing pass and music (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/post_stream.py::run` (951 lines) with no behaviour change. Every name the block read
from `post_stream` is read through it (`_pst.<name>`), so a patch on `post_stream` still governs it. The function
takes the chain's locals it read as keyword arguments and returns the ones the rest of `run` reads, only when
bound.
"""
from __future__ import annotations

from nucleo.flash import act_repair as _act_repair, post_stream as _pst


async def run_the_light_lanes(*, FastClient, _apply_widget_data, _brief, _buf_add, _buf_reset, _cardc, _close_target, _cover_work, _identify, _identify_system, _named_by_verdict, _no_tool, _op_text, _prompt_mod, _router, _rv, _say, _show_target_instance, _shown_ids, _t, _tag_emit, _tool_fired, _turn_op_tasks, acted, attention, brain, clarify, data_done, emit, escalate_req, images_req, listing_req, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, send, speak, spec, speech, spoken, spoken_text, take, text, with_also_named) -> dict:
    _playback = _router.promises_playback(spoken_text, _op_text, music_open=_pst._direct_action.on_screen_now("musica"))
    if (_no_tool and spoken_text
            and (_router.promises_action(spoken_text) or _playback
                 or _pst._direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))
                 or _pst._direct_action.verdict_shows(_brief))
            and not _router.asks_for_missing_detail(spoken_text)):
        _win_goal = ""
        if not (_router.looks_like_create_widget(_op_text) or _router.looks_like_escalate_task(_op_text)):
            # V2-132 — la petición puede ser de HACE UNOS TURNOS: zaelar pidió el dato que faltaba (correcto),
            # el operador se lo dio, y la promesa cayó en un turno cuyo texto por sí solo no describe tarea
            # ninguna («vale, avísame»). El backstop miraba solo ESTE turno, así que no podía dispararse — y
            # la corrida se fue en ocho turnos narrando una búsqueda que nunca arrancó. Solo con NADA vivo:
            # con una tarea en marcha, «sigo con ello» es honesto y re-escalar haría el trabajo dos veces.
            #
            # V2-176: «nada vivo» era la pregunta equivocada — la que decide es «nada vivo PARA ESTO».
            # Medido en `book-hotel-night-known__es`: el encargo del hotel no escaló porque seguía vivo un
            # worker del encargo ANTERIOR, y zaelar pasó cuatro turnos diciendo «la reserva sigue en marcha»
            # sobre una tarea de Ticketmaster ya cancelada. Espejo exacto del canal de texto; el predicado es
            # compartido (`router_guards.nothing_running_for`) y es CONSERVADOR: ante la duda, se comporta
            # como antes.
            try:
                from nucleo import dispatch as _disp_wg
                _cand = _router.escalate_goal_from_window(brain._window, _op_text)
                if _cand:
                    _live = [str(r.get("request") or "") for r in _disp_wg.pending_summaries()]
                    if not _disp_wg.has_active() or _router.nothing_running_for(_cand, _live):
                        _win_goal = _cand
            except Exception:
                _win_goal = ""
        # V2-773 — …or the brief's own verdict said this order needs a worker (kickoff A1: «On it — I'll show
        # you the options» over nothing; the verb tables know «búscame», not every way of asking).
        # V2-773 (demo S1) — a «show me X» that NAMES a card we have (open, or a finished errand's closed sheet)
        # is a show, before any worker: the escalate verdict fired first and a second worker searched the
        # monitors again over their own closed sheet.
        # C1 (demo pass 52, 2026-09-29): «show me what i've got tomorrow» — the catalogue named `agenda`, `identify`
        # answered by CONTEXT with the minimized monitor sheet, and the sheet came up over the day he asked for.
        # The card the verdict names wins over a contextual guess.
        _pw = ((_named_by_verdict or _identify(_op_text))
               if (_router.looks_like_show_strict(_op_text) or _pst._direct_action.verdict_shows(_brief)) else "")
        if _pw:
            # V2-776 — the CARD, not the piece: a bare `results` is resolved like the tool path resolves it
            # (open instance, or the closed sheet the phrase names), or «Show me the monitors» opened the base.
            try:
                _r_pw = _show_target_instance(_pw, _op_text, brain._last_spoken or "")
                if not _r_pw.get("ask"):
                    _pw = _r_pw.get("id") or _pw
            except Exception:  # noqa: BLE001
                pass
            acted["widget"] = True
            _shown_ids.add(_pw)          # V2-660: a shown card is an end state the harness verifies
            _pst._cvis.present(_pw, reason="turn-order", src="flash", emit=emit)
            emit("brain", "🪟 show por backstop de promesa (prometió mostrar sin tool)", text=_pw, role="system")
            from nucleo.flash import card_commission as _cc_fill
            _fill = _cc_fill.search_to_fill(_pw, _op_text)    # demo pass 93, V1: an empty catalogue is its search
            if _fill:
                _apply_widget_data(_fill["widget_id"], _fill["action"], _fill["payload"])
                data_done["v"] = True
                emit("brain", "🔎 la tarjeta estaba vacía — su búsqueda, con su frase", role="system",
                     text=f"{_fill['widget_id']}:{_fill['action']} ← {_op_text[:80]}", extra={"cat": "flash"})
        elif _playback:
            # BEFORE any worker or show: the song is on the player, not on the web. The query is the title the
            # words carry, never his sentence whole («no, put like a prayer» is not a song).
            music_req["v"] = {"query": _router.music_query(spoken_text, _op_text), "action": "play"}
            emit("brain", "🎵 música por backstop (prometió ponerla sin tool, en inglés)",
                 text=music_req["v"]["query"][:80], role="system")
        elif (_router.looks_like_create_widget(_op_text) or _router.looks_like_escalate_task(_op_text) or _win_goal
                or _pst._direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))
                or _pst._direct_action.order_over_a_card_left_undone(_brief)):
            # crear widget (o sinónimo: panel/gadget) = código → escala; marketplace/informe = navegador → escala
            escalate_req["v"] = _win_goal or _op_text
            emit("brain", "🧭 escalada por backstop (prometió crear/gestionar sin escalar)",
                 text=(_win_goal or _op_text)[:80], role="system")
        elif _router.looks_like_show_strict(_op_text):    # it named no card: a TAB of the wall, or nothing
            _wtab = _pst._wall_tab_for(_identify_system(_op_text), _op_text)
            if _wtab:
                # V2-761 — it named a TAB of the wall («te abro el panel de apps», nothing called).
                acted["widget"] = True
                emit("panel", "open", extra={"tab": _wtab, "src": "flash"})
                emit("brain", "🗂️ panel por backstop de promesa (prometió abrirlo sin tool)", text=_wtab,
                     role="system")
        elif _router.promises_music(spoken_text):     # 'voy a poner algo de rock' sin tool → reproduce
            music_req["v"] = {"query": _op_text, "action": "play"}
            emit("brain", "🎵 música por backstop (prometió poner música sin tool)", text=_op_text[:80], role="system")

    # BACKSTOP DE TRABAJO DEVUELTO (V2-142). Distinto del de promesa: aquí el modelo no promete nada, MANDA
    # AL OPERADOR a buscar en Google/Maps lo que él acaba de pedir. Medido en `reorder-prescription`: «¿puedes
    # buscar tú el teléfono?, para eso te pido ayuda» → «la forma más fiable es que tú busques "farmacia" en
    # Google Maps y me pases el teléfono». Una regla de prompt no basta: lo que hace falta es HACER la
    # búsqueda. Solo si NADA corre (con una tarea viva la frase puede ser una sugerencia mientras se trabaja,
    # y re-escalar duplicaría el trabajo, V2-123).
    if (_no_tool and spoken_text and escalate_req["v"] is None
            and _router.hands_public_lookup_back(spoken_text)):
        try:
            from nucleo import dispatch as _disp_hb
            _busy = _disp_hb.has_active()
        except Exception:
            _busy = False
        if not _busy:
            escalate_req["v"] = _router.escalate_goal_from_window(brain._window, _op_text) or _op_text
            emit("brain", "🧭 escalada por backstop (devolvió la búsqueda al operador)", text=_op_text[:80], role="system")

    # BACKSTOP DETERMINISTA de CIERRE corto (sesión 22:40 2026-07-16): «Vale, ciérralo» → el modelo respondió
    # "Listo, cerrado" SIN emitir [[close]] ni tool alguna — la tarjeta quedó abierta y el operador tuvo que
    # repetirlo (T10 muteó, luego "no se está cerrando nada"). Orden CORTA que es claramente CERRAR (verbo de
    # cerrar, sin verbo de borrar, ≤5 palabras — `looks_like_close`, mismo guard que cerrar≠borrar) y el turno
    # NO cerró nada → cerramos AQUÍ: el widget que nombre el texto, o el ÚNICO abierto. Con varios abiertos y
    # sin nombre no adivinamos ("cierra todo" ya lo cubre `hard_interrupt`). Post-stream (la voz ya salió):
    # la lectura µs de `state.open_widgets` no toca la latencia del turno.
    # AMPLIADO (sesión absurda 2026-07-19): «Cierra el widget de música. Has puesto un videoclip…» (>5 palabras,
    # con queja) NO cazó el guard corto → el modelo ESCALÓ, y una escalada de "cerrar" cayó en el worker de
    # MODIFICAR código («modificando el widget musica…»), que giró 3 min leyendo fuentes mientras zaelar repetía
    # "sigo procesando el cierre" e ignoraba "ya está cerrado". Cerrar un widget NUNCA es tarea de código
    # (V2-017). Por eso: si hay verbo de CERRAR (sin borrar/crear) Y se NOMBRA un widget ABIERTO concreto,
    # cerramos AQUÍ aunque el turno sea largo, y CANCELAMOS cualquier escalada que el modelo haya pedido.
    # guardas contra verbos AMPLIOS ('apaga/quita'): si el turno ya disparó MÚSICA ('apaga la música'=stop
    # audio) o una data-op ('quita la tarea X'), NO cerramos el widget además (evita doble-acción).
    # BUG real 2026-07-23: "quita la pantalla completa" (verbo amplio 'quita' + turno corto + 1 solo widget
    # abierto) disparaba ESTE backstop y CERRABA el widget entero — el operador solo quería salir de
    # fullscreen. `fullscreen_widget` YA resolvió la intención real este turno; no lo pisa un cierre espurio
    # (mismo criterio que música/data-op de arriba: una acción real explícita gana sobre el backstop genérico).
    # V2-600 (2026-09-05): the fullscreen guard used to depend on the MODEL having called fullscreen_widget
    # this turn (`_tool_fired`). Measured live (session 3050e623): the operator's complaint «te he dicho que
    # cerraras la pantalla completa, no que cerraras el widget del vídeo» — a turn where the model called
    # nothing — matched the close verb + named widget and this backstop closed `youtube` AGAIN, twice, while
    # he was describing the first wrongful close. A turn that MENTIONS fullscreen is about a screen state
    # (leaving it, or narrating it), never a whole-widget close order for a backstop to guess at; if the
    # operator really wants it closed the model can still emit [[close]] itself.
    # V2-759 — «Y sal de pantalla completa.» → «Ya está, fuera de pantalla completa.» with NOTHING called,
    # for the second time (V2-609 was the first). Completed here only when a card IS covering the screen
    # and the existing licence reads the turn as leaving — see `show_target.fullscreen_exit_backstop` for
    # why that is safe. It runs BEFORE the close backstop and marks the tool as fired, so a turn that is
    # about leaving full screen can never be read below as an order to close the whole widget.
    try:
        if _pst._show_target.fullscreen_exit_backstop(
                _pst._bnotes.operator_half(text), fired="fullscreen_widget" in _tool_fired,
                tag_emit=_tag_emit, emit=emit):
            _tool_fired.add("fullscreen_widget")
    except Exception:  # noqa: BLE001 — a backstop never adds an exception to a turn
        pass
    if (not acted.get("closed")) and _pst._canvas_lic.close_license(text, brief=_brief) \
            and not _router.looks_like_create_widget(text) \
            and not music_req["v"] and not data_done["v"] \
            and "fullscreen_widget" not in _tool_fired \
            and not attention.mentions_fullscreen(text):
        try:
            from memory import api as _memapi
            _openw = list((_memapi.state() or {}).get("open_widgets") or [])
        except Exception:
            _openw = []
        _cw = None
        # THE VERDICT NAMES THE CARD before any word match does (demo pass 2026-09-28, V7: «ok stop the video
        # and close it» — the video was already closed, «video» then tied navegador↔youtube, «the open one
        # wins» picked the worker's browser card, and the backstop closed THAT). Already closed → nothing to do.
        _vc = _pst._direct_action.verdict_card(_brief) if _pst._direct_action.sure_canvas(_brief) == "close" else ""
        try:
            from widgets import runtime as _rt_close
            # los ABIERTOS desempatan ("cierra el vídeo": vídeo empata navegador↔youtube; gana el abierto)
            _idc = ({"match": _vc if _vc in _openw else ""} if _vc
                    else (_rt_close.identify(text, open_ids=_openw) or {}))
            # NOMBRE resuelto y NO ambiguo = cerramos aunque el turno sea largo (señal fuerte: cerrar + widget
            # nombrado). No exigimos que esté en open_widgets: el frontend puede no haberlo reportado y cerrar
            # uno ya cerrado es no-op inofensivo; el valor real es CANCELAR la escalada espuria.
            if not _idc.get("ambiguous"):
                _cw = _idc.get("match")
        except Exception:
            _cw = None
        # sin nombre resuelto: solo el caso corto genérico ("ciérralo") con un único widget abierto.
        if not _cw and not _vc and _pst._closeg.is_short_order(text) and len(_openw) == 1:
            _cw = _openw[0]
        if _cw:
            _t = _close_target(_cw, text)
            if _t["ask"]:                           # V2-259 F3
                clarify["msg"] = _t["ask"]
                emit("brain", "❓ cerrar: varias tarjetas abiertas", text=_cw, role="system",
                     extra={"options": _t["options"]})
                if escalate_req["v"] is not None:
                    escalate_req["v"] = None
                _cw = None
        if _cw:
            acted["widget"] = True
            acted["closed"] = True
            for _cid in with_also_named(_t.get("ids") or [_t["id"] or _cw], text):
                emit("widget", "close", extra={"id": _cid, "src": "flash"})
                _pst._canvas_lic.note_operator_close(_cid)                     # V2-650b
            emit("brain", "🙈 close por backstop (cerrar widget nombrado sin [[close]])",
                 text=_cw, role="system")
            # cerrar un widget NO es tarea de worker → cancela la escalada espuria (evita el bucle de 3 min)
            if escalate_req["v"] is not None:
                escalate_req["v"] = None
                emit("brain", "🚫 escalada de cierre cancelada (cerrar ≠ tarea de código)", role="system")

    # REVELAR UN SECRETO (V2-060): el operador pidió un secreto guardado (reveal_secret). El valor se descifra
    # FUERA del event loop y se entrega OUT-OF-BAND: NUNCA entra en un prompt del modelo NI en el observer/logs.
    # En F1b zaelar IDENTIFICA el secreto y confirma/pide passphrase por voz (SIN el valor); el valor lo sirve la
    # API `/api/vault/reveal` (loopback) al frontend/tester. (Lectura del valor POR VOZ con redacción = F2.)
    if reveal_req["v"] is not None and escalate_req["v"] is None:
        _lblq = reveal_req["v"]
        emit("brain", "🔐 reveal_secret", text=_lblq, role="system")
        from nucleo.turn import vault_gate as _vgate
        _rv = await _vgate.reveal(_lblq)
        for _k, _lb, _ex in _rv.events:
            emit(_k, _lb, role="system", extra=_ex)
        _buf_reset()   # descarta restos de tags del 1er pase
        send(speech.sanitize(_vgate.voice_line(_rv), drop_metadata=False))
        spoken_text = "".join(spoken).strip()

    # RECALL DE MEMORIA por tool (V2-056): ruta LIGERA hermana de web_search — memory.query FUERA del event
    # loop (to_thread, V2-011) + 2º pase con los recuerdos (el modelo que el turno ya paga). Solo si el turno
    # no escaló (el worker recibe su propio dossier) ni buscó (una sola respuesta compuesta por turno).
    # LECTURA DE UN WIDGET por tool (V2-668): la ruta LIGERA hermana de recall — lo que el widget GUARDA, leído
    # por las costuras que ya publica para el prompt (`widget_read.read`) + 2º pase con ese contenido como
    # ÚNICA fuente. Sesión 53de97d4: la hora de la cita con Hacienda estaba en la agenda y el modelo no tenía
    # ninguna puerta para leerla con la tarjeta cerrada. Solo si el turno no escaló ni buscó ni reveló.
    if read_req["v"] is not None and escalate_req["v"] is None and search_req["v"] is None \
            and reveal_req["v"] is None:
        from nucleo.flash import widget_read as _wread
        # V2-773 — «Show me that time in my calendar»: a read answers in words, and the card he asked to SEE
        # stayed closed. When the verdict says the canvas should SHOW, the card comes up (`card_commission`).
        from nucleo.flash import card_commission as _cardc
        _cardc.present_if_show(read_req, brief=_brief, operator_text=operator_text, is_open=_pst._cvis.is_open,
                               present=_pst._cvis.present, emit=emit)
        _cover_work("widget", _wread.cover_target(read_req["v"] or {}, operator_text))
        # A card this turn just changed is read AFTER the change lands (demo pass 2026-09-28, full11 M3: the chart
        # was switched to the Nasdaq and the read, a few ms later, answered «the only thing on the chart is Apple»).
        _rw = str((read_req["v"] or {}).get("widget_id") or "").split("::")[0]
        _pending = [t for w, t in _turn_op_tasks if str(w).split("::")[0] == _rw and not t.done()]
        if _pending:
            await _pst.asyncio.wait(_pending, timeout=6.0)
        # A read that serves an ORDER on another card (full20 C5: «send rowan a telegram with the new time» read
        # the agenda for the time) — the order is carried out with what was read, instead of a words-only pass
        # that has no tools and says it cannot.
        _after = await _act_repair.after_a_read(_brief, _op_text, _rw, "".join(spoken).strip(), spec=spec,
                                                window=list(brain._window))    # V2-781 T518: or this same card
        if _after:
            _pst._cvis.present(_after["widget_id"], reason="turn-order", src="flash", emit=emit)
            _apply_widget_data(_after["widget_id"], _after["action"], _after["payload"])
            acted["widget"] = True
            data_done["v"] = True
            emit("brain", "🔁 leyó para una orden — la llamada, con lo leído", role="system",
                 text=f"{_rw} → {_after['widget_id']}:{_after['action']}",
                 extra={"cat": "flash", "widget": _after["widget_id"], "action": _after["action"]})
        else:
            await speak(await _wread.prepare(read_req["v"] or {}, operator_text, _prompt_mod._lang_lock(), emit),
                        operator_text, 220, "read_widget compose")
            spoken_text = "".join(spoken).strip()

    # V2-728 — RECUPERAR UN ENCARGO TERMINADO. La decisión ENTERA (índice léxico → Jev → preguntar si hay
    # varios) y su descripción viven en `task_recall.voice_turn`; aquí solo lo propio del canal.
    if reopen_req["v"] is not None and escalate_req["v"] is None:
        _re = await _pst.asyncio.to_thread(_pst._trecall.voice_turn, reopen_req["v"])
        acted["widget"] = True          # lo ATENDIMOS (abriendo o preguntando) — no cae a escalate
        if _re["show"]:
            _tag_emit("show", {"id": _re["show"]})
        elif _re["ask"]:
            clarify["msg"] = _say().ask_which_item.format(cands=_re["ask"])
        emit("brain", _re["label"], role="system", text=_re["text"], extra=_re["extra"])

    if recall_req["v"] is not None and escalate_req["v"] is None and search_req["v"] is None \
            and reveal_req["v"] is None and read_req["v"] is None:
        from nucleo.flash import second_pass as _second_v
        _cover_work("recall")
        _recall_empty_thread = await _second_v.recall_spoken(text, recall_req["v"], spec, emit, speak)
        spoken_text = "".join(spoken).strip()
        if _recall_empty_thread == "empty_thread" and not acted["widget"] and not data_done["v"]:
            # fix02: the pills came back empty on a LIVE-thread question — the compose would have narrated
            # the void as no-access. The deterministic which-message question replaces it at the clarify
            # gate below (V2-026: a hard "I don't know what you mean" never loses to invented prose).
            clarify["msg"] = _say().ask_which_item_bare

    # BÚSQUEDA WEB FACTUAL (V2-022): ruta LIGERA — se resuelve EN ESTE turno (NO es el navegador pesado del
    # SlowBrain). La búsqueda es I/O de red → FUERA del event loop (to_thread). La EXTRACCIÓN reusa el MISMO
    # modelo rápido que el turno ya paga (coste marginal ≈0): 2º pase con los snippets como contexto →
    # respuesta hablada. Proveedor por capas (calidad primero): respuesta-IA (Perplexity/Tavily) → snippets
    # (Brave) → gratis (DDG). Compartido con el SlowBrain. Ver nucleo/websearch.py.
    # V2-210 — AQUÍ NO. El backstop de «un dato del mundo no se improvisa» vive en el canal de texto
    # (`probe.py`) y este canal se queda FUERA a propósito, que es lo contrario de lo que pide la regla de
    # implementación paralela y por eso se escribe.
    #
    # La razón es una asimetría real entre los dos canales: la voz EMITE los deltas del modelo según llegan,
    # así que cuando el turno llega hasta aquí la frase inventada YA SE HA DICHO. Sustituirla es imposible y
    # añadir la versión con fuente detrás significa hablar dos veces en toda pregunta de horarios o precios
    # — una regresión en el canal del operador, cambiada por un defecto que en este canal nadie ha medido.
    #
    # El arreglo BUENO para la voz es el mismo disparo pero ANTES de generar (si la pregunta es de un dato
    # del mundo, se busca primero y el modelo compone con los resultados), que es además lo que el modelo
    # hace cuando acierta. Eso toca `_run_inner` antes del stream y quiere su propia medición de latencia.
    if search_req["v"] is not None and reveal_req["v"] is None:
        query = search_req["v"]
        emit("brain", "🔎 búsqueda web", text=query, role="system")
        _cover_work("search")     # the slowest light route measured (7.2 s end to end) — V2-669
        _t_s = _pst.time.time()
        try:
            from nucleo import websearch as _ws
            res = await _pst.asyncio.to_thread(_ws.search, query)
            ctx = _ws.format_results(res)
        except Exception as e:  # noqa: BLE001
            _pst.logger.warning(f"web_search falló (voz sigue): {e}")
            res, ctx = {"source": "none", "results": []}, ""
        # EVIDENCIA (2026-08-10): además del proveedor y el número, se guarda QUÉ VOLVIÓ — título, URL y un
        # trozo del snippet de cada resultado, más la respuesta sintetizada si el proveedor la dio. Sin esto
        # se podía auditar que el sistema BUSCÓ, nunca si respondió con lo que traía: la fila decía «7
        # resultados» y el contenido que el modelo leyó se perdía para siempre. Presupuestada en
        # `observability.evidence` (se recorta, no se resume) y best-effort: si falla, el evento sale igual.
        _ev = {"source": res.get("source"), "ai": bool(res.get("ai")), "ms": round((_pst.time.time() - _t_s) * 1000),
               "n": len(res.get("results", [])), **({"failure": res["failure"]} if res.get("failure") else {})}
        try:
            from observability import evidence as _evd
            _ev["evidence"] = _evd.web_results(res.get("results"))
            _ans = _evd.body(res.get("answer"))
            if _ans:
                _ev["evidence"]["answer"] = _ans
        except Exception:
            pass
        emit("search", "🔎 resultados web", text=query, role="system", extra=_ev)
        # V2-676 — the prompt (and the REASON an empty search was empty) now lives in ONE home shared with
        # the probe channel: `flash/search_turn`. It was a parallel implementation these two files had been
        # apologising for since V2-135, and the half that was missing in BOTH is what cost the operator his
        # «don't you have access to the Internet?» turn.
        from nucleo.flash import search_turn as _st
        from nucleo import canvas_focus as _cf_s
        sys2 = _st.compose_system(operator_text, query, res, ctx,
                                  today=_pst.time.strftime("%A %d %b %Y (%Y-%m-%d)"), on_screen=_cf_s.this_turn_cards())
        await speak(sys2, operator_text or query, _st.MAX_TOKENS, "web_search compose")
        spoken_text = "".join(spoken).strip()
        # THE BACKSTOP. The prompt above forbids the sentence; this catches it when the model says it
        # anyway. Only reaches the room if it fires, and then what was already spoken is corrected — see
        # `denial_repair` for why a false claim cannot be left standing as merely "a bad answer".
        _fixed = _st.denial_repair(spoken_text, res)
        if _fixed != spoken_text:
            emit("alert", "🌐 retirada una frase que negaba tener internet",
                 text=spoken_text[:200], role="system",
                 extra={"cat": "flash", "guard": "denies_the_world", "failure": res.get("failure")})
            send(_fixed)
            spoken_text = _fixed
        await _act_repair.voice_after_search(_op_text, spoken_text, _brief, spec, window=list(brain._window),   # V2-781 T515
                                             apply=_apply_widget_data, send=send, emit=emit, acted=acted, done=data_done)
        brain._last_action = "search"

    # BÚSQUEDA DE ANUNCIOS (V2-556): ruta LIGERA hermana de web_search. La pasada rápida corre FUERA del
    # event loop y el MÓDULO decide solo (listing_turn.run): o hay filas reales en la hoja y este 2º pase
    # las cuenta, o él mismo ya escaló a un worker que HEREDA la hoja y este 2º pase dice honestamente que
    # la búsqueda a fondo está en marcha. Se salta si el turno además escaló (escalate_req): dos workers
    # corriendo la misma caza es exactamente el defecto del fontanero (c480413b), no una redundancia sana.
    if listing_req["v"] is not None and reveal_req["v"] is None and escalate_req["v"] is None:
        emit("brain", "🛒 búsqueda de anuncios", text=listing_req["v"]["query"], role="system")
        _buf_reset()   # descarta cualquier resto de tags del 1º pase antes de componer la respuesta
        _said_before = "".join(spoken).strip()
        _lsep = [bool(_said_before)]      # a second pass after spoken words starts with a space, once

        def _listing_delta(_d: str) -> None:
            if _lsep[0] and _d.strip():
                _d, _lsep[0] = " " + _d.lstrip(), False
            _buf_add(_d)
            send(speech.inline(take(False)))

        await _pst._lt.voice_turn(listing_req["v"], operator_text or text, spec=spec, on_delta=_listing_delta,
                             already_said=_said_before)
        send(speech.sanitize(take(True), drop_metadata=False))
        spoken_text = "".join(spoken).strip()
        brain._last_action = "listings"

    # MÚSICA (V2-041/V2-042): ruta LIGERA como web_search, ahora con la CADENA resolver→validar→actuar
    # (`nucleo/flash/music_flow`): intento directo → si no_track, websearch (Chromium CALIENTE del prewarm) +
    # 2º pase del modelo que el turno ya paga (extractor 'Artista - Título') → reintento. El estado del intento
    # vive en las ACTIVIDADES (buscando / sonando / sin_resolver AISLADA con intentos → el turno siguiente la
    # continúa con más datos) y cada reproducción se vuelca a memoria (source="music" → gustos/historial).
    # Todo el I/O va FUERA del event loop (to_thread, V2-011). Se dice el mensaje si (a) falló, (b) el modelo
    # no habló (nunca mudo), o (c) la cadena RESOLVIÓ otra cosa que lo dicho (validación por anuncio).
    if images_req["v"] is not None:
        # V2-457 — aquí y no en la rama de la tool: buscar es red y en el stream bloquearía el turno (V2-011).
        _parte_img, _say_img = await _pst._image_turn.voice_turn(images_req["v"], silent=not spoken_text)
        emit("brain", "🖼️ fotos ↩", text=str(_parte_img)[:200], role="system")
        if _say_img:
            send(speech.sanitize(_say_img, drop_metadata=False))
            spoken_text = "".join(spoken).strip()

    if music_req["v"] is not None:
        mq = music_req["v"]
        emit("brain", "🎵 música", text=f"{mq.get('action')} {mq.get('query')}".strip(), role="system")
        _t_m = _pst.time.time()

        async def _extract(sys2: str, user2: str) -> str:
            """2º pase INTERNO (no se habla): mismo modelo del turno, respuesta corta y estricta."""
            out: list[str] = []
            async for d in FastClient().stream([{"role": "system", "content": sys2},
                                                {"role": "user", "content": user2}],
                                               spec=spec, max_tokens=40):
                out.append(d)
            return "".join(out)

        try:
            from nucleo.flash import music_flow as _mflow
            res = await _mflow.run(mq.get("action") or "play", mq.get("query") or "", extract=_extract)
        except Exception as e:  # noqa: BLE001
            _pst.logger.warning(f"play_music falló (voz sigue): {e}")
            res = None
        # Ejecuta el FOLLOWUP de control (volumen/pausa) tras un play/queue OK — en SECUENCIA, nunca antes
        # (bug real 2026-07-23, ver comentario en el collapse de arriba). Fail-open: si falla, el play ya
        # dicho/hecho no se deshace; solo no se aplica el ajuste.
        if music_req.get("followup") and bool(getattr(res, "ok", False)):
            try:
                await _mflow.run(music_req["followup"]["action"], "", extract=None)
            except Exception as e:  # noqa: BLE001
                _pst.logger.warning(f"play_music followup falló: {e}")
        ok = bool(getattr(res, "ok", False))
        msg = (getattr(res, "message", "") or "").strip()
        _extra = getattr(res, "extra", {}) or {}
        _resolved = bool(_extra.get("resolved_from"))
        emit("music", "🎵 acción de música", text=mq.get("query") or mq.get("action"), role="system",
             extra={"provider": getattr(res, "provider", ""), "action": mq.get("action"),
                    "ok": ok, "reason": getattr(res, "reason", ""), "surface": _extra.get("surface", ""),
                    "resolved_from": _extra.get("resolved_from", ""),
                    "ms": round((_pst.time.time() - _t_m) * 1000)})
        # V2-721/V2-723 — `surface` says WHERE the audio is, never what must be on SCREEN. The door
        # checks the claim against the widget's own declaration and refuses to raise an open card.
        if ok and str(_extra.get("surface") or "") == "widget":
            _pst._cvis.present(str(_extra.get("widget") or ""), reason="producer-mount",
                          action=mq.get("action") or "", src="flash", emit=emit)
        # No re-anunciar un no-op (F5): si la reproducción fue "ya suena eso", el modelo ya habló; no encajes
        # el "ya está sonando" salvo que el modelo callara.
        _is_noop = bool(_extra.get("noop"))
        if msg and (not ok or not spoken_text or _resolved) and not (_is_noop and spoken_text):
            _clean = speech.sanitize(msg, drop_metadata=False)
            # HIGIENE (V2-047 F11, sesión 23:15 «…sin pausa.Con esta fuente gratis…»): el msg del conector se
            # concatenaba al texto del modelo SIN separador → dos frases pegadas. Si ya hay locución y no cierra
            # con espacio/puntuación, antepón un separador.
            if spoken_text and _clean and spoken_text[-1:] not in " \n.,;:!?¡¿—-":
                _clean = " " + _clean
            elif spoken_text and _clean and not _clean[:1].isspace():
                _clean = " " + _clean
            send(_clean)
            spoken_text = "".join(spoken).strip()
    _out = locals()
    return {k: _out[k] for k in ('spoken_text', ) if k in _out}
