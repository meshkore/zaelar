"""The text channel names the turn's ACTION from what the model called (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/probe.py::run_turn` (1,000 lines): the chain that reads the hard interrupt and the tool
names the model emitted and decides which single action the probe reports — and, for the media and secret tools,
what to execute below. The code is the SAME; every name it read from `probe` is read through the module
(`_probe.<name>`), so a patch on `probe` still governs it.
"""
from __future__ import annotations

from nucleo.flash import build_decision as _build_decision
from nucleo.flash import hard_turn as _hard_turn
from nucleo.flash import probe as _probe
from nucleo.flash import task_recall as _task_recall


#: The model's calls to a live worker, in the order they win (stop before a message, a message before an answer).
_WORKER_CALLS = ("stop_worker", "send_to_worker", "answer_worker")


def _worker_call(names) -> str:
    return next((n for n in _WORKER_CALLS if n in names), "")


def _hard_that_ends_the_turn(text: str, hard):
    """V2-778 F2-22 — the voice turn's hard interrupt (`hard_turn.handle`) lets the turn go on when a short stop is
    aimed at a live worker, and when the close or the stop was not all the sentence ordered. The same two questions
    here, so «para eso» names `stop_worker` and «cierra todo y ábreme la agenda» names the open."""
    if hard and (_hard_turn.is_worker_stop(text, hard) or _hard_turn.remainder(text, hard)):
        return None
    return hard


async def _reopen_action(tool_calls, text: str) -> str:
    """V2-778 F2-22 — the voice turn answers `reopen_task` with `task_recall` (lexical index → Jev → ask when several
    fit, V2-728). Same decision here, DRY like `connect_cluster`: it resolves which errand he means and names the show
    or the question, without rebuilding the sheet a headless channel would never see."""
    import asyncio
    q = next((t["args"] for t in tool_calls if t["name"] == "reopen_task"), {}) or {}
    r = await asyncio.to_thread(_task_recall.resolve, str(q.get("query") or "").strip() or text)
    return "canvas:show:results" if r.get("ok") else "clarify"


def _builds(text: str, router, brief) -> bool:
    """V2-778 F2-22 — the SAME decision the voice turn asks (V2-750): the grammar proposes, the verdict vetoes a
    create over a card we already have."""
    return _build_decision.decide(text, brief=brief, proposed=router.looks_like_create_widget(text))[0]


