"""The text channel AFTER the model has answered: execute what was decided, then the words the turn owes
(V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/probe.py::run_turn` (1,232 lines; `probe.py` was over its size ceiling): the block
that EXECUTES the turn's decision (confirmations, escalations, worker messages, data-ops, music/images/video) and
the block that composes the spoken line when the model said nothing, and the web-search branch
(`answer_a_search`). The code is the SAME; every name it read from
`probe` is read through the module (`_probe.<name>`), so a patch on `probe` still governs it. Each function takes
the turn's locals it read as keyword arguments and returns the ones the rest of `run_turn` reads, only when bound.
"""
from __future__ import annotations

from nucleo.flash import probe as _probe


async def _escalated_with_its_data_ops(task_ids: list, tool_calls: list, text: str, brief) -> dict:
    """The escalation's report — and a data-op of the SAME turn runs too, as in the voice channel, where each tool
    call runs as it streams (V2-781 T515). Measured: «prográmame el recordatorio… ¿y de dónde sacaste la fecha?» →
    escalate + an agenda add; this channel ran only the escalation, and the notice was never written."""
    out = {"executed": "escalate", "task_id": task_ids[0], "task_ids": task_ids}
    if any(t.get("name") == "widget_data" for t in tool_calls):
        out["widget_data"] = await _probe._widget_data_turn.execute(tool_calls, text=text, brief=brief)
    return out


def _send_each(tool_calls: list, text: str) -> dict:
    """Every `send_to_worker` of the turn, each to the worker its `which` names — the voice executor's behaviour.

    three-tasks-at-once (EN, 2026-10-10): this channel sent only the FIRST message, and to `which=""`, i.e. every
    live worker — «the monitor, no more than $150» landed in the report's worker and «jump higher» reached nobody.
    A turn with no usable message keeps the old fallback: the operator's words, to every worker."""
    from nucleo import dispatch as _disp
    sends = [(str(t["args"].get("which") or "").strip() or "todo", str(t["args"].get("message") or "").strip())
             for t in tool_calls if t.get("name") == "send_to_worker"]
    sends = [(w, m) for w, m in sends if m] or [("", str(text))]
    to: list[str] = []
    for which, msg in sends:
        _disp.inject_soon(which, msg)
        to += [n for n in _errand_names(_disp.resolve_sessions(which)) if n not in to]   # said back (three-tasks)
    return {"executed": "inject", "sent": len(sends), "to": to}


def _errand_names(tids) -> list[str]:
    """How the refinement's errands are named back to him: their label, or their request when the label is still
    the kind placeholder («Investigando…»)."""
    from nucleo import dispatch as _disp
    out = []
    for tid in tids or []:
        rec = _disp.get_record(tid)
        label = str(getattr(rec, "label", "") or "").strip()
        name = (label if label and not label.endswith("…") else str(getattr(rec, "goal", "") or "").strip())[:70]
        if name:
            out.append(name)
    return out


def _the_turns_errands(tool_calls: list, operator_text: str, window_goal: str, *, resolved: str | None = None):
    """(requests, surfaces, not_started) — every errand this turn asked for, decided by the shared rules.

    The escalations the model called, each with its declared surface (V2-227: a turn can ask for a list, a sheet
    and a widget, and the first one's screen is wrong for the other two); the create-widget CLAUSE when no outgoing
    request builds one (V2-118/V2-155: the whole turn says «informe» and the dedup ate the game by its target); a
    listing hunt that is none of them (three-tasks-at-once). `operator_text`, never `text`: an errand must not be
    the [SISTEMA] notes. With `resolved`, the errand a yes/no just answered is taken out and nothing falls back to
    the turn's words; without it an empty list falls back to the window goal (V2-132) or his sentence."""
    from nucleo.turn import errands_of_a_turn as _eot
    reqs: list[str] = []
    _surf: dict[str, str] = {}
    for _tc in tool_calls:
        _r = str(_tc["args"].get("request") or "").strip() if _tc["name"] == "escalate_to_slowbrain" else ""
        if _r and _r not in reqs:
            reqs.append(_r)
            _surf[_r] = str(_tc["args"].get("surface") or "").strip()
    listing = next((t["args"] for t in tool_calls if t["name"] == "search_listings"), None)
    if listing is not None and (rides := _eot.listing_rides(_probe._lt.request_from(listing, operator_text), reqs)):
        reqs.append(rides)
        _surf[rides] = "lista"
    try:
        from nucleo.flash import router_guards as _rg_cw
        if not any(_rg_cw.looks_like_create_widget(r) for r in reqs):
            if (_w_req := _rg_cw.create_widget_request(operator_text)):
                reqs.append(_w_req)
    except Exception:  # noqa: BLE001
        pass
    if resolved is not None:
        reqs = _eot.beside_an_answer(resolved, reqs)
    kept, dropped = _eot.within_the_pool(reqs or ([] if resolved is not None else [window_goal or operator_text]))
    return kept, _surf, dropped


