"""The executor's `_on_tool_call`, lifted out of `tool_executor.build` (V2-778 F1, 2026-10-01).

`build` was a closure factory of 550 lines and this closure was 517 of them. It is the same code: what it closed
over (the turn's state, the injected motor helpers, its sibling closures) is passed as keyword arguments by the
thin closure that stays in `build`, at CALL time — the same late binding a closure has. Module-level names of
`tool_executor` are read through it (`_tx.<name>`), so patches still govern.
"""
from __future__ import annotations

from types import SimpleNamespace as _SimpleNamespace

from nucleo.acts import canvas as _canvas_door, media as _media_door
from nucleo.flash import prior_line as _prior_line
from nucleo.flash import resume_turn as _resume_turn   # V2-799
from nucleo.flash import tool_executor as _tx
from nucleo.turn import errands_of_a_turn as _eot
from nucleo.acts import tools as _acts   # refactor2710-05: the tool catalogue as a dict
from nucleo.turn import split_by_errand as _sbe   # a send beside a status question is said (2.644)


def a_search_is_his(query: str, operator_text: str, brief, overlap) -> bool:
    """False for a web search that shares NO word with his turn while the verdict reads the turn, surely, as an
    order on a card (demo pass 89, F2 — see the `web_search` branch). Anything else is his search."""
    from nucleo.flash import direct_action as _da_ws
    return not (overlap(query, operator_text) == 0 and _da_ws._action_sure(brief, floor=0.9))


def _on_tool_call(name: str, args: dict, *, _apply_widget_data, _brief, _closed_by_tool, _data_ops_hechas, _finish_web_auth, _handle_widget_data_tool, _norm_nfkd, _request_cluster_confirm, _request_delete_confirm, _request_restore_confirm, _resolve_confirm, _router, _say, _says_stop, _show_guard_target, _show_target_instance, _spawn, _start_web_auth, _tag_emit, _tool_fired, _word_overlap, acted, brain, clarify, confirm_state, deduped, emit, escalate_req, images_req, listing_req, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, self, style_fired, text, worker_acted) -> None:
    _turn = _SimpleNamespace(**locals())   # the turn's context, as every door in `acts.tools.CATALOG` reads it
    # No tool runs from a superseded fragment: he kept talking, so it was decided on half a sentence.
    if self._superseded():
        emit("brain", "🧩 tool ignorada — la frase seguía", text=name, role="system",
             extra={"cat": "flash", "fragment": (getattr(self, "_turn_text", "") or "")[:120]})
        return

    # Recorded AFTER the superseded gate: a tool that never ran must not weigh on the flow merge (V2-123).
    try:
        brain._turn_tools.add(name)
        brain._turn_calls.append({"name": name, "args": dict(args or {})})
    except Exception:
        pass

    # Feeds the next turn's `recent` layer: a conversation about widgets keeps them even unnamed.
    try:
        from nucleo.flash import tool_selection as _tsel2
        _fams = _tsel2.families_used([name])
        if _fams:
            prev = list(getattr(brain, "_recent_tool_families", None) or ())
            brain._recent_tool_families = list(dict.fromkeys(list(_fams) + prev))[:3]
    except Exception:
        pass
    arm = _acts.CATALOG.get(name)
    if arm is not None:
        return arm(args, _turn)


def _t_escalate_to_slowbrain(*, args, escalate_req, text):
    req = (args.get("request") or "").strip() or text
    # V2-227: the declared surface is kept PER request, only from a real model call; fallbacks let
    # `surfaces.resolve()` derive it.
    _sf = str(args.get("surface") or "").strip()
    if _sf:
        escalate_req["surface"][req] = _sf
    escalate_req.setdefault("done_when", {})[req] = args.get("done_when")   # V2-776 L1: the spec rides
    if escalate_req["v"] is None:
        escalate_req["v"] = req
    elif (args.get("request") or "").strip():
        # Another MODEL call this turn = another task, and it needs its own `request` (else it is the same
        # sentence). Capped: the target is a pool of real workers (`dispatch._max_parallel`, 3 by default).
        if req not in escalate_req["more"] and req != escalate_req["v"]:
            # three-tasks-at-once: what the pool cannot take is KEPT, so the turn can say it did not start it.
            _full = len(escalate_req["more"]) >= _eot.MAX_ERRANDS - 1
            (escalate_req.setdefault("dropped", []) if _full else escalate_req["more"]).append(req)


