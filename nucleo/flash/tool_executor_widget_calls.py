"""The widget half's big closures — `_tag_emit`, `_apply_widget_data`, `_handle_widget_data_tool` — lifted out of
`tool_executor_widget.build` (V2-778 F1, 2026-10-01).

The same code: what each closed over (the turn's state, the injected motor helpers, its sibling closures) is
passed as keyword arguments by the thin closure that stays in `build`, at CALL time — the same late binding a
closure has. Module-level names of `tool_executor_widget` are read through it (`_txw.<name>`).
"""
from __future__ import annotations

from nucleo.acts import card as _card   # refactor2710-05 T-02: the one licence
from nucleo.acts import canvas as _canvas_door, message as _message_door   # V2-800: his order over a row he has seen is the yes
from nucleo.flash import prior_line as _prior_line
from nucleo.flash import tool_executor_widget as _txw


def _tag_emit(action: str, extra: dict, *, _apply_widget_data, _brief, _is_meta_widget_question, _norm_nfkd, _on_tool_call, _request_delete_confirm, _show_guard_target, _show_target_instance, _shown_ids, _spawn, acted, aside, brain, canvas_h, cron_seen, deduped, emit, escalate_req, text) -> "bool | None":
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
        # V2-657 — sanctioned silence: a turn addressed to someone else in the room; resolved after the stream.
        aside["v"] = True
        return
    if action == "widget.data":
        # Fallback path (V2-026): the inline tag; the MAIN path is the `widget_data` tool — both converge.
        data = extra.get("data") or {}
        _apply_widget_data(str(extra.get("id") or ""), str(data.get("action") or ""),
                           data.get("payload") or {})
        return
    if action == "delete":
        # DELETE is the Flash's, but confirmed (V2-017): the tag opens the Yes/No overlay, never deletes.
        _request_delete_confirm(extra.get("id") or "", text)
        acted["widget"] = True
        return
    if action in ("create", "modify", "push"):
        # Hard boundary: create/modify/push data → SlowBrain (writes code); delete is handled above.
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
        # Own proactivity (V2-005): the loop's scheduler (not Hermes's cron), kept in memory.journal.
        if action == "cron.create":
            cron_seen["v"] = True          # V2-146: el backstop de abajo no duplica lo que ya se pidió
        try:
            from nucleo import scheduler as _sched
            d = extra.get("data") or {}
            if action == "cron.create":
                # refactor2710-06 T-06: the notice's slots decide; the agenda bounds the consequence, no words read
                from widgets.agenda import notice as _notice
                r, verdict = _notice.schedule(_sched.create, d)
                emit("cron", "⏰ tarea programada" if r.get("ok") else "⚠️ schedule no reconocido",
                     text=r.get("display") or r.get("error") or "", role="system",
                     extra={"ok": bool(r.get("ok")), "op": action, "verdict": verdict})
            else:
                _sched.cancel(extra.get("name") or d.get("name") or "")
                emit("cron", "🗑️ tarea cancelada", role="system", extra={"ok": True, "op": action})
        except Exception as e:  # noqa: BLE001
            _txw.logger.warning(f"nucleo cron {action} failed: {e}")
        return
    # show / close / move → canvas action. GUARD close without order (V2-635, like stop_worker's GUARD 2):
    # «Johnny eres tonto» ended in an unasked [[close]] (34386d8f). Exempt: `named` (full18 V7) and a card
    # his words call by name (full18 C6: «close the calendar and the messages»).
    if (action == "close" and not (extra or {}).get("named")
            and not _txw._direct_action._says_the_name(_txw._bnotes.operator_half(text), str((extra or {}).get("id") or ""))
            and _txw._close_cancel.inside_or_cancelled(_brief, _txw._bnotes.operator_half(text), extra, lambda c: _apply_widget_data(c["widget_id"], c["action"], c["payload"]))):
        # V2-770 — the order is an action INSIDE the card («ciérrala» over a detail card): not this tag.
        emit("brain", "🛡️ close ignorado — la orden es una acción DENTRO de la tarjeta",
             text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_inside_card"})
        deduped["v"] = True
        return False                  # V2-787: a refused close says so to its caller (`close_dispatch`)
    if action == "close":
        # the one close licence (the door's): his words, completed by the turn's brief; a model's call is forgiven a
        # grammar miss only by a sure `canvas=close` (T-jev-show-close) — `source` says which reader moved.
        _has_order, _order_src = _canvas_door.close_ordered(text, brief=_brief, called=True, handle=canvas_h)
        if not _has_order:
            emit("brain", "🛡️ close ignorado — el operador no ha pedido cerrar nada (context-bleed)",
                 text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_without_order"})
            deduped["v"] = True
            return False              # V2-787: a refused close says so to its caller (`close_dispatch`)
        if _order_src != "grammar":
            emit("brain", "🔓 close licenciado por Jev (la gramática no veía orden, dos lectores de acuerdo)",
                 text=(text or "")[:120], role="system", extra={"cat": "flash", "kind_diag": "close_jev_licensed"})
    if action == "show":
        contextual = _txw._show_target.named_or_guess(extra, lambda: _show_guard_target(text, brain._window, brain._last_action))  # V2-807 T-06
        if contextual:
            extra = {**(extra or {}), "id": contextual}
        # V2-776 — the CARD as the tool path resolves it (verification 2026-09-27, «Compare them visually»).
        _tid = str((extra or {}).get("id") or "").strip()
        if _tid and "::" not in _tid:
            try:
                _r_tag = _show_target_instance(_tid, _txw._bnotes.operator_half(text), brain._last_spoken or "")
                if not _r_tag.get("ask") and _r_tag.get("id"):
                    extra = {**(extra or {}), "id": _r_tag["id"]}
            except Exception:  # noqa: BLE001
                pass
    # GUARD anti-clutter (2026-07-12): [[show:navegador]] on a search opened an EMPTY browser beside the
    # task card; the search shows in ITS card (navegador::tN), so the bare one is ignored.
    if action == "show" and str(extra.get("id") or "").strip().lower() == "navegador":
        emit("brain", "🚫 [[show:navegador]] ignorado (la tarjeta de la tarea es la superficie)", role="system")
        return
    # A META question on a past action («¿por qué abriste proyectos?») is no show order (bug 2026-07-12).
    # V2-776: HIS words only (V2-678) — our `[SISTEMA]` notes dropped «Show me the monitors».
    if action == "show" and _is_meta_widget_question(_norm_nfkd(_txw._bnotes.operator_half(text))):
        emit("brain", "🚫 show ignorado (pregunta META sobre un widget, no una orden)",
             text=str(extra.get("id") or ""), role="system")
        return
    # DEDUP show by id within the turn: desktop.show is idempotent, but the bus is not flooded.
    if action == "show":
        _sid = str(extra.get("id") or "").strip().lower()
        if _sid and _sid in _shown_ids:
            return
        _shown_ids.add(_sid)
        extra["reason"] = "turn-order"       # V2-723: the guards above ARE the turn's license
        # V2-770 — a show of an ALREADY open card whose verdict names an action INSIDE it is not the act.
        if _txw._direct_action.order_is_inside(_brief, _sid):
            emit("brain", "🪟 show de una tarjeta ya abierta — la orden es una acción DENTRO",
                 text=_sid, role="system", extra={"cat": "flash", "kind_diag": "show_inside_card"})
            _cross_the_door(action, extra, text=text, brief=_brief, emit=emit)
            return
    # V2-039: the order comes from the FlashBrain; the event carries the phrase that caused it (2026-08-09).
    if not _cross_the_door(action, extra, text=text, brief=_brief, emit=emit, log_text=(text or "").strip()[:160]):
        deduped["v"] = True
        return False                  # the canvas door vetoed it: what was not done is not recorded as done
    acted["widget"] = True
    if action == "show" and extra.get("id"):
        # V2-776 — WHICH card: without it a tag show skipped the after-show repair (empty Markets, demo v7).
        acted["widget_id"] = acted.get("widget_id") or str(extra.get("id"))
    if action == "close":
        acted["closed"] = True                   # the short-close backstop does not close it again (post-stream)
        _txw._canvas_lic.note_operator_close(str(extra.get("id") or ""))   # V2-650b: reopen needs his words


def _cross_the_door(action: str, extra: dict, *, text: str, brief, emit, log_text: str = "") -> bool:
    """A canvas tag of the FlashBrain's turn, through the one canvas door (`nucleo.acts.canvas.apply`)."""
    from nucleo.acts import canvas_turn
    from nucleo.acts import canvas
    fields = {k: v for k, v in (extra or {}).items() if k not in ("id", "src")}
    src = str((extra or {}).get("src") or "") if str((extra or {}).get("src") or "").startswith("recall:") else "flash"
    return canvas.apply(action, str((extra or {}).get("id") or ""), src=src, text=log_text, emit=emit,
                        request=canvas_turn.request_of(brief, _txw._bnotes.operator_half(text)), **fields)


def _apply_widget_data(wid: str, action_name: str, payload: dict, ref: str='', *, _apply_widget_data, _brief, _frontend, _request_data_confirm, _spawn, _tag_emit, _turn_op_tasks, acted, brain, data_done, deduped, emit, escalate_req, text) -> None:
    """Run a data-op by its mode (V2-025): FAST now, CONFIRM held for his yes, undeclared → escalated. The
    point the tool and the tag converge on."""
    from widgets import actions as _wactions, text_home as _text_home
    wid, action_name, payload = _text_home.redirect(_txw._data_ops.one_open_instance((wid or "").strip().lower()), (action_name or "").strip(), payload, emit=emit, present=_txw._cvis.present)   # V2-773 one open instance · V2-807 T-09 a held message's text goes to its row
    action_name = (action_name or "").strip()
    # refactor2710-05 T-02 — the vetoes are ONE ladder read against the request (`nucleo.acts.card`).
    _req = {"brief": _brief, "text": text}
    _lic = _card.logged(_card.licence(_req, wid, action_name, payload, at=_card.GATE, last_reply=_prior_line.of(brain)), emit)
    if _lic.verdict == _card.CLOSE:
        _tag_emit("close", {"id": _lic.card})
        acted["widget"] = True
    if _lic.verdict != _card.RUN:
        return
    action_name, payload = _txw._row_lens.retarget(wid, action_name, _txw._said_day.payload(wid, action_name, payload, _txw._bnotes.operator_half(text)), _txw._bnotes.operator_half(text))   # the day he said; the row he named, on ITS day (pass 140)
    mode = _message_door.release(_frontend.action_mode_now(wid, action_name, payload), wid, action_name, payload, _brief)   # V2-712 · V2-800
    # TWO READERS DISAGREE ON AN ACT THAT LEAVES (demo pass 2026-09-28, full12 E3): verdict draft 1.00,
    # model `reply`, and a real email went out. V2-754 lets the model win since a wrong verdict costs a
    # view; at level ≥ sensitive that reverses: the verdict's action runs, or he is asked.
    if mode == _wactions.FAST and _frontend.at_least_sensitive(wid, action_name):
        _vdis = _txw._direct_action.completes(_brief, wid, model_action=action_name) or _txw._message.forward_instead(wid, action_name, payload, _txw._bnotes.operator_half(text))
        if _vdis:
            emit("brain", "🛑 acto que sale fuera y el veredicto dice otra cosa — corre el veredicto",
                 text=f"{wid}: modelo={action_name} · veredicto={_vdis}", role="system",
                 extra={"cat": "flash", "id": wid, "model": action_name, "verdict": _vdis})
            # The model's content travels to the verdict's action, filtered to its declared keys.
            _vkeys = set(_txw._direct_action._payload_spec(wid, _vdis))
            _vpay = _txw._message.forward_of(wid, action_name, payload, _txw._bnotes.operator_half(text)) or {k: v for k, v in (payload or {}).items() if k in _vkeys and str(v or "").strip()}
            # …plus the recipient his sentence names (full18 E3: `reply` has none; `forward` needs one).
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
        elif _card.logged(_card.licence(_req, wid, action_name, payload, at=_card.LEAVES), emit).verdict != _card.RUN:
            return
    if _txw._message.run_ordered(_brief, wid, action_name, payload, _txw._bnotes.operator_half(text), emit=emit, acted=acted, apply=_apply_widget_data): return  # noqa: E701 — an ordered act that leaves, the model only prepared (E3)

    def _log_dataop(m: str) -> None:
        """The ORDER behind a data-op (2026-08-09): action, card, mode and the sentence, so a wrong act ties to
        the words that made it (the store row is the effect, not the order)."""
        # V2-678 — HIS words, not the composed turn: with our notes glued on, the row named ours.
        emit("widget", f"data:{action_name}", text=_txw._bnotes.operator_half(text).strip()[:160],
             extra={"id": wid, "action": action_name, "mode": m, "src": "flash", "item": ref,
                    "payload": payload if isinstance(payload, dict) else {}})   # V2-653: the order's content

    mode = _txw._message.asked_if_leaving(mode, _brief, wid, action_name, emit=emit, payload=payload, said=_txw._bnotes.operator_half(text))
    if mode == _wactions.FAST:
        if _card.logged(_card.licence(_req, wid, action_name, payload, at=_card.FAST, last_dataop=brain._last_dataop),
                        emit).verdict != _card.RUN:
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

        # V2-778 F0-4 — an op that could not start is NOT done: the turn forgets it, so «Done.» never lies.
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
        # An action whose output only exists ON SCREEN (`present.mount`) brings its card via the one door
        # («Show me a chart of Apple stock» over an empty canvas, 2026-09-26); an open card is refused.
        try:
            from widgets import effects as _fx
            if _fx.carries(wid, action_name, _fx.PRESENT_MOUNT):
                _txw._cvis.present(wid, reason="producer-mount", action=action_name, src="flash", emit=emit, text=text, brief=_brief)
            # A LENS on a closed card brings the card (V2-773 final pass, C2: `agenda:show_day` changed a day
            # nobody could see). A write is not this: it may run behind the screen on purpose.
            elif (_fx.carries(wid, action_name, _fx.DATA_READ) and not _txw._cvis.is_open(wid)
                  and not _canvas_door.show_under_close(brief=_brief, wid=wid, words=False)):   # V2-773 E5: a close never brings the card
                _txw._cvis.present(wid, reason="turn-order", action=action_name, src="flash", emit=emit, text=text, brief=_brief)
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


def _handle_widget_data_tool(args: dict, *, _apply_widget_data, _brief, _frontend, _identify, _repeat_repair, _say, _tag_emit, acted, brain, clarify, deduped, emit, escalate_req, text) -> None:
    """Tool `widget_data` (V2-026, the main data-op path): the card and the row he names resolved to REAL ids,
    then `_apply_widget_data`; an ambiguous or missing row is asked, never guessed."""
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
    # refactor2710-05 T-02 — the vetoes over the model's call are one ladder (`nucleo.acts.card`).
    _req = {"brief": _brief, "text": text}
    _lic = _card.logged(_card.licence(_req, wid, action_name, payload, at=_card.CALL, emit=emit), emit)
    if _lic.verdict == _card.DROP:
        deduped["v"] = True
        return
    if _lic.verdict != _card.RUN:
        _tag_emit(_lic.verdict, {"id": _lic.card})
        return
    from nucleo.flash import router as _router
    if _router.is_pure_show_request(text) and runtime.get(wid) is not None:
        # V2-545 — a display-only action (`"view": true`) runs beside the card a pure show brings.
        emit("brain", "🪟 'abrir/mostrar' puro + acción de VISTA → la tarjeta Y la vista",
             text=f"{wid}:{action_name}", role="system",
             extra={"id": wid, "action": action_name, "payload": payload or {}})
        _tag_emit("show", {"id": wid})
    if _frontend.action_mode(wid, action_name) is None:   # acción no declarada → canvas, reparación Jev o escala
        # GUARD canvas vs data (diag 2026-07-15): `widget_data(clock, action="show")` maps DIRECT to the
        # canvas tag. Decided in `frontend.resolve_undeclared_action` (shared with the probe): canvas verb →
        # tag; else Jev picks among DECLARED actions; no verdict → escalate.
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
    if (_lic := _card.logged(_card.licence(_req, wid, action_name, payload, at=_card.DECLARED), emit)).verdict != _card.RUN:
        acted["widget"] = True
        _tag_emit("show", {"id": _lic.card})
        return
    res = refs.resolve(wid, action_name, ref, payload, order=_txw._bnotes.operator_half(text))
    # A bare-pronoun misroute on a widget neither shown nor named: `frontend.absent_widget_misroute`
    # (shared with the probe). An AMBIGUOUS ref on this card's rows is a «which one?», not a worker's job.
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
        # V2-754 — before «which one?»: a verdict naming ANOTHER action here means the doubt was the action.
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
    # V2-740 — WHOSE order, with two cards able to do it: `frontend.card_decision` (shared with the probe).
    _cd = _frontend.card_decision(wid, action_name, brief=_brief, ask_phrase=_say().ask_which_item,
                                  payload=payload, operator_text=_txw._bnotes.operator_half(text))
    if _cd["label"]:
        emit("brain", _cd["label"], role="system", text=_cd["text"], extra=_cd["extra"])
    if _cd["ask"]:
        acted["widget"] = True; clarify["msg"] = _cd["ask"]; return
    if _txw._vcard.takes_the_view(_brief, _cd["card"], action_name, operator_text=_txw._bnotes.operator_half(text), emit=emit, present=_txw._cvis.present, apply_widget_data=_apply_widget_data):
        acted["widget"] = True; return       # pass 114 I3: a sure verdict view on the card in front (`verdict_card`)
    # V2-754 — a VALID model call runs over a disagreeing verdict (a 0.99 would have RESTARTED the video); logged.
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
        # A sure QUESTION verdict over a model WRITE on the same card (full19 C2) — the answer runs. full52 V5:
        # a sure LENS (show_tab 0.97) over a state change (clear_search erased the results) — the lens runs.
        # `output.answer` is declared, never guessed.
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
            # full51 C2: when the verdict cannot complete alone, the WRITE still booked over the 15:00 meeting.
            # The write never runs; the verdict's call is asked after the turn (repair pass).
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
        # …a REPEATED view with a verdict needing a written payload (full20 E3): it runs, then one repair pass.
        if (_txw._data_ops.repeats_last_view(brain._last_dataop, _cd["card"], action_name, res.payload)   # full37 E2:
                or _txw._data_ops.a_view_where_the_verdict_acts(_cd["card"], action_name, _dis, _vw_words)):  # a lens
            _repeat_repair["v"] = (_cd["card"], action_name, _dis)
        emit("brain", "⚖️ el modelo y el veredicto discrepan — corre el modelo", role="system",
             text=f"{_cd['card']}: modelo={action_name} · veredicto={_dis}",
             extra={"cat": "flash", "id": _cd["card"], "model": action_name, "verdict": _dis})
    # V2-756 — what the model left EMPTY is filled from his words (`show_tab` without `tab`): it only adds
    # a missing key, by a declared alias or a spoken number.
    if (_fill := _txw._direct_action.fill_missing(_cd["card"], action_name, res.payload,
                                             _txw._bnotes.operator_half(text))):
        res.payload.update(_fill)
        emit("brain", "🧩 el modelo dejó la clave vacía — la rellenan sus palabras", role="system",
             text=f"{_cd['card']}:{action_name} {_fill}", extra={"cat": "flash", "id": _cd["card"],
             "action": action_name, "fill": _fill})
    _apply_widget_data(_cd["card"], action_name, res.payload, ref)