def _launch(reqs: list, _surf: dict, *, trace_id: str, brief, text: str) -> list:
    """One escalation per request through the one portal (`escalate_to_slowbrain`); the DECISION to park an
    errand whose turn asked permission lives there (V2-655), so the spoken turn travels as `asked`."""
    from nucleo import surfaces as _surfaces
    from nucleo.flash import escalate as _esc
    return [_esc.escalate_to_slowbrain(str(_r), context={"src": "probe", "trace": trace_id, "asked": text,
                                                          "surface": _surfaces.pick(_surf.get(_r, ""),
                                                                                    _surfaces.from_brief(brief))})
            for _r in reqs]


async def execute_what_was_decided(*, _kind, _r, _res, _tbrief, _trace_id, _window_goal, action, execute, images_req, music_req, operator_text, sess, spoken, tags, text, tool_calls, video_req) -> dict:
    _beside = None    # three-tasks-at-once: the errands a yes/no did NOT resolve still start
    if execute:
        # CONFIRMACIÓN de una TAREA irreversible parada por el confirm-gate (V2-126) y del navegador parado en
        # un clic (V2-202). Va ANTES que el resto: un «sí» reanuda lo PARADO, no abre nada nuevo, así que tiene
        # que poder anular la escalada de este turno. La PRECEDENCIA entre puertas —un «sí» contesta a UNA
        # pregunta— la decide `nucleo/turn/confirm_gates.py` en una sola llamada, para este canal y para la voz:
        # este bloque eran dos copias hermanas de la de la voz, y la de la voz DERIVÓ (el guarda del segundo
        # bloque miraba la puerta equivocada y un «sí» autorizaba las dos cosas; medido 2026-08-24, nodo 2.29).
        # Aquí solo queda la BOCA: convertir la respuesta en el nombre de acción que el probe reporta.
        try:
            from nucleo.turn import confirm_gates as _gates
            _ans = _gates.resolve_all(text, brief=_tbrief)
            if _ans:
                action = "confirm_task" if _ans.yes else "confirm_task_no"
                _res = _ans.result if isinstance(_ans.result, dict) else {}
                if _ans.gate == "browser":
                    return_extra_exec = {"executed": "confirm_nav_task", "ok": _ans.yes,
                                         "task_id": str(_res.get("task_id") or "")}
                else:
                    return_extra_exec = {"executed": "confirm_task", "ok": bool(_res.get("ok"))}
                    _beside = _the_turns_errands(tool_calls, operator_text, "", resolved=str(_res.get("request") or ""))
        except Exception:
            pass
        # The three SCHEDULING backstops (promise → tag, execute the cron tags, write the commitment to
        # the agenda) moved to `probe_scheduling.py` in the 2026-09-02 ratchet pass. They were a closed
        # unit over these five locals, and `tags` is passed so the derived cron tag still lands in the
        # turn the caller reports. Still «espejo del provider — cablear en AMBOS».
        await _probe._probe_scheduling.run_scheduling_backstops(
            spoken=spoken, operator_text=operator_text, action=action, tags=tags, sess=sess)
        try:
            if action == "escalate" or (_beside and _beside[0]):
                # SEVERAL errands in one turn (V2-118), each WITH its declared surface (V2-227) — the decision lives
                # in `_the_turns_errands`, the launch in `_launch`. Beside a yes/no only what it did not resolve.
                _reqs, _surf, _left = _beside or _the_turns_errands(tool_calls, operator_text, _window_goal)
                _tids = _launch(_reqs, _surf, trace_id=_trace_id, brief=_tbrief, text=text)
                return_extra_exec = (await _escalated_with_its_data_ops(_tids, tool_calls, text, _tbrief)
                                     if action == "escalate" else {"executed": action, "beside": _tids})
                if _left:
                    return_extra_exec["not_started"] = _left   # said by `the_words_it_owes`
            elif action == "send_to_worker":
                return_extra_exec = _send_each(tool_calls, text)
            elif action == "answer_worker":
                _ans = next((t["args"].get("answer") or t["args"].get("text") for t in tool_calls
                             if t["name"] == "answer_worker"), "") or text
                from nucleo import worker_api as _wapi
                _wapi.answer_active_soon(str(_ans))
                return_extra_exec = {"executed": "answer"}
            elif action == "stop_worker":
                from nucleo import dispatch as _disp
                _which = next((t["args"].get("which") for t in tool_calls if t["name"] == "stop_worker"), None)
                _disp.cancel_soon(str(_which) if _which else text)   # resuelve which del modelo, o del texto (bulk→todas)
                return_extra_exec = {"executed": "stop"}
            # EL TRASPASO DE INICIO DE SESIÓN (V2-176, 2026-08-20 — mismo agujero que describe el bloque de cron de
            # abajo, y por la misma razón). `authenticate_web` y `login_done` se resolvían aquí a una ETIQUETA y nada
            # más: la voz llamaba a sus dos closures y este canal —el que usan los casos de uso— no ejecutaba nada.
            # Medido en `cancel-subscription-before-charge__es`: naturalidad 5, adaptación 5 (el diálogo era honesto:
            # se negó a fingir que tenía la cuenta y ofreció el traspaso) y luego «Aquí lo tienes» con
            # `navegador_task` VACÍO — no se abrió nada, así que «ya he entrado» no tenía tarea que reanudar y «dame
            # un momento que lo miro» no tenía nada que mirar. El juez lo llamó «una fachada vacía»: las palabras
            # eran ciertas y lo que faltaba era el cableado. Los 54 escenarios del segmento `credentials` pasan por
            # aquí, así que su mitad más importante era INMEDIBLE.
            #
            # La DECISIÓN vive en `web_auth.decide` (compartida con la voz), no aquí: música se conecta en su tarjeta
            # y mensajería por QR, nunca conduciendo un Chromium a spotify.com. Sin esa guarda, este cableado habría
            # roto dos invariantes en su primer turno.
            elif action == "authenticate_web":
                try:
                    from . import web_auth as _wa
                    _aw = next((t for t in tool_calls if t["name"] == "authenticate_web"), None)
                    _kind, _site = _wa.decide((_aw or {}).get("args", {}).get("site", ""), text)
                    if _kind == _wa.KIND_LOGIN:
                        _opened = _wa.start(_site)
                        return_extra_exec = {"executed": "authenticate_web", "site": _site, "task": _opened}
                    else:
                        # No se ejecuta, y se DICE cuál era: un `authenticate_web` que no abre navegador no es un
                        # fallo, es otro camino — y el que lee la corrida necesita distinguirlos.
                        return_extra_exec = {"executed": "", "authenticate_kind": _kind, "site": _site}
                except Exception as e:  # noqa: BLE001
                    return_extra_exec = {"execute_error": str(e)[:200]}
            elif action == "login_done":
                try:
                    from . import web_auth as _wa2
                    _resumed = _wa2.finish("texto")
                    # Un "" honesto: dijo que ya entró y no había ningún login esperando. Se reporta como tal en vez
                    # de dar el turno por bueno — es el mismo criterio que la confirmación caducada de V2-190.
                    return_extra_exec = {"executed": "login_done", "resumed": _resumed}
                except Exception as e:  # noqa: BLE001
                    return_extra_exec = {"execute_error": str(e)[:200]}
            elif action == "canvas:arrange":
                # V2-588 — el mismo emit que POST /api/canvas/arrange: el canvas de quien mire reacciona por SSE.
                from voice.observer import emit as _emit_arr
                _emit_arr("widget", "arrange", extra={"src": "flash"})
                return_extra_exec = {"executed": "arrange"}
            elif action == "canvas:show:imagenes" and images_req:
                # V2-457/463 — mismo rail que la voz (`image_turn`), que además abre la TARJETA: aquí no.
                return_extra_exec = await _probe._image_turn.execute(images_req["query"], images_req.get("n") or 12,
                                                              bool(images_req.get("more")))
            elif action == "canvas:show:youtube" and video_req:
                # V2-383 — EL VÍDEO SE PONE, NO SE ROTULA. Hermano de la música: mismo rail que la voz
                # (`brain_action` → `load` del widget `youtube`), que es quien de verdad busca y carga.
                return_extra_exec = await _probe._video_turn.execute(video_req["query"], video_req.get("action") or "play")
            elif action == "music" and music_req:
                # V2-380 — LA MÚSICA SE PONE, NO SE ROTULA. La decisión y su ejecución viven en
                # `music_turn`, igual que `web_auth` para el traspaso de login: este canal es la
                # implementación PARALELA del provider de voz y lo que se comparte es el MECANISMO.
                return_extra_exec = await _probe._music_turn.execute(music_req["action"], music_req["query"])
            elif action == "widget_data":
                # V2-469 — the links the operator pasted all travel: two links in one message, the model's
                # single add carried one. His own words verbatim, so completing invents nothing.
                return_extra_exec = await _probe._widget_data_turn.execute(
                    _probe._widget_data_turn.complete_pasted_links(tool_calls, text), text=text, brief=_tbrief)
            else:
                return_extra_exec = {}
            from . import probe_companions as _pc   # the other cards the same turn asked for (V2-781)
            if isinstance(return_extra_exec, dict) and (_comp := await _pc.run(
                    action, tool_calls, text, window=sess.window, brief=_tbrief)):
                return_extra_exec["companions"] = _comp
        except Exception as e:  # noqa: BLE001
            return_extra_exec = {"execute_error": str(e)[:200]}
    else:
        return_extra_exec = {}
    _out = {}
    try:
        _out['action'] = action
    except NameError:
        pass
    try:
        _out['return_extra_exec'] = return_extra_exec
    except NameError:
        pass
    return _out