def _t_play_music(*, args, music_req, _brief=None, _apply_widget_data=None, acted=None, clarify=None, emit=None,
                  ask_phrase="", text="", esc=None):
    # V2-041: one music action per turn, resolved after the stream. V2-812 T-05 — an answer to OUR «which
    # one should I close?» carries that question's licence, not a player's («Las dos.» resumed the music).
    from nucleo.flash import close_answer as _close_answer
    if _close_answer.refuses(_brief, "musica", str(args.get("action") or "play").strip().lower()):
        if emit is not None:
            emit("brain", "🛡️ play_music refused: the turn answers our «which one should I close?»", role="system",
                 text=str(args.get("action") or "play"), extra={"cat": "flash", "kind_diag": "close_answer_not_play"})
        return
    # V2-794: a one-shot play over a SURE commission verdict is the errand, not a search query played as a title.
    if music_req["v"] is None and esc is not None and esc["v"] is None and _media_door.commissioned(_brief, args):
        _t_escalate_to_slowbrain(args={}, escalate_req=esc, text=text)
        esc["say"] = getattr(__import__("i18n.langs", fromlist=["x"]).current_language(), "done_just_started", "")
        if emit is not None:
            emit("brain", "⚖️ encargo, no reproducción: el veredicto lee el turno como trabajo de fondo", role="system",
                 text=f"play «{str(args.get('query') or '')[:80]}» → escalate", extra={"cat": "flash", "tool": "play_music"})
        return
    # A CONTROL with the video open too: whose player? Asked once, on the turn's first music call.
    if music_req["v"] is None and _apply_widget_data is not None and _media_door.control(
            {"text": text, "brief": _brief}, args, tool="play_music", apply_widget_data=_apply_widget_data, acted=acted,
            clarify=clarify, emit=emit, ask_phrase=ask_phrase).fired:
        return
    _mq = {"query": (args.get("query") or "").strip(),
           "action": (args.get("action") or "play").strip().lower()}
    if music_req["v"] is None:
        music_req["v"] = _mq
    else:
        # Collapse of several play_music in one turn (V2-047 F4: play AND queue for «luego pon X»). With music
        # already playing a `queue` wins over a `play`; otherwise the first stays. Rail state, not a word table.
        try:
            from nucleo import rails as _rails_m
            _playing = _rails_m.get("music.playing") is not None
        except Exception:
            _playing = False
        if _playing and _mq["action"] == "queue" and music_req["v"].get("action") != "queue":
            music_req["v"] = _mq
        # Real bug 2026-07-23: «pon música de Queen y súbele el volumen» → play + volume_up; the 2nd was dropped
        # while the voice promised it. A pure CONTROL call after a play/queue is kept as `followup`, run after.
        elif (not _mq["query"] and _mq["action"] in
              ("volume_up", "volume_down", "pause", "resume", "stop", "next", "previous")):
            music_req["followup"] = _mq