async def name_the_action(*, _hard, _router, _tbrief, _vault_gate, ingest, names, sess, tags, text, tool_calls) -> dict:
    _hard = _hard_that_ends_the_turn(text, _hard)
    if _hard == "close":
        action = "canvas:close"
    elif _hard == "stop":
        action = "chat"
    elif _wcall := _worker_call(names):
        action = _wcall
    elif "escalate_to_slowbrain" in names:
        action = "escalate"
    elif "reopen_task" in names:
        action = await _reopen_action(tool_calls, text)
    elif "search_listings" in names:
        # V2-556: the LISTING fast pass. Above web_search for the same reason escalate is: a turn that hunts
        # ads AND asks a fact is a hunt. The heavy side effects (search + possible self-escalation) run only
        # under `execute`, mirroring how `escalate` is reported here but executed further down.
        action = "listings"
    elif "read_widget" in names:
        action = "read_widget"               # V2-668: lee lo que guarda un widget — ruta ligera, se compone abajo
    elif "web_search" in names:
        action = "search"
    elif "reveal_secret" in names:
        # V2-060: el operador pide un secreto guardado. El DESENLACE lo resuelve la puerta compartida (F1); lo
        # que es de ESTE canal es que la respuesta viaje SIN el valor — va al arnés y a los logs de casos de uso,
        # así que `as_probe_payload()` lo deja fuera por construcción en vez de por acordarse de tirarlo.
        action = "reveal_secret"
        _rl = next((t["args"].get("label") for t in tool_calls if t["name"] == "reveal_secret"), "") or text
        from nucleo.turn import vault_gate as _vault_gate
        reveal_out = (await _vault_gate.reveal(str(_rl))).as_probe_payload()
    elif "play_music" in names:
        action = "music"                     # V2-041: ruta ligera; la EJECUTA el bloque `execute` de abajo (V2-380)
        music_req = _probe._music_turn.request_from(tool_calls)
    elif "play_video" in names:
        from nucleo.flash import canvas_license as _lic_v
        if _lic_v.video_license(text, _probe._last_assistant_line(sess.window), brief=getattr(sess, "brief", None)):
            action = "canvas:show:youtube"   # V2-045: VER → widget youtube (show + data-op load); espejo del provider
            video_req = _probe._video_turn.request_from(tool_calls)   # V2-383: y se EJECUTA abajo, como la música
        else:
            # V2-635 (espejo del provider): un turno que no pide ningún vídeo no carga ninguno — arrastre.
            action = "chat"
    elif "show_images" in names:
        action = "canvas:show:imagenes"      # V2-457: FOTOS → visor `imagenes`; espejo del provider
        images_req = _probe._image_turn.request_from(tool_calls)
    elif "show_panel" in names:
        # V2-079: abre el PANEL nativo lateral (chat/procesos/crons) por voz — espejo del provider (emite `panel`).
        _sp = next(t for t in tool_calls if t["name"] == "show_panel")
        action = "panel:" + _router._canon_panel(_sp["args"].get("panel"))
        if action == "panel:apps":   # V2-761 — mirror: his words pick the Custom sub-tab
            action = "panel:" + _probe._wall_tab_for("apps", text)
    elif "manage_widget_alias" in names:
        # V2-082 — classification only (the provider writes manifests); body lives with its siblings in
        # `show_target.py` since the 2026-09-03 ratchet pass.
        action = _probe.classify_alias_call(tool_calls, text)
    elif "show_widget" in names:
        # MOSTRAR una pieza por NOMBRE/ALIAS con CERTEZA (V2-082) — espejo del provider: CREATE→escala; si hay match
        # de widget → [[show:id]]; si nombró el CHAT (superficie) → panel; sin match → PREGUNTA (clarify), NUNCA
        # fabrica un widget ("no se abre el más parecido").
        _sw = next(t for t in tool_calls if t["name"] == "show_widget")
        _swid = (_sw["args"].get("widget_id") or "").strip()
        if _router.show_contradicts_the_order(text):
            # V2-567 — this file already carried the rule in prose (see the close backstop below: «un canvas:show
            # ESPURIO en un turno de cerrar SÍ debe corregirse»); now both channels apply it as code. The action
            # string stays out of `_already`, so the close backstop below still closes the NAMED widget.
            action = "guard:show-contradicts-close"
        elif _builds(text, _router, _tbrief):
            action = "escalate"
        else:
            from widgets import runtime as _rt
            _res = {}
            try:
                _contextual = _probe._show_target(text, sess.window, sess.last_action)
                if _contextual:
                    _res = {"match": _contextual, "system": None}
                elif _swid and _rt.get(_swid) is not None:
                    _res = {"match": _swid, "system": None}
                else:
                    _o, _r = _probe._ctx_ids()
                    _res = _rt.identify(_swid or text, open_ids=_o, recent_ids=_r) or {}
            except Exception:
                _res = {}
            _rid = _res.get("match") or ""
            _rid = _rid if (_rid and _rt.get(_rid) is not None) else ""
            _sys = _res.get("system")
            _show_ask = ""
            _reopen_drag = False
            if _rid:
                # V2-650b — mirror of the voice guard: a widget the operator JUST closed does not reopen
                # over a turn whose words ask for nothing of the kind (parallel impl, wire in BOTH).
                from nucleo.flash import canvas_license as _lic_s
                _o2, _r2 = _probe._ctx_ids()
                _reopen_drag = not _lic_s.reopen_license(_rid, text, _o2, _r2)
            if _rid and not _reopen_drag:
                # V2-300/V2-605 — WHICH card, decided once for both channels (`show_target.show_instance`).
                _rid, _show_ask, _show_chose = _probe._show_instance(
                    _rid, text, _probe._last_assistant_line(sess.window))
            action = ("guard:show-of-just-closed-widget" if _reopen_drag else
                      f"canvas:show:{_rid}" if _rid else
                      "clarify" if _show_ask else
                      f"panel:{_probe._wall_tab_for(_sys, text)}" if _probe._wall_tab_for(_sys, text) else "clarify")
    elif "close_widget" in names:
        _cw = next(t for t in tool_calls if t["name"] == "close_widget")
        _crid = _probe._close_target(str(_cw["args"].get("widget_id") or ""))
        _cmode = "minimize" if str(_cw["args"].get("mode") or "") == "minimize" else "close"
        action = f"canvas:{_cmode}:{_crid}" if _crid else "clarify"
    elif "fullscreen_widget" in names:
        # BUG real 2026-07-23 — espejo del provider: pone/quita pantalla completa de verdad. Resuelve el id por
        # nombre/alias con certeza (V2-082); sin match → pregunta (no fabrica).
        # V2-609 — the SAME decision as the voice channel, not a second copy of it
        # (`show_target.fullscreen_target`): with `widget_id` empty it falls through to the card the canvas
        # says IS at full screen, which is what makes «sal de pantalla completa» answerable at all.
        # V2-635 (espejo del provider): sin palabras de tamaño de pantalla la llamada es arrastre; con
        # orden de ENCOGER la ruta es el `minimize` del canvas, nunca el toggle al revés.
        from nucleo.flash import canvas_license as _lic_f
        _fw = next(t for t in tool_calls if t["name"] == "fullscreen_widget")
        _fsv = _lic_f.fullscreen_license(text)
        if not _fsv:
            action = "chat"
        else:
            _frid = _probe._fullscreen_target((_fw["args"].get("widget_id") or "").strip(), text)
            # V2-759 — the direction is an argument now, same as the voice: `off` never needs a name.
            if str(_fw["args"].get("mode") or "").strip().lower() == "off":
                action = f"canvas:unfullscreen:{_frid}"
            else:
                action = f"canvas:{_fsv}:{_frid}" if _frid else "clarify"
    elif "arrange_canvas" in names:
        # V2-588 — espejo del provider (cablear en AMBOS): ordenar el canvas es una acción global, sin id.
        action = "canvas:arrange"
    elif "widget_data" in names:
        # ESPEJO de la voz (`_handle_widget_data_tool`, impl PARALELA — cablear en AMBOS): la voz NO ejecuta a
        # ciegas el nombre de la tool — resuelve el widget, consulta `action_mode` y (diag sesiones-largas
        # 2026-07-15) mapea un VERBO DE CANVAS no declarado ("show"/"close") a la tag directa, o escala si la
        # acción no existe. Sin este espejo el probe reporta "widget_data ✗" donde la voz real hace show.
        action = "widget_data"
        try:
            from widgets import runtime as _rt

            from . import close_guards as _cg, frontend as _fe
            _wd = next(t for t in tool_calls if t["name"] == "widget_data")
            _wid = str(_wd["args"].get("widget_id") or "").strip().lower()
            _act = str(_wd["args"].get("action") or "").strip()
            if _wid and _rt.get(_wid) is None:   # id flojito → resuélvelo contra el catálogo, como la voz
                _wid = (_probe._identify_ctx(_rt, _wid) or _probe._identify_ctx(_rt, text) or _wid)
            # MIRROR of the voice guard «'abrir/mostrar' puro → show» (V2-544, rewritten in V2-545). It was NOT
            # mirrored here at first, and that absence made this channel give a FALSE GREEN on the very defect
            # it was being used to diagnose: the probe reported `widget_data open {name:'Francisco'}` while the
            # voice rail turned that same call into a bare [[show]] over an unmoved card. A test channel that
            # does not carry a guard reports the decision the product does not take.
            # The blocked branch stops here exactly like the voice rail's early return; a VIEW action falls
            # through as `widget_data` (the rail runs it, and also shows the card).
            _pl = _wd["args"].get("payload") if isinstance(_wd["args"].get("payload"), dict) else {}
            if _router.show_request_blocks_data_action(text, _wid, _act, _pl) and _rt.get(_wid) is not None:
                action = f"canvas:show:{_wid}"
            # V2-713 R3 — the short-close redirect, which had lived only in the voice rail. Shared as a
            # FUNCTION, never copied; the incident and the reason are in `close_guards.is_short_close_order`.
            elif (_cg.is_short_close_order(text) and _rt.get(_wid) is not None
                  # V2-770 — unless the verdict names THIS very action: «ya la puedes cerrar» → close_meeting
                  and __import__("nucleo.flash.direct_action", fromlist=["x"]).from_brief(_tbrief) != (_wid, _act)):
                action = f"canvas:close:{_wid}"
            elif _fe.action_mode(_wid, _act) is None:
                # ESPEJO de la voz (misma decisión compartida, `frontend.resolve_undeclared_action` — cablear
                # en AMBOS): verbo de canvas → tag; reparación Jev a una acción DECLARADA → el rail la ejecuta
                # (sigue siendo `widget_data`); sin veredicto → la voz escala.
                _kind, _val = _fe.resolve_undeclared_action(_wid, _act, text)
                if _kind == "canvas":
                    action = f"canvas:{_val}:{_wid}"
                elif _kind == "repair":
                    action = "widget_data"
                else:
                    action = "escalate"          # acción inventada sin verbo de canvas ni reparación → escala
            # V2-740 — ESPEJO de la voz, misma FUNCIÓN (nunca copiada). Sin brief que leer, la duda
            # se PREGUNTA: la segunda pregunta de V2-712, no una nueva.
            if action == "widget_data":
                _cd = _fe.card_decision(_wid, _act, payload=(_wd.get("args") or {}).get("payload"))
                _wd["args"]["widget_id"] = _wid = _cd["card"]
                if _cd["ask"]:
                    action = "clarify"
            # …y el mis-ruteo por pronombre suelto, que vivía COPIADO aquí y en el provider: el porqué y
            # las dos veces que hubo que arreglarlo por separado están en `frontend.absent_widget_misroute`.
            if action == "widget_data" and _fe.absent_widget_misroute(
                    _wid, _act, str(_wd["args"].get("item") or ""), named_widget=_probe._identify_ctx(_rt, text),
                    payload=_wd["args"].get("payload") if isinstance(_wd["args"].get("payload"), dict) else None):
                action = "escalate"
        except Exception:
            pass
    elif "delete_widget" in names:
        # espejo del provider (V2-045): 'cierra el widget de X' → delete_widget se redirige a CLOSE (cerrar≠borrar).
        action = "canvas:close" if _router.looks_like_close(text) else "delete_widget"
    elif "authenticate_web" in names:
        action = "authenticate_web"
    elif "connect_cluster" in names:
        # espejo del provider (V2-064) — dry, como authenticate_web: reporta la acción, no abre una conexión real
        # de red desde el canal de prueba.
        action = "connect_cluster"
    elif any(n in names for n in ("confirm_widget_delete", "login_done")):
        action = names[0]
    elif "set_style_directive" in names:
        action = "style"
        _sd = next(t for t in tool_calls if t["name"] == "set_style_directive")
        d = (_sd["args"].get("directive") or "").strip()
        # The whole path (identity mirror, V2-633 style flags, persisted user rule) lives in
        # `nucleo/flash/style_directive.py` — the module that owns this tool in BOTH channels.
        from nucleo.flash import style_directive as _styled
        _ident_action = await _styled.handle_probe(d, text, sess, ingest)
        if _ident_action:
            action = _ident_action
    elif tags:
        show_ids = [str(t.get("extra", {}).get("id") or "") for t in tags if t["action"] == "show"]
        action = (f"canvas:show:{show_ids[-1]}" if show_ids and show_ids[-1]
                  else "canvas:" + ",".join(t["action"] for t in tags))
    else:
        action = "chat"
        # V2-759 — espejo del provider: «sal de pantalla completa» answered with nothing called still leaves,
        # when a card IS covering the screen. Same decision (`show_target.fullscreen_exit_due`), reported here.
        try:
            _fx = _probe._fullscreen_exit_due(text, fired=False)
            if _fx:
                action = f"canvas:unfullscreen:{_fx}"
        except Exception:  # noqa: BLE001
            pass
    _out = locals()
    return {k: _out[k] for k in ('_cw', '_rt', '_show_chose', '_sp', 'action', 'images_req', 'music_req', 'reveal_out', 'video_req', ) if k in _out}