async def the_words_it_owes(*, _hw, _parts, _show_chose, action, images_req, return_extra_exec, sess, spoken, tags, text, video_req, spec=None, brief=None) -> dict:
    if not spoken and any(t.get("action") == "aparte" for t in tags):
        pass          # V2-657 (espejo del provider): [[aparte]] es silencio SANCIONADO — ningún backstop lo rellena
    elif not spoken:
        try:
            from i18n import langs as _langs   # the voice.engine.core shim is this same module
            _lg = _langs.current_language()
            if action == "confirm_task":
                # V2-176 frente 1 — un «sí» a la puerta de confirmación ARRANCA la tarea; no la termina. Usaba
                # `data_ack` («Hecho.») y eso es una afirmación de hecho sobre algo que acaba de empezar.
                # Medido en `cancel-subscription-before-charge__es`, con el daño en las palabras del propio
                # operador: «Sí, adelante» → «Hecho.» → «**¿Ya está cancelada del todo?**». El juez lo marcó
                # grave («falsa confirmación de ejecución»), y no lo dijo el modelo: lo decía este ack.
                #
                # La medición sobre las 78 respuestas archivadas es lo que trajo aquí: solo 10 AFIRMAN un
                # hecho frente a 41 que expresan intención —el modelo casi siempre acierta— y las tres
                # afirmaciones sobre corridas donde el mecanismo no registró NADA son todas la misma palabra,
                # «Hecho.». O sea que la frontera que este frente buscaba no estaba en el prompt: estaba en
                # nuestras propias frases de relleno.
                from . import router_guards as _rg_ack
                spoken = _rg_ack.holding_line(sess.window, _lg)
            elif action == "widget_data" and isinstance(return_extra_exec, dict) and (
                    return_extra_exec.get("fallidas") or
                    return_extra_exec.get("executed") == "widget_data_failed"):
                # V2-394 — lo que el widget RECHAZÓ no sale como «Hecho.»; va ANTES de la rama de abajo.
                spoken = _probe._widget_data_turn.spoken_for(return_extra_exec, _lg.data_ack)
            elif action in ("widget_data", "confirm_task_no"):
                # Una data-op SÍ terminó, y un «no, déjalo» también resuelve algo de verdad: ahí «Hecho.» es
                # cierto. El turno que resuelve un sí/no tampoco puede caer al backstop genérico y contestar
                # «¿me lo repites?» a una confirmación.
                # V2-469 — but «Hecho.» to a QUESTION is a non-answer: when the operator asked something
                # and the model went mute over the op, the ack enumerates what the widget now holds.
                if action == "widget_data" and isinstance(return_extra_exec, dict):
                    spoken = (await _probe._widget_data_turn.answer_in_words(return_extra_exec, text, spec)  # T518
                              or _probe._widget_data_turn.named_ack(return_extra_exec, _lg.data_ack, text))
                else:
                    spoken = _lg.data_ack
            elif action == "canvas:show:imagenes" and images_req:
                # V2-457 — se NOMBRA cuántas y de quién, ANTES del ack genérico de `canvas:` (razón: la del vídeo).
                spoken = _probe._image_turn.spoken_for(
                    return_extra_exec if isinstance(return_extra_exec, dict) else {}, _lg.data_ack)
            elif action == "canvas:show:youtube" and video_req:
                # V2-383 — se NOMBRA el vídeo que cargó. Va ANTES del ack genérico de `canvas:` a propósito:
                # ahí abajo un turno de vídeo solo puede decir «aquí lo tienes» o —si no cargó— «está vacío»,
                # que es literalmente la frase que el tester leyó cuatro veces seguidas.
                spoken = _probe._video_turn.spoken_for(
                    return_extra_exec if isinstance(return_extra_exec, dict) else {}, _lg.data_ack)
            elif action.startswith("canvas:"):
                # V2-209 — abrir una tarjeta NO es entregar un resultado, y este ack lo afirmaba. Medido en
                # `book-hotel-night-known__es` (13:49): «Aquí lo tienes» sobre la tarjeta del navegador con la
                # tarea todavía trabajando y nada encontrado → «alucinación de éxito» para el juez. La decide
                # `router_guards` para que no pueda divergir entre canales, que es justo cómo esta clase de
                # fallo sobrevive (V2-176 frente 1, la misma historia con «Hecho.»).
                from . import router_guards as _rg_show
                # `split(":")[-1]` NO sirve: una tarjeta de INSTANCIA lleva dos puntos dentro
                #                 (`canvas:show:navegador::t1` → «t1», que no es ningún widget).
                _parts = action.split(":", 2)
                # the OPEN phrase only for an open: «I've opened it, though there's nothing in it yet» over a close
                # was the demo pass's S4 (2026-09-28)
                spoken = (_rg_show.show_ack(_lg, _parts[2] if len(_parts) > 2 else "", chose=_show_chose)
                          if _parts[1] == "show" else _lg.data_ack)
            elif action.startswith("panel:"):
                # V2-761 — a native panel opened with no spoken line. The provider counts it as `acted["widget"]`
                # and speaks `show_ack`; this mirror fell to the MUTE backstop and blamed itself («se me ha
                # cruzado algo») over a panel that had opened — measured on his own Apps phrases.
                from . import router_guards as _rg_panel
                spoken = _rg_panel.show_ack(_lg, "")
            elif action in ("escalate", "send_to_worker", "stop_worker", "answer_worker", "authenticate_web",
                            "connect_cluster"):
                # V2-189: nunca la MISMA frase dos veces (espejo del provider — cablear en AMBOS).
                from . import router_guards as _rg_hold
                from nucleo.turn import errands_of_a_turn as _eot   # a status question owes the phases (three-tasks)
                _stopped = isinstance(return_extra_exec, dict) and return_extra_exec.get("executed") == "stop"   # a stop he ordered is DONE, never «a moment»
                _to = (return_extra_exec.get("to") if isinstance(return_extra_exec, dict) else None) or []   # «del informe quítame…»
                spoken = ((_stopped and _lg.worker_stopped) or (action != "escalate" and _eot.status_owed(text, brief))
                          or (_to and _lg.errand_refined.format(what="; ".join(f"«{t}»" for t in _to[:3])))
                          or _rg_hold.holding_line(sess.window, _lg))
            elif action == "music":
                # V2-380 — la BOCA dice lo que PASÓ, no «Hecho.» pase lo que pase. Misma casa que la ejecución.
                spoken = _probe._music_turn.spoken_for(
                    return_extra_exec if isinstance(return_extra_exec, dict) else {}, _lg.data_ack)
            elif action in ("style", "attention_mode", "rename_assistant"):   # V2-046 A1 + identity_actions 2026-09-09: una acción HECHA nunca sale muda ni con ack de culpa
                spoken = _lg.data_ack   # («Perdona, se me ha ido» medido en vivo sobre el toggle YA aplicado)
            else:
                # BACKSTOP GENÉRICO — turno de CHARLA pura (`action=="chat"` u otro no cubierto arriba) que
                # salió MUDO: el modelo no llamó a ninguna tool Y no dijo nada. Live bug (search-buy-used-car,
                # 2026-08-17): ninguno de los casos de arriba está gateado a `action=="chat"`, así que un turno
                # de check-in ("¿pudiste relanzarla?") con el modelo genuinamente sin respuesta se quedaba en
                # silencio total — y el turno SIGUIENTE, viendo ese hueco en la ventana, acabó ECOANDO la propia
                # pregunta del operador ("Dime algo, por favor. ¿Se relanzó la búsqueda...?", literalmente sus
                # palabras). Espejo del backstop genérico de `nucleo.py` (impl PARALELA, cablear en AMBOS).
                spoken = _probe._rg_mute.mute_backstop(sess.window, _lg, _hw, operator_text=text)   # V2-603: rotates, owns the fault
        except Exception:
            pass
    if isinstance(return_extra_exec, dict) and return_extra_exec.get("not_started"):   # three-tasks-at-once
        from nucleo.turn import errands_of_a_turn as _eot
        spoken = f"{spoken or ''} {_eot.not_started_line(return_extra_exec['not_started'])}".strip()
    _out = {}
    try:
        _out['_lg'] = _lg
    except NameError:
        pass
    try:
        _out['spoken'] = spoken
    except NameError:
        pass
    return _out