def _t_show_widget(*, args, _brief, _router, _say, _show_guard_target, _show_target_instance, _tag_emit, _tool_fired, acted, brain, clarify, deduped, emit, escalate_req, text):
    # show_widget as a first-class tool (more reliable than [[show]], e.g. games); same canvas path.
    if args.get("screen"):                # V2-792: «ponlo en el ordenador» — this turn's cards go to that screen
        from voice import screens as _scr
        _scr.send_turn_to(str(args.get("screen")))
    if "show_widget" not in _tool_fired:
        _tool_fired.add("show_widget")
        _wid = (args.get("widget_id") or "").strip()
        # GUARD (V2-567): a CLOSE order is not answered with a show («Cierra los contactos» → show(mensajeria)
        # made two mutations); the show is dropped, the close backstop closes. V2-750: grammar only PROPOSES;
        # `build_decision` composes the verdict with `build_or_use` (zh/ja/hi 6/9 → 9/9, node 2.68).
        if _canvas_door.show_under_close(text, brief=_brief, wid=_wid):
            # V2-807 T-08 — a show of an ALREADY open card on a close turn is the model KEEPING it; nothing
            # opens, and the keep is remembered so the same sentence's bulk close spares it.
            from nucleo.flash import bulk_close as _bulk, canvas_visibility as _cvis_keep
            if _wid and _cvis_keep.is_open(_wid):
                _bulk.note_kept(_wid)
                emit("brain", "🧷 show_widget on a close turn over an open card: kept, not opened",
                     text=_wid[:40], role="system", extra={"cat": "flash", "kept": _wid})
            else:
                emit("brain", "🚧 show_widget descartado: la orden dice CERRAR, no abrir",
                     text=(_wid or "?")[:40], role="system")
        # GUARD: CREATING a widget is not a show → escalate to the generator (deterministic backstop).
        elif (_bd := _tx._build_decision.decide(text, brief=_brief, proposed=_router.looks_like_create_widget(text)))[0]:
            if escalate_req["v"] is None:
                escalate_req["v"] = text
            emit("brain", "🏗️ show_widget→CREATE: se escala al generador (no es un show)", text=_bd[1][:60], role="system")
        else:
            from widgets import runtime
            # Resolved WITH CERTAINTY (V2-082) by the canvas door's own resolver (`canvas.resolve`, refactor2710-04).
            from nucleo.acts import canvas as _door
            _res, _open, _recent = _door.resolve(_wid, text, brain._window, brain._last_action, _show_guard_target)
            _rid = _res.get("match") or ""
            _rid = _rid if (_rid and runtime.get(_rid.split("::", 1)[0]) is not None) else ""
            _sys = _res.get("system")
            # V2-650b: a widget he JUST closed does not reopen over chatter (a re-emitted discarded show).
            if _rid and not _door.reopen_ordered(_rid, text, open_ids=_open, recent_ids=_recent, brief=_brief):
                emit("brain", "🛡️ show de un widget recién cerrado sin pedirlo — ignorado "
                     "(context-bleed)", text=_rid, role="system")
                deduped["v"] = True
            elif _rid:
                # V2-300 — the BASE with a live instance resolves to the INSTANCE (round 24: an empty base beside the
                # errand sheet). Same owner as close (`instances.resolve_close`); several open → ask.
                _r2 = _show_target_instance(_rid, text, brain._last_spoken or "")
                if _r2.get("ask"):
                    clarify["msg"] = _r2["ask"]
                    emit("brain", "🤔 show_widget con varias hojas → pregunto", text=_rid,
                         role="system")
                else:
                    _rid = _r2.get("id") or _rid
                    # V2-605: a FORCED choice (asked, he did not pick) must be named in the ack.
                    acted["show_chose"] = str(_r2.get("chose") or "")
                    _tag_emit("show", {"id": _rid})
                    # V2-209: WHICH widget opened, so the ack tells «here it is» from claiming an undelivered delivery.
                    acted["widget_id"] = _rid
                    emit("brain", "🪟 show_widget → canvas", text=_rid, role="system",
                         extra={"empty": _tx._surface_is_empty(_rid)})
            elif _tx._wall_tab_for(_sys, text):
                # It named the CHAT or the catalogue (V2-761: «ábreme las apps»): native wall tabs, not widgets.
                emit("panel", "open", extra={"tab": _tx._wall_tab_for(_sys, text), "src": "flash"})
                emit("brain", f"🗂️ show_widget→{_sys} (superficie de sistema)", role="system")
                acted["widget"] = True
            else:
                # V2-082: no match → ASK naturally; never fabricate a widget or open the «closest» one.
                clarify["msg"] = (_say().open_no_such_piece if _sys is None
                                  else _say().open_system_piece)
                emit("brain", "🤔 show_widget sin match → pregunto (no fabrico widget)",
                     text=str(_sys or "—"), role="system")


