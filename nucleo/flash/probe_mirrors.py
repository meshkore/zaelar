"""The text channel's MIRRORS of the voice backstops: a show by name, a promise without an action, work handed back,
a marketplace to browse, a short close, a card completed or closed by its verdict, an answer to a waiting worker,
a stop nobody called, the web errand behind a promise and the fact that is never improvised (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/probe.py::run_turn` with no behaviour change. Every name the block read from `probe` is
read through the module (`_probe.<name>`), so a patch on `probe` still governs it.
"""
from __future__ import annotations

from nucleo.flash import probe as _probe


def _a_show_may_replace(action: str, names) -> bool:
    """An escalate/search turn the show backstop may turn into a show — never one that also wrote a card, the voice
    guard's `not acted["widget"]` (V2-781 T515: «¿de dónde has sacado esa fecha?» read «saca» + «fecha» as «show the
    clock» and threw the turn's agenda write away)."""
    return action in ("escalate", "search") and "widget_data" not in names


async def mirror_the_voice_backstops(*, _akp, _cw, _hw, _router, _rt, _sp, _tbrief, action, canvas_h, dialog, names, operator_text, sess, spec, speech, spoken, tags, text, tool_calls) -> dict:
    # V2-778 F2-16 — the voice turn's question, asked the same way here: did the reply promise something?
    from nucleo.flash import reply_promise as _reply_promise
    await _reply_promise.prefetch("".join(spoken).strip() if isinstance(spoken, list) else str(spoken or ""),
                                  operator_text)
    if _a_show_may_replace(action, names):
        wid = _probe._show_target(text, sess.window, sess.last_action)
        if not wid:
            # Jev show license (T-jev-show-close, lector COMPARTIDO `show_target.show_from_verb`,
            # nunca una segunda implementación): un "show" seguro + identify real rescata un fallo
            # de la gramática; lo demás deja el camino de hoy intacto.
            from nucleo.flash import show_target as _st_show
            try:
                wid, _show_src = _st_show.show_from_verb(text, canvas_h)
            except Exception:
                wid, _show_src = None, "none"
        if wid:
            # V2-605 F2 — mirror of the voice fallback: resolve the CARD, not just the piece. This backstop has
            # no channel to ask through, so it only ever narrows (`instances.show_id`).
            action = f"canvas:show:{_probe._show_card(wid, text)}"
    _window_goal = ""    # V2-132: objetivo recuperado de la ventana cuando la promesa no lo lleva en su turno
    # BACKSTOP PROMESA-SIN-ACCIÓN UNIFICADO (espejo del provider): el modelo charló una promesa sin tool → re-deriva
    # la intención. Gated por la promesa en la RESPUESTA. Generaliza sobre conjugaciones/cortesías.
    # V2-770 — a show of a card that is already open, on a turn whose verdict names an action INSIDE it, is not
    # the act («ábreme la ficha del dentista» → show_widget(agenda) over an open agenda): the repair runs.
    try:
        from . import direct_action as _da_show
        if action.startswith("canvas:show:") and _da_show.order_is_inside(_tbrief, action.split(":", 2)[2]):
            action = "chat"
    except Exception:
        pass
    if action == "chat" and spoken:
        try:
            from . import router as _routerc
            # Mirror of the voice provider: a reply that ASKS the operator for the detail it needs is not a
            # promise it failed to keep, so nothing is re-derived from it (V2-534). Wired in BOTH channels
            # because this class of defect survives by diverging between them.
            _ar = None
            from . import direct_action as _da_probe
            # full44 M1 — mirror of the voice door: the repair judges its own reply, the door needs no wording table
            if not _routerc.asks_for_missing_detail(spoken):
                # V2-764 — mirror of the voice repair (`act_repair`), gated like it on the verdict too (V2-770).
                from . import act_repair as _act_repair, card_commission as _cardc_probe
                _ar_wid = _cardc_probe.named_or_catalogue(_tbrief, operator_text)
                _pv_o, _pv_a = _da_probe.from_brief(_tbrief)
                _ar = (await _act_repair.call_for_promise_or_order(operator_text, spoken, _ar_wid, _pv_a if _pv_o == _ar_wid
                       else "", spec=spec, window=getattr(sess, "window", None), brief=_tbrief) if _ar_wid   # V2-781 p3, T529
                       else await _act_repair.probe_call_for_promise(operator_text, spoken, spec, window=getattr(sess, "window", None)))
            if _ar:
                # «widget_data», the label the executor matches — a richer label here meant the repaired call was
                # recorded and never RUN in this channel (V2-770: «Hecho.» over an untouched agenda).
                action = "widget_data"
                tool_calls.append({"name": "widget_data", "args": {"widget_id": _ar["widget_id"],
                                   "action": _ar["action"], "payload": _ar["payload"], "_repair": True}})
                spoken = ""          # its words were about a call it never made; the result speaks now
            elif (_routerc.promises_playback(spoken, text, music_open=_da_probe.on_screen_now("musica"))
                  and not _routerc.asks_for_missing_detail(spoken)):
                # mirror of the provider's U2 branch: an ENGLISH promise of playback plays, with the title its words carry
                action = "music"
                music_req = {"action": "play", "query": _routerc.music_query(spoken, text)}
            elif _routerc.promises_action(spoken) and not _routerc.asks_for_missing_detail(spoken):
                if (_routerc.looks_like_create_widget(text) or _routerc.looks_like_escalate_task(text)
                        or _routerc.looks_like_create_widget(spoken) or _routerc.looks_like_escalate_task(spoken)):
                    action = "escalate"
                # V2-132: the request may have been made a turn or two back — zaelar asked for the missing
                # detail (correct), the operator gave it, and the promise landed on a turn whose text
                # describes no task by itself. Only when NOTHING is running: with a live task, "sigo con
                # ello" is honest and re-escalating would run the same work twice.
                # V2-176: `_hw` contesta «¿hay algo corriendo?» y lo que decide es «¿hay algo corriendo PARA
                # ESTO?». Medido en `book-hotel-night-known__es`: el encargo del hotel no escaló porque seguía
                # vivo un worker del encargo ANTERIOR, y luego «la reserva sigue en marcha» durante cuatro
                # turnos sobre una tarea de Ticketmaster ya cancelada. El razonamiento de la puerta era correcto
                # e incompleto: con una tarea viva «sigo con ello» ES honesto y re-escalar SÍ duplicaría el
                # trabajo — pero solo si la tarea viva es de lo que se ha pedido.
                elif (_wgoal := _routerc.escalate_goal_from_window(sess.window, text)) and (
                        not _hw or _routerc.nothing_running_for(_wgoal, _probe._running_goals())):
                    action = "escalate"
                    _window_goal = _wgoal
                elif _routerc.looks_like_show_strict(text):
                    from widgets import runtime as _rtp
                    _idp = _rtp.identify(text) or {}
                    _pw = _idp.get("match")
                    _wtab = "" if _pw else _probe._wall_tab_for(_idp.get("system"), text)
                    if _pw:
                        action = f"canvas:show:{_pw}"
                    elif _wtab:
                        action = f"panel:{_wtab}"      # V2-761 — mirror: a promised TAB of the wall
                elif _routerc.promises_music(spoken):
                    action = "music"
        except Exception:
            pass

    # BACKSTOP DE TRABAJO DEVUELTO (V2-142, espejo del provider — cablear en AMBOS). Distinto del de promesa:
    # aquí el modelo no promete nada, MANDA AL OPERADOR a buscar en Google/Maps lo que él acaba de pedir. Medido:
    # «¿puedes buscar tú el teléfono?, para eso te pido ayuda» → «la forma más fiable es que tú busques
    # "farmacia" en Google Maps y me pases el teléfono». Una regla de prompt sola no basta para esto: lo que hace
    # falta es HACER la búsqueda, y para eso hay worker y navegador. Solo si NADA corre — con una tarea viva la
    # frase puede ser una sugerencia mientras se trabaja, y re-escalar duplicaría el trabajo (V2-123).
    if action == "chat" and spoken and not _hw:
        try:
            from . import router as _routerh
            if _routerh.hands_public_lookup_back(spoken):
                action = "escalate"
                _window_goal = (_routerh.escalate_goal_from_window(sess.window, text) or _window_goal
                                or operator_text)
        except Exception:
            pass

    # GUARD MARKETPLACE → NAVEGAR (V2-057 2026-07-21, espejo del provider): un sitio de compraventa NOMBRADO
    # (Idealista/coches.net/Wallapop…) exige ENTRAR y navegar el catálogo, no un dato puntual de web_search ni un
    # "no puedo". Si el modelo eligió search/chat/show pero el texto nombra un marketplace → escala (navegador).
    # Alta precisión: el nombre del sitio + una intención de búsqueda/compra es señal fuerte de navegar.
    if action in ("search", "chat", "widget_data") or action.startswith("canvas:show") or action.startswith("canvas:unknown"):
        try:
            # V2-677 — the SAME function the voice channel calls, not a copy of it (V2-252).
            from . import escalation_guard as _eguard
            if _eguard.escalation_text(operator_text, text):
                action = "escalate"
        except Exception:
            pass

    # BACKSTOP de CIERRE corto (sesión 22:40 2026-07-16, espejo del provider — cablear en AMBOS): «Vale,
    # ciérralo» → el modelo dice "cerrado" SIN emitir [[close]] (o cuela una data-op tipo mute). Orden corta de
    # cerrar (≤5 palabras, verbo de cerrar sin borrar) y ningún close en el turno → la voz cierra el widget
    # nombrado o el ÚNICO abierto; el probe lo reporta igual.
    # verbos AMPLIOS ('apaga/quita'): NO pises una acción ya tomada — si el turno resolvió MÚSICA ('apaga la música'
    # =stop audio), VÍDEO, búsqueda o data-op, el backstop de cierre NO cierra el widget además (espejo del guard
    # music_req/data_done del provider).
    # music/video/search/data ya resolvieron → no cerrar además. PERO un canvas:show ESPURIO en un turno de cerrar
    # SÍ debe corregirse a close (el modelo eligió show para 'podrías cerrar el reloj') → no lo metemos en _already.
    # BUG real 2026-07-23: "quita la pantalla completa" (verbo amplio 'quita' + turno corto + 1 widget abierto) NO
    # estaba en esta lista → el backstop de cierre de abajo CERRABA el widget entero en vez de solo salir de
    # fullscreen (fullscreen_widget YA resolvió la intención real este turno).
    _already = action.startswith(("music", "video", "search", "widget_data", "canvas:fullscreen", "canvas:minimize",
                                  "canvas:close"))            # close_widget already decided (demo pass 2026-09-28)
    # Mirror of the voice `complete_canvas` (demo pass 2026-09-28): no call, no tag, and the brief SURELY names a
    # canvas gesture → that gesture on the turn's card.
    if not _already and not tool_calls and not tags:
        try:
            from voice.observer import emit as _emit_cc
            from . import direct_action as _da_cc
            _cc: list = []
            _verb = _da_cc.complete_canvas(_tbrief, tag_emit=lambda a, x: _cc.append((a, x)), emit=_emit_cc,
                                           operator_text=operator_text)
            if _verb == "arrange":
                action, _already, spoken = "canvas:arrange", True, ""
            elif _verb and _cc:
                _cid = str(_cc[0][1].get("id") or "")
                action = {"close": f"canvas:close:{_cid}", "minimize": f"canvas:minimize:{_cid}",
                          "fullscreen": f"canvas:fullscreen:{_cid}"}.get(_verb, f"canvas:unfullscreen:{_cid}")
                _already, spoken = True, ""
        except Exception:
            pass
    # Mirror of the voice `closes_the_named_card` (demo pass 2026-09-28, V7): a data-op inside a card he ALSO told
    # to close by its name closes the card after the op.
    if action == "widget_data" and not any(t["action"] == "close" for t in tags):
        try:
            from . import direct_action as _da_cn
            _ops = [(str((c.get("args") or {}).get("widget_id") or ""), str((c.get("args") or {}).get("action") or ""))
                    for c in tool_calls if c.get("name") == "widget_data"]
            _cn = _da_cn.closes_the_named_card(_tbrief, operator_text, _ops)
            if _cn:
                tags.append({"action": "close", "extra": {"id": _cn, "verdict": True}})
        except Exception:
            pass
    # V2-770 — the mirror of the voice `direct_action.complete`: a turn with no call whose verdict names an action
    # INSIDE an open card («ya la puedes cerrar» → agenda:close_meeting) runs that action — and the close
    # backstop below, which would have shut the whole card, never sees it.
    if not _already and not any(t["action"] == "close" for t in tags) and not model_already_acted(tool_calls):
        try:
            from . import direct_action as _da_bs
            if (_da_bs.names_an_order(_tbrief) and __import__("nucleo.flash.verdict_card", fromlist=["x"]).canvas_yields(_tbrief)
                    and (_rung := _da_bs.resolve(operator_text, brief=_tbrief, operator_text=operator_text,
                                                 model_words=spoken if isinstance(spoken, str) else ""))):
                tool_calls.append({"name": "widget_data", "args": {"widget_id": _rung["widget"],
                                   "action": _rung["action"], "payload": _rung["payload"], "_verdict": True}})
                action, _already, spoken = "widget_data", True, ""
        except Exception:
            pass
    if not _already and not any(t["action"] == "close" for t in tags):
        try:
            from . import close_guards as _closeg, router as _router0
            # AMPLIADO (sesión absurda 2026-07-19, espejo del provider): cerrar un widget NOMBRADO que está ABIERTO
            # cierra AQUÍ aunque el turno sea largo (una queja acompañaba «cierra el widget de música» → escaló a
            # modificar código y giró en bucle). Cerrar ≠ tarea de código.
            # V2-600 (espejo del provider — cablear en AMBOS): un turno que MENCIONA «pantalla completa» habla
            # del estado de pantalla (salir de él, o narrarlo), nunca es una orden de cierre para un backstop —
            # medido 2026-09-05: la queja del operador sobre un cierre indebido volvió a cerrar el widget.
            from voice import attention as _att_fs
            if _router0.looks_like_close(text) and not _router0.looks_like_create_widget(text) \
                    and not _att_fs.mentions_fullscreen(text):
                try:
                    from memory import api as _memapi
                    _ow = list((_memapi.state() or {}).get("open_widgets") or [])
                except Exception:
                    _ow = []
                _cw = None
                try:
                    from widgets import runtime as _rt
                    # los ABIERTOS desempatan ("cierra el vídeo": vídeo empata navegador↔youtube; gana el abierto)
                    _idc = _rt.identify(text, open_ids=_ow) or {}
                    if not _idc.get("ambiguous"):
                        _cw = _idc.get("match")
                except Exception:
                    _cw = None
                if not _cw and _closeg.is_short_order(text) and len(_ow) == 1:
                    _cw = _ow[0]
                if _cw:
                    tags.append({"action": "close", "extra": {"id": _cw, "backstop": True}})
                    action = "canvas:close:" + _cw
        except Exception:
            pass

    # BACKSTOP de RESPUESTA A WORKER (espejo del provider — cablear en AMBOS): un worker ESPERA respuesta y el turno
    # corto ES esa respuesta, aunque el modelo mis-rutee a escalate/chat. Precede a la escalada espuria.
    if _akp and action in ("escalate", "chat") and "widget_data" not in names and len(text) <= 140:
        action = "answer_worker"

    # BACKSTOP de PARADA (espejo del provider L1182 — cablear en AMBOS): hay workers vivos, el operador ordena parar
    # trabajo y el modelo NO llamó stop_worker → se para de forma determinista (looks_like_stop_work). Cubre 'para
    # todas las tareas' cuando el no-razonador no emite la tool.
    if action == "chat" and "escalate_to_slowbrain" not in names:
        try:
            from nucleo import dispatch as _disp0
            from . import router as _router1
            if _disp0.has_active() and _router1.looks_like_stop_work(text):
                action = "stop_worker"
        except Exception:
            pass

    # BACKSTOP promesa-sin-acción → escalada de gestión WEB (V2-049, espejo del provider — cablear en AMBOS): el
    # modelo rápido a veces dice «me pongo con ello» sin llamar a escalate_to_slowbrain; si es una tarea web real,
    # la escalada la forzamos NOSOTROS (determinista). Arregla el «¿por qué te has parado?».
    if action == "chat" and spoken:
        import re as _re_prom
        _committed = bool(_re_prom.search(
            r"\b(me pongo con|me pongo a|ahora mismo|lo hago|lo hago ya|te lo (?:reservo|busco|miro|preparo|hago|"
            r"gestiono)|arranco|voy (?:con|a por|alla|alli|ya)|me meto en|enseguida|me encargo|lo pongo en marcha|"
            r"entro (?:en|a) la web)\b",
            "".join(c for c in __import__("unicodedata").normalize("NFKD", spoken) if not __import__("unicodedata").combining(c)).lower()))
        if _committed and _router.looks_like_web_task(text):
            action = "escalate"

    # PARIDAD con el canal vivo: recall y web_search are two-pass LIGHT routes. Historically the probe only
    # reported the tool and returned an empty reply, so a chronological headless conversation lost the assistant
    # turn and every following pronoun was tested against a state that can never occur in production.
    # recall · read_widget — see second_pass's docstring; a read that served an order returns "" (V2-781 T518)
    spoken, action = await _probe._second.probe_light_routes(
        action, names, tool_calls, text, operator_text, spec,
        lambda s: dialog.sanitize_reply(speech.sanitize(s, drop_metadata=False)), brief=_tbrief, reply=spoken)
    # V2-210 — UN DATO DEL MUNDO NO SE IMPROVISA (espejo del provider — cablear en AMBOS). Medido en
    # `quick-fact-opening-hours`: «abre a las 10:00 y cuesta 15 €» con CERO herramientas. Las cifras eran
    # aproximadamente correctas, que es justo lo que lo hace peligroso — el modelo va seguro y no pide la tool.
    # Convertir el turno en `search` reusa la maquinaria que ya existe aquí abajo (V2-022 + la composición de
    # V2-135), así que el dato inventado se SUSTITUYE por el que traiga la fuente, no se adorna.
    _forced_search = False
    if action == "chat" and spoken:
        try:
            from . import router_guards as _rg_src
            if _rg_src.answer_needs_a_source(operator_text, spoken):
                action, _forced_search = "search", True
            else:
                # V2-572/587/645 — the post-turn repairs (a bare «Hecho.» over a question, «sigo con
                # ello/ella» over nothing), extracted to ONE home shared with the voice seam: probe.py sat
                # over its ratchet ceiling and the parallel impl these comments used to apologise for is gone.
                spoken = await _probe._second.probe_hollow_repairs(operator_text, spoken, sess.window, spec)
        except Exception:
            pass
    _out = locals()
    return {k: _out[k] for k in ('_ar', '_forced_search', '_window_goal', 'action', 'music_req', 'spoken', ) if k in _out}


def model_already_acted(tool_calls) -> bool:
    """The model READ the card: that is the turn's call, and the verdict backstop (for a turn with NO call) stays out
    (V2-781: «what do I have on those days?» → read_widget, plus a verdict `show_day` of his whole sentence = today)."""
    return any((t or {}).get("name") == "read_widget" for t in tool_calls or [])