async def answer_a_search(*, FastClient, _forced_search, _res, action, dialog, operator_text, spec, speech, text, tool_calls,
                          _tbrief=None) -> dict:
    if action == "search":
        _sq = next((t["args"].get("query") for t in tool_calls if t["name"] == "web_search"), "") or text
        # Demo pass 109, C2 — a search the card ANSWERS goes to the card (`card_commission.instead_of_a_search`).
        from . import card_commission as _cc_s
        _card = await _cc_s.instead_of_a_search(_sq, brief=_tbrief, operator_text=operator_text or text, spec=spec)
        if _card and _card.get("kind") == "call":
            tool_calls.append({"name": "widget_data", "args": {"widget_id": _card["widget_id"], "action": _card["action"],
                                                               "payload": _card["payload"], "_repair": True}})
            return {"action": "widget_data", "spoken": ""}
        try:
            from nucleo.flash import search_routing as _sr          # V2-782: the service's route, in shadow
            from voice.observer import emit as _emit_route
            _sr.shadow(_sq, proposal="web_search", brief=_tbrief, emit=_emit_route, channel="probe")
            from nucleo import websearch as _ws
            _t_s = _probe.time.time()
            _res = await _probe.asyncio.to_thread(_ws.search, _sq)
            _ctx = _ws.format_results(_res)
            # PARIDAD DE OBSERVABILIDAD con el canal vivo (2026-08-10). El probe es una implementación PARALELA
            # del turno, y este camino no registraba nada: una búsqueda hecha por el canal de prueba no dejaba ni
            # la fila `search` ni su evidencia, así que auditar lo que hace el sistema dependía de por dónde
            # hubiera entrado la frase — justo el tipo de punto ciego que esta capa existe para no tener.
            try:
                from observability import evidence as _evd
                from voice.observer import emit as _emit_obs
                _x = {"source": _res.get("source"), "ai": bool(_res.get("ai")),
                      "n": len(_res.get("results", [])), "ms": round((_probe.time.time() - _t_s) * 1000),
                      "src": "probe", "evidence": _evd.web_results(_res.get("results"))}
                _a = _evd.body(_res.get("answer"))
                if _a:
                    _x["evidence"]["answer"] = _a
                _emit_obs("search", "🔎 resultados web", text=_sq, role="system", extra=_x)
            except Exception:
                pass
            # V2-676 — the prompt lives in `flash/search_turn`, shared with the voice channel (it was a
            # parallel impl since V2-135, and the missing half — telling the model WHY a search came back
            # empty — was missing in both). `denial_repair` is the backstop for the sentence the prompt bans.
            from . import search_turn as _st
            from nucleo import canvas_focus as _cf_s
            _sys2 = _st.compose_system(operator_text, _sq, _res, _ctx, on_screen=_cf_s.this_turn_cards())
            _parts = []
            async for _delta in FastClient().stream(
                    [{"role": "system", "content": _sys2}, {"role": "user", "content": operator_text or _sq}],
                    spec=spec, max_tokens=_st.MAX_TOKENS):
                _parts.append(_delta)
            spoken = _st.denial_repair(
                dialog.sanitize_reply(speech.sanitize("".join(_parts), drop_metadata=False)), _res)
            # V2-781 T515 — an ORDER beside the fact («set a reminder for the premiere day»): the answer pass has no
            # tools and refused it. The call goes to the execute block below like any other (same `execute` gate).
            from . import act_repair as _ar_s
            _after = await _ar_s.call_after_search(operator_text or text, spoken, _tbrief, spec)
            if _after:
                tool_calls.append({"name": "widget_data", "args": {"widget_id": _after["widget_id"],
                                   "action": _after["action"], "payload": _after["payload"], "_repair": True}})
                action = "widget_data"
                spoken = (_ar_s.without_the_denial(spoken)
                          + _ar_s.after_the_repair(spoken, False, _after["widget_id"], _after["action"])).strip()
        except Exception:
            # Con la búsqueda CAÍDA, dejar la respuesta original sería quedarnos justo con el dato improvisado
            # que este backstop existe para no dar. Un «no lo he podido comprobar» es peor respuesta y mejor
            # información. Solo aplica al turno FORZADO: uno que el modelo enrutó a búsqueda ya tenía su propia
            # frase y no hay nada que retirar.
            if _forced_search:
                try:
                    from i18n import langs as _lg_src   # the voice.engine.core shim is this same module
                    spoken = _lg_src.current_language().unverified_fact
                except Exception:  # noqa: BLE001 — V2-682: the last resort is the PRODUCT default (English),
                    from i18n.langs import LANGUAGES  # never a Spanish literal an English operator cannot read
                    spoken = LANGUAGES["en"].unverified_fact
    _out = {'action': action}
    try:
        _out['spoken'] = spoken
    except NameError:
        pass
    return _out