def _t_show_panel(*, args, _router, _tool_fired, acted, emit, operator_text, text):
    # V2-079: opens the native side PANEL (ChatWall) on a tab by voice: a `panel` event, not a widget.
    if "show_panel" not in _tool_fired:
        _tool_fired.add("show_panel")
        _tab = _router._canon_panel(args.get("panel"))
        if _tab == "apps":      # V2-761: «¿qué apps tengo CUSTOMIZADAS?» → the Custom sub-tab
            _tab = _tx._wall_tab_for("apps", _router.operator_words(operator_text, text))
        # 2026-08-10: it also CLOSES; before, «cierra el chat» ended in a false «vale, cerrado».
        _act = _router._canon_panel_action(args.get("action"))
        # The ONE door to connect a service: the ⚙ Conectores section opened on that connector alone.
        _cx = _router._canon_connector(args.get("connector")) if _tab == "conectores" and _act == "open" else ""
        emit("panel", _act, extra={"tab": _tab, "src": "flash", **({"connector": _cx} if _cx else {})})
        emit("brain", f"🗂️ show_panel → panel nativo ({_act})", text=_tab, role="system")
        acted["widget"] = True     # cuenta como acción de UI (ack "nunca mudo" + no escala espurio)


def _t_manage_widget_alias(*, args, _say, _tool_fired, acted, clarify, emit, text):
    # V2-082: add/remove a widget ALIAS by voice — a surgical manifest write with a collision guard; this
    # tool loop is SYNCHRONOUS, so the file write goes inline.
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


def _t_arrange_canvas(*, _tool_fired, acted, emit):
    # V2-588: «ordena los widgets» had the whole path built and no tool, so the model said no such button
    # existed. A whole-canvas action: the same emit as the REST endpoint.
    if "arrange_canvas" not in _tool_fired:
        _tool_fired.add("arrange_canvas")
        from nucleo.acts import canvas
        canvas.apply("arrange", src="flash", emit=emit)
        emit("brain", "▦ arrange_canvas → canvas", role="system")
        acted["widget"] = True


def _t_reply_message(*, args, _apply_widget_data, _say, _tool_fired, clarify):
    # V2-051: reply via `mensajeria`'s `reply` data-op (confirm:true → the gate asks before SENDING).
    if "reply_message" not in _tool_fired:
        _tool_fired.add("reply_message")
        try:
            _n = int(args.get("n"))
        except (TypeError, ValueError):
            _n = None
        _rtext = (args.get("text") or "").strip()
        if _n is not None and _rtext:
            _apply_widget_data("mensajeria", "reply", {"n": _n, "text": _rtext})
        elif _rtext:
            # No number: the card resolves it to the conversation that is OPEN, or refuses with what is missing.
            _apply_widget_data("mensajeria", "reply", {"text": _rtext})
        else:
            clarify["msg"] = _say().reply_which_message


def _t_set_style_directive(*, args, _spawn, brain, emit, style_fired, text):
    # V2-046 A1 + V2-633 — the path lives in `nucleo/flash/style_directive.py`; True = identity took it.
    directive = (args.get("directive") or "").strip()
    if directive:
        style_fired["v"] = True
        from nucleo.flash import style_directive as _styled
        if _styled.handle(directive, text, brain, emit, _spawn, name=(args.get("name") or "").strip()): return


def _t_authenticate_web(*, args, _start_web_auth, emit, escalate_req, text):
    # Deterministic guard (V2-022): login PLUS a TASK («entra en mi Gmail y BÓRRAME…») escalates to the
    # browser; authenticate_web is ONLY a pure login. V2-176: the DECISION lives in `web_auth.decide`
    # (shared with the text channel); the EFFECTS stay per channel.
    from nucleo.flash import web_auth as _wa_v
    _site = (args.get("site") or "").strip()
    _kind_v, _site_resolved = _wa_v.decide(_site, text)
    if _kind_v in (_wa_v.KIND_MUSIC, _wa_v.KIND_MESSAGING):
        # INVARIANT (2026-07-16, V2-045): Spotify, WhatsApp, Telegram and email are never logged into via the
        # browser; since 2026-10-04 they connect in ONE place, the ⚙ Conectores section on that connector.
        from nucleo.flash.connector_canon import canon_connector as _cc
        _cx = _cc(_site) or _cc(text) or ("spotify" if _kind_v == _wa_v.KIND_MUSIC else "")
        emit("panel", "open", extra={"tab": "conectores", "src": "flash", **({"connector": _cx} if _cx else {})})
        emit("brain", f"🔌 connect → Conectores section ({_cx or 'list'}), not the browser", text=_site or text[:60],
             role="system")
    elif _kind_v == _wa_v.KIND_TASK:
        if escalate_req["v"] is None:
            escalate_req["v"] = text
        emit("brain", "🔐→🧭 login+tarea → escalado (no solo auth)", role="system")
    else:
        _start_web_auth(_site_resolved)


def _t_connect_cluster(*, args, _request_cluster_confirm):
    # V2-064: the pipe existed; this tool exposes it behind a deterministic confirm
    # (`_request_cluster_confirm`): the description alone did not stop pasted text with an id/token.
    _ccid = (args.get("cluster_id") or "").strip()
    _ctok = (args.get("token") or "").strip()
    # V2-086 — two cluster classes: a PUBLIC one (MeshKore Commons, tokenless) needs only cluster_id;
    # before, it was dropped silently. ⚠️ The name is `_cluster_vis`, NOT `_cvis` (V2-758): assigning a
    # module alias's name makes it LOCAL to the whole function, so every earlier `_cvis.present(...)`
    # raised UnboundLocalError — 2026-09-23: nine turns reported «Cerebro rápido caído», DeepSeek fine.
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


def _t_cluster_send(*, args, _spawn, emit):
    # V2-086: a first-class tool, by the SAME path as [[cluster.send]] → `bridge.dispatch_tag` (outbound
    # secret guard + journal). No confirm: a normal message he just asked for.
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
                _spawn(_mk3.dispatch_tag("cluster.send", {"name": _scl, "data": _data}), "cluster-send")
                emit("brain", "🛰 mensaje enviado al cluster", role="system",
                     text=f"{_scl}{('→' + _sto) if _sto else ''}")
            except Exception as _e:  # noqa: BLE001
                _tx.logger.warning(f"cluster_send falló: {_e}")
        else:
            emit("brain", "🛰 cluster_send sin cluster resuelto (¿varios o ninguno?)", role="system")


def _t_set_cluster_objective(*, args, _say, _spawn, clarify, emit):
    # T-02 (audit 2026-07-26): nothing wrote capsule.objective, so `perms.gate_dev_by_objective` (V2-076)
    # kept every 'code' cluster's dev-worker inert. No confirm: declarative, reversible with an empty one.
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


def _t_send_to_worker(*, args, emit, worker_acted, fired=None):
    # V2-038: refine a live worker → INJECT (no relaunch), fire-and-forget on the server loop (§v3·O).
    which = (args.get("which") or "").strip()
    msg = (args.get("message") or "").strip()
    if msg:
        try:
            from nucleo import dispatch as _d
            _d.inject_soon(which or "todo", msg)
            worker_acted["v"] = "inject"
            fired is not None and fired.add("send_to_worker")    # the close backstop reads it (three-tasks)
            emit("brain", "↪️ inyección a worker", text=f"{which}: {msg}"[:120], role="system")
            # Observability (V2-090): a correction to a LIVE task joins that task's flow — only when exactly
            # one session matches; with several, merging would be a guess.
            try:
                # ⚠️ ruff F821 (2026-09-05): `_trace` was never in scope, so this merge died as a NameError
                # inside this except every time — the fail-open class, live in the hot path.
                from voice import trace as _trace
                _targets = _d.resolve_sessions(which or "todo")
                if len(_targets) == 1:
                    _target_trace = _d.trace_of(_targets[0])
                    if _target_trace:
                        _trace.adopt(_target_trace)
            except Exception:
                pass
            _sbe.note_sent(which)   # the status line names the errand this reached (2.644)
        except Exception as e:  # noqa: BLE001
            _tx.logger.warning(f"send_to_worker falló: {e}")


def _t_stop_worker(*, args, _norm_nfkd, _say, _says_stop, clarify, emit, text, worker_acted, brief=None,
                   prior: str = ""):
    which = (args.get("which") or "").strip()
    # ── GUARD 1: never stop the worker you just answered (2026-08-14, session b70a45d0) ──
    # answer_worker («Sí, autorizado: borra TODA la agenda») + stop_worker killed the answered task and
    # «Vale, se lo digo» was false. Answering and killing in one turn: the (non-destructive) answer wins.
    if worker_acted["v"] == "answer":
        emit("brain", "🛡️ stop_worker ignorado — este turno ACABA de responder al worker", text=f"{which or 'todo'}",
             role="system", extra={"cat": "flash", "kind_diag": "stop_after_answer"})
        return
    # ── GUARD 2: stopping needs HIS order in THIS turn, read asymmetrically (`stop.model_stop`, refactor2710-07).
    from nucleo.request import stop as _stop_decision
    _may = _stop_decision.model_stop(brief, grammar=bool(_says_stop(text)
                                                         or _prior_line.answers_our_question(brief, prior)))
    if _may == "veto":
        emit("brain", "🛡️ stop_worker ignorado — el operador no ha pedido parar nada (context-bleed)",
             text=(text or "")[:120], role="system",
             extra={"cat": "flash", "kind_diag": "stop_without_order", "which": which or "todo"})
        return
    if _may != "run":     # refactor2710-07: an unsure verdict against the model's stop is asked, never refused silently
        clarify["msg"], worker_acted["v"] = _say().stop_doubt, "stop"
        return emit("brain", "❓ stop_worker en duda — se pregunta", text=(text or "")[:120], role="system",
                    extra={"cat": "flash", "kind_diag": "stop_asked", "which": which or "todo"})
    try:
        from nucleo import dispatch as _d
        # GUARD stop-ALL (session 23:15 2026-07-16, T49): «si solo es una tarea» → stop_worker(todo) killed BOTH live
        # sessions. «todo» over distinct goals needs the brief's SURE `stop_all` (`stop.all_ordered`); else the matching
        # session (`resolve_sessions`), and with no clear match nothing is killed (ask).
        _w = which or "todo"
        if _w == "todo":
            _live = _d.pending_summaries()
            _goals = {(s.get("request") or "")[:60] for s in _live}
            _says_all = _stop_decision.all_ordered(brief)
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
        worker_acted["stopped"] = _stop_decision.goals_of(_w)   # V2-820: a replace carries what it stopped
        tids = _d.cancel_soon(_w)
        if _w == "todo":     # «para todo y quédate tranquilo» → además LIMPIA las marcas de trabajo
            from nucleo import reset as _reset_mod
            _reset_mod.abandon_work_soon(source="voz")     # mismo núcleo que Reset; ver su docstring
        worker_acted["v"] = "stop"
        emit("brain", "🛑 stop worker", text=f"{_w} → {tids}"[:120], role="system")
    except Exception as e:  # noqa: BLE001
        _tx.logger.warning(f"stop_worker falló: {e}")


def _t_answer_worker(*, args, emit, worker_acted, fired=None):
    ans = (args.get("answer") or "").strip()
    if ans:
        try:
            from nucleo.cli import worker_api as _wapi
            if _wapi.answer_active_soon(ans):
                worker_acted["v"] = "answer"
                fired is not None and fired.add("answer_worker")    # the close backstop reads it (three-tasks)
                emit("brain", "💬 respuesta a worker", text=ans[:120], role="system")
        except Exception as e:  # noqa: BLE001
            _tx.logger.warning(f"answer_worker falló: {e}")


def _t_confirm(args: dict, said: str, _resolve_confirm, clarify, emit) -> bool:
    """The model's answer to a pending confirmation — except a YES to an act that leaves the machine that his own
    words do not give (`widgets.confirm.backs_a_yes`, demo pass 133 E4): nothing is resolved, and the turn asks the
    question again instead of saying it sent."""
    from widgets import confirm as _wconfirm
    if bool(args.get("confirmed")) and not _wconfirm.backs_a_yes(said):
        items = sorted(_wconfirm.pending().values(), key=lambda p: p.get("ts", 0))
        clarify["msg"] = str((items[-1] if items else {}).get("question") or "")
        emit("brain", "🛑 el modelo dio el sí a un acto que sale fuera y sus palabras no", role="system",
             text=str(said or "")[:120], extra={"cat": "flash"})
        return False
    return _resolve_confirm(bool(args.get("confirmed")))
