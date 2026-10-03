"""The post-stream chain holds the model to its WORDS: a pure show over a spurious tool, a ghost worker, the third rung, the escalate gate's evidence, promised reminders and dated notes, an order on a card that was never called (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/post_stream.py::run` (951 lines) with no behaviour change. Every name the block read
from `post_stream` is read through it (`_pst.<name>`), so a patch on `post_stream` still governs it. The function
takes the chain's locals it read as keyword arguments and returns the ones the rest of `run` reads, only when
bound.
"""
from __future__ import annotations

from nucleo.flash import post_stream as _pst


async def hold_the_model_to_its_words(*, _apply_widget_data, _brief, _data_ops_hechas, _has_workers, _prompt_mod, _repeat_repair, _router, _show_guard_target, _tag_emit, _tool_fired, _turn_op_tasks, acted, brain, canvas_h, clarify, cron_seen, data_done, emit, escalate_req, images_req, listing_req, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, send, speak, spec, speech, spoken, text, worker_acted) -> dict:
    spoken_text = "".join(spoken).strip()

    # GUARD DETERMINISTA de SHOW puro (V2-023, ampliado 2026-07-14). "muéstrame el de mensajería" / "abre la
    # agenda" / "muéstrame el widget de fútbol": si el modelo rápido ESCALÓ (→ widget basura) o disparó
    # web_search (las palabras-tema «fútbol/resultados» ceban la búsqueda, hallazgo del test post-P1/P2) una
    # petición que en realidad es MOSTRAR un widget que YA EXISTE, lo resolvemos aquí: `_show_guard_target`
    # exige verbo de show + NO-crear + que `runtime.identify` (fuzzy por keywords, GENÉRICO) case un widget
    # real → override determinista de la tool espuria. Solo si no hubo ya una data-op efectiva.
    # Solo si el modelo emitió una tool ESPURIA (escalate/search) para lo que en realidad es MOSTRAR un widget
    # existente. (Se probó ampliarlo a CHARLA en el mar de testing 2026-07-19, pero los verbos 'pon/ver' del
    # guard colisionan con 'pon música'/'va a poner el tiempo'/'a ver si…' → hijack de web/deep/música. La cola
    # de show-promesa-en-charla la captura el Susurro, no un guard sobre-amplio.)
    if (escalate_req["v"] is not None or search_req["v"] is not None) and not acted["widget"]:
        _guard_wid = _show_guard_target(text, brain._window, brain._last_action)
        _guard_src = "grammar" if _guard_wid else "none"
        if not _guard_wid:
            # Jev show license (T-jev-show-close, shared reader `show_target.show_from_verb`):
            # a confident "show" + a real identify hit rescues a grammar miss (e.g. English
            # "show me X", whose verb the Spanish-stem grammar never sees). Anything else —
            # vetoed, unsure, unresolvable, Jev off — keeps the path below untouched.
            try:
                _guard_wid, _guard_src = _pst._show_target.show_from_verb(text, canvas_h)
            except Exception:
                _guard_wid, _guard_src = None, "none"
        if _guard_wid:
            _was_search = search_req["v"] is not None
            escalate_req["v"] = None
            search_req["v"] = None
            acted["widget"] = True
            # V2-773 — a show the door SUPPRESSES (already open) is not the act: the turn's order was inside
            # the card («Open the most important one»), and `card_commission.after_show` asks for the call.
            acted["show_suppressed"] = not _pst._cvis.present(_guard_wid, reason="turn-order", src="flash", emit=emit)
            acted["widget_id"] = acted.get("widget_id") or _guard_wid
            emit("brain", "🪟 show por guard determinista (tool espuria evitada)",
                 text=f"{_guard_wid} ({'search' if _was_search else 'escalate'}→show"
                      f"{', licencia Jev' if _guard_src == 'jev' else ''})", role="system")
            if not spoken_text:
                try:
                    # V2-209 (impl PARALELA — cablear en AMBOS): abrir una tarjeta no es entregar un
                    # resultado. La decisión vive en `router_guards` para que los dos canales no puedan
                    # divergir.
                    from i18n import langs as _langs   # same object as the voice.engine.core shim
                    from nucleo.flash import router_guards as _rg_show
                    spoken_text = _rg_show.show_ack(_langs.current_language(), _guard_wid)
                except Exception:
                    spoken_text = "Aquí lo tienes."
                send(speech.sanitize(spoken_text, drop_metadata=False))

    # Demo pass 69, B1 — his words NAME the (empty) picture viewer: the turn is the picture search, whatever tool
    # the model reached for (a listing search this time; a worker, a promise and a commission before).
    from nucleo.flash import card_commission as _cardc_pic
    _pic_named = (None if images_req["v"] is not None
                  or any(str(_w).split("::")[0] == "imagenes" for _w, _a in (data_done.get("ops") or []))
                  else _cardc_pic.picture_named_by(operator_text))
    if _pic_named:
        images_req["v"], listing_req["v"] = _pic_named, None
        escalate_req["v"], escalate_req["more"] = None, []
        emit("brain", "🎯 sus palabras nombran el visor de imágenes — la búsqueda de fotos, nada más",
             text=_pic_named["query"][:120], role="system", extra={"cat": "flash", "tool": "show_images"})

    # GHOST-WORKER guard, plus the «Sí» that has no directive either — in `escalation_guard`.
    _pst._eguard.drop_if_fragment(escalate_req, operator_text=operator_text, brief=_brief,
                             last_reply=brain._last_reply or "", emit=emit)

    # V2-741 · THE THIRD RUNG — a declared action BEFORE anything may cost minutes: a catalogue of
    # videos became a worker that took 195 s to reach the `youtube:search` the brief had named.
    if escalate_req["v"] is not None and not acted["widget"] and not data_done["v"]:
        if _pst._direct_action.take_rung(escalate_req, brief=_brief, operator_text=operator_text,
                                    emit=emit, present=_pst._cvis.present,
                                    apply_widget_data=_apply_widget_data):
            acted["widget"] = True
        # V2-770 — the rung fills ONE key; a data-op of two («a partir de noviembre ya no hay piano» →
        # cancel_meeting {title, from}) gets one pass with the named card's fields before a worker.
        elif (_esc_owner := _pst._direct_action.from_brief(_brief)[0]):
            from nucleo import danger as _danger_esc
            from nucleo.flash import act_repair as _act_repair_esc
            _ar = (None if _danger_esc.is_dangerous(operator_text) else   # full44 E3: + the verdict's call
                   await _act_repair_esc.call_for_promise_or_order(operator_text, str(escalate_req.get("v") or ""),
                                                                   _esc_owner, _pst._direct_action.from_brief(_brief)[1],
                                                                   spec=spec, window=list(brain._window)))
            if _ar:
                _pst._cvis.present(_ar["widget_id"], reason="turn-order", src="flash", emit=emit)
                _apply_widget_data(_ar["widget_id"], _ar["action"], _ar["payload"])
                escalate_req["v"], escalate_req["more"] = None, []
                acted["widget"] = True
                emit("brain", "🎯 acción declarada en vez de un worker (segunda pasada con sus campos)",
                     text=f"{_ar['widget_id']}:{_ar['action']}", role="system",
                     extra={"cat": "flash", "widget": _ar["widget_id"], "action": _ar["action"]})
        # V2-773 — the card is CLOSED and the verdict names it from the catalogue: a commission whose answer
        # lives in one of our cards is a READ (or a declared call), never a five-minute worker. The decision
        # and its two outcomes live in `card_commission`; None keeps the worker.
        else:
            from nucleo.flash import card_commission as _cardc
            if await _cardc.before_worker(escalate_req, read_req, brief=_brief, operator_text=operator_text,
                                          spec=spec, emit=emit, present=_pst._cvis.present,
                                          apply_widget_data=_apply_widget_data,
                                          window=list(brain._window), images_req=images_req) == "call":
                acted["widget"] = True

    # JEV ESCALATE GATE (T-jev-escalate): a commission that SURVIVED the grammar guards gets a
    # cheap second opinion before it spends money. A confident `handle_inline` annuls it in the
    # same shape as the ghost-worker guard above; anything else keeps `v`. Only ever CLEARS —
    # every backstop below already handles `None`, so their precedence is intact.
    #
    # V2-726 A3 — AND IT NEEDS EVIDENCE NOW. We are past the model and usually past the start of
    # speech: the reply the operator just heard normally PROMISED this errand. `handle_inline`
    # says «no worker needed», not «already done», and clearing `v` on it alone produced a
    # promise with nothing behind it. The rule and the three promise detectors it reuses live in
    # `escalation_guard.annulment_verdict`; every commission ends with a DISPOSITION, emitted,
    # because one that simply disappears is the failure this whole gate was meant to prevent.
    if escalate_req["v"] is not None:
        _pst._eguard.settle_commission(
            escalate_req, brief=_brief, operator_text=operator_text, reply="".join(spoken),
            acted=bool(acted["widget"] or data_done["v"] or listing_req["v"]
                       or music_req["v"] or search_req["v"]),
            anything_running=bool(_has_workers), emit=emit)

    # BACKSTOP PROMESA-SIN-ACCIÓN UNIFICADO 2026-07-19 (mar de testing): ante fraseo CORTÉS/subjuntivo
    # («¿podrías…?», «deberías…», «sería genial que hicieras…», «me haría falta…») el modelo CHARLA una promesa
    # («me pongo con ello», «te lo abro», «voy a poner…») SIN llamar a la tool → causa nº1 de "dice que lo hace y
    # no lo hace". Gated por la promesa en la RESPUESTA (zaelar se comprometió) → re-derivamos la intención con
    # los clasificadores DETERMINISTAS. GENERALIZA sobre todas las conjugaciones (no se parchea verbo a verbo).
    # V2-556: elegir la pasada rápida de anuncios YA es actuar (ver `listing_turn.voice_turn`).
    # The two guards themselves, and WHY they read the operator's words, live in `escalation_guard`.
    if (escalate_req["v"] is None and listing_req["v"] is None and not acted["widget"]
            and not data_done["v"] and not music_req["v"]):
        _guard_text = _pst._eguard.escalation_text(operator_text, text)
        if _guard_text:
            search_req["v"] = None
            escalate_req["v"] = _guard_text
            emit("brain", "🧭 escalada por guard (marketplace→navegar / modificar-widget→generador)",
                 text=_guard_text[:80], role="system")

    # BACKSTOP DE AVISO PROMETIDO (V2-146, impl PARALELA con el probe — cablear en AMBOS): el modelo prometió
    # el recordatorio en PROSA y no emitió la tag, así que `scheduled_jobs.created` salió vacío mientras el
    # turno decía «te avisaré el miércoles». El ejecutor de tags funciona y el prompt lo pide con todas las
    # letras: faltaba hacerlo cuando el modelo no lo hace. Solo con un momento RESOLUBLE — la función
    # devuelve "" ante cualquier expresión que no sea inequívoca, porque un aviso mal fechado no se nota
    # hasta el día que no suena.
    if spoken_text and not cron_seen["v"]:
        try:
            # V2-153: misma función que el probe. Ver su docstring — el duplicado nació justamente de que
            # cada canal decidía por su cuenta.
            _cron = _router.dated_reminder_backstop(spoken_text, operator_text, window=brain._window)
            if _cron:
                from nucleo import scheduler as _sched_bk
                _r = _sched_bk.create(_cron["prompt"], _cron["schedule"], name=_cron["name"])
                emit("cron", "⏰ aviso programado por backstop (lo prometió sin emitir la tag)"
                     if _r.get("ok") else "⚠️ schedule no reconocido",
                     text=_r.get("display") or _r.get("error") or "", role="system",
                     extra={"ok": bool(_r.get("ok")), "op": "cron.create", "backstop": True})
        except Exception:
            pass

    # BACKSTOP DEL APUNTE CON FECHA (V2-159, espejo del probe — cablear en AMBOS). La OTRA mitad del mismo
    # encargo: el caso pide las dos cosas —el compromiso registrado y el aviso— y la corrida salió con el
    # cron puesto y ninguna cita. Solo si el turno no hizo ya una data-op.
    if spoken_text and not data_done["v"]:
        try:
            _note = _router.dated_note_backstop(spoken_text, operator_text, window=brain._window)
            if _note:
                import widgets as _w_note
                await _w_note.dispatch_tag("widget.data", {"id": "agenda", "data": {
                    "action": "add_meeting", "payload": _note}})
                emit("widget", "🗓️ cita apuntada por backstop (lo prometió sin emitir la data-op)",
                     text=f"{_note['date']} · {_note['title']}", role="system",
                     extra={"id": "agenda", "act": "add_meeting", "backstop": True})
        except Exception:
            pass

    # EVERY tool the model can answer with counts — demo pass 2026-09-28, I1: «show me a red ferari f40» called
    # show_images, the pictures came up, and the verdict «completed» the «empty» turn with a YouTube search too.
    _completed = ""                     # the action the verdict's completion ran, if it ran one (pass 90, S2)
    _no_tool = (not acted["widget"] and not data_done["v"] and not music_req["v"] and not worker_acted["v"]
                and escalate_req["v"] is None and search_req["v"] is None
                and all(r["v"] is None for r in (images_req, listing_req, recall_req, read_req, reopen_req,
                                                 reveal_req)))
    _op_text = _router.operator_words(operator_text, text)   # a note is CONTEXT, never the errand
    # V2-754 — no tool, an ORDER on an open card (`show_tab` 0.88 over nothing): the verdict completes the turn.
    if _no_tool and not clarify["msg"] and (
            _pst._direct_action.complete_canvas(_brief, tag_emit=_tag_emit, emit=emit, operator_text=_op_text)
            or (_completed := _pst._direct_action.complete(_brief, operator_text=_op_text, emit=emit, present=_pst._cvis.present,
                                       apply_widget_data=_apply_widget_data, model_words=spoken_text))):
        acted["widget"] = True
        _no_tool = False
        if _completed:
            from nucleo.flash import act_repair as _act_repair_c
            _c_tail = _act_repair_c.after_the_completion(spoken_text, _pst._direct_action.from_brief(_brief)[0],
                                                         _completed)
            if _c_tail:
                send(speech.sanitize(_c_tail, drop_metadata=False))
                spoken_text = spoken_text + _c_tail
    # …and a data-op INSIDE a card he also told to close by its name («stop the video and close youtube»): the
    # card closes after the op (`closes_the_named_card`).
    if data_done["v"] and not clarify["msg"] and "close_widget" not in _tool_fired:
        _cn = _pst._direct_action.closes_the_named_card(_brief, _op_text, data_done.get("ops"))
        if _cn:
            _tag_emit("close", {"id": _cn, "named": True})
            emit("brain", "🎯 el veredicto completa al modelo — close", text=_cn, role="system",
                 extra={"cat": "flash", "widget": _cn, "action": "close", "said": (_op_text or "")[:120]})
    # V2-764 — it PROMISED to act on a card the verdict names and called nothing: one pass for the call
    # (`act_repair`), before any backstop decides it was a web errand and spends a worker on it.
    # full44 M1: «Checking… Apple's up about 1.4% today, roughly $258 — pulling the chart up now.», nothing called,
    # the verdict unsure — and `promises_action` is a table of SPANISH promise forms, so an English promise never
    # opened this door. Whether the words promised or claimed an act is the repair pass's own question (its
    # prompt); the door only needs a card the turn names (`named_or_catalogue` below, "" = no pass).
    _named_by_verdict = ""     # the card the verdict (brief or late catalogue) names for this order, if any
    if (_no_tool and spoken_text and not clarify["msg"]
            and not _router.asks_for_missing_detail(spoken_text)):
        from nucleo.flash import act_repair as _act_repair, build_decision as _bd_ar
        from nucleo.flash import card_commission as _cardc_ar
        _ar_wid = _cardc_ar.named_or_catalogue(_brief, _op_text)   # V2-773: a closed card while others are open
        _named_by_verdict = _ar_wid
        if _ar_wid and _pst._direct_action.sure_canvas(_brief) == "close":
            # the promise was to CLOSE it: the card's own close, never a data action (S4 emptied the sheet)
            _tag_emit("close", {"id": _pst._show_target.close_target(_ar_wid)})
            acted["widget"] = True
            _no_tool = False
            emit("brain", "🔁 prometió cerrar sin tool — cierra la tarjeta", text=_ar_wid, role="system",
                 extra={"cat": "flash", "widget": _ar_wid, "action": "close"})
            _ar_wid = ""
        _ar_vo, _ar_va = _pst._direct_action.from_brief(_brief)    # full41 E3: a refusal of the verdict's declared act
        _ar = (await _act_repair.call_for_promise_or_order(_op_text, spoken_text, _ar_wid, _ar_va if _ar_vo == _ar_wid
                                                           else "", spec=spec, window=list(brain._window)) if _ar_wid else None)
        # Demo pass 67, B1: a promise to find a wallpaper, the catalogue naming the EMPTY picture viewer, and no
        # call from the pass — the promise backstop then spent a worker. That order is the picture search.
        _pic = None if (_ar or not _ar_wid) else _cardc_ar.picture_search_for(_ar_wid, _op_text)
        if _pic and images_req["v"] is None:
            images_req["v"] = _pic
            acted["widget"] = True
            _no_tool = False
            emit("brain", "🎯 la herramienta del turno en vez de un worker (promesa sobre el visor vacío)",
                 text=f"{_ar_wid} ← show_images «{_pic['query'][:100]}»", role="system",
                 extra={"cat": "flash", "widget": _ar_wid, "tool": "show_images"})
        if _ar:
            _pst._cvis.present(_ar["widget_id"], reason="turn-order", src="flash", emit=emit)
            _apply_widget_data(_ar["widget_id"], _ar["action"], _ar["payload"])
            acted["widget"] = True
            _no_tool = False
            emit("brain", "🔁 prometió actuar sin tool — la llamada, en una segunda pasada",
                 text=f"{_ar['widget_id']}:{_ar['action']}", role="system",
                 extra={"cat": "flash", "widget": _ar["widget_id"], "action": _ar["action"]})
            # the words did not promise it (they may have REFUSED it): what was done is said after them
            _ar_tail = _act_repair.after_the_repair(spoken_text, _router.promises_action(spoken_text),
                                                    _ar["widget_id"], _ar["action"])
            if _ar_tail:
                send(speech.sanitize(_ar_tail, drop_metadata=False))
                spoken_text = spoken_text + _ar_tail
    # An order on ONE card while the turn only touched OTHERS (full23 C5: «send rowan a telegram with the new
    # time» re-wrote the meeting on the agenda and the reply said «he's getting the update now» — nothing was
    # sent). The order is carried out on its card, with what the touched card holds.
    _ops_cards = {str(w).split("::")[0] for w, _a in (data_done.get("ops") or [])}
    if _ops_cards and not clarify["msg"] and "close_widget" not in _tool_fired:
        _missed = _pst._direct_action.order_card_after_read(_brief, _op_text, next(iter(_ops_cards)))
        if _missed and _missed not in _ops_cards:
            from nucleo.flash import act_repair as _act_repair_oc
            _oc = await _act_repair_oc.call_after_read(_op_text, next(iter(_ops_cards)), _missed, spec=spec,
                                                       window=list(brain._window))
            if _oc:
                _pst._cvis.present(_oc["widget_id"], reason="turn-order", src="flash", emit=emit)
                _apply_widget_data(_oc["widget_id"], _oc["action"], _oc["payload"])
                emit("brain", "🔁 la orden era sobre otra tarjeta — la llamada, en una segunda pasada",
                     role="system", text=f"{sorted(_ops_cards)} → {_oc['widget_id']}:{_oc['action']}",
                     extra={"cat": "flash", "widget": _oc["widget_id"], "action": _oc["action"]})
    if _repeat_repair["v"] and not clarify["msg"]:
        from nucleo.flash import act_repair as _act_repair_rv
        _rv_card, _rv_seen, _rv_act = _repeat_repair["v"]
        _rv = await _act_repair_rv.call_for_repeated_view(_op_text, _rv_card, _rv_seen, _rv_act, spec=spec,
                                                           window=list(brain._window))
        if _rv:
            _apply_widget_data(_rv["widget_id"], _rv["action"], _rv["payload"])
            acted["widget"] = True
            emit("brain", "🔁 solo repitió la vista — la llamada del veredicto, en una segunda pasada",
                 text=f"{_rv['widget_id']}:{_rv['action']}", role="system",
                 extra={"cat": "flash", "widget": _rv["widget_id"], "action": _rv["action"]})
    # V2-773 — the turn SHOWED a card and promised more on it, or its show was suppressed over the open card
    # with the verdict naming an action: the show is not the act (`card_commission.after_show`).
    if acted.get("widget_id") and not data_done["v"] and not clarify["msg"]:   # a SILENT show too (M1)
        from nucleo.flash import card_commission as _cardc2
        if await _cardc2.after_show(acted, brief=_brief, operator_text=_op_text, spoken_text=spoken_text, spec=spec,
                                    emit=emit, present=_pst._cvis.present, apply_widget_data=_apply_widget_data,
                                    window=list(brain._window)):
            data_done["v"] = True
    # An order that owes WORDS whose data-op RETURNED data (search_archive, peek…): the answer is that data
    # (`data_ops.answer_of`) — composed with it as the only source, after the op lands (bounded wait).
    _op_answer = None
    if read_req["v"] is None and escalate_req["v"] is None and _turn_op_tasks:
        from nucleo.flash import turn_brief as _tbw
        _wk, _wi = _tbw.read(_brief, _tbw.WORDS_KEY, "")
        _rk, _ri = _tbw.read(_brief, _tbw.REQUEST_KEY, "")
        from widgets import effects as _fx_ans
        _answers = any(_fx_ans.carries(_w, _a, _fx_ans.OUTPUT_ANSWER) for _w, _a in (data_done.get("ops") or []))
        if _answers or (_wi is not None and str(_wk) == "tell") or (_ri is not None and str(_rk) == "question"):
            _pend = [t for _w, t in _turn_op_tasks if not t.done()]
            if _pend:
                await _pst.asyncio.wait(_pend, timeout=6.0)
            _got = []
            for _w, _t in _turn_op_tasks:
                try:
                    _got.append((_w, _pst._data_ops.answer_of(_t.result()) if _t.done() and not _t.cancelled() else {}))
                except Exception:  # noqa: BLE001
                    pass
            _op_answer = _pst._data_ops.answer_to_speak(_got, data_done.get("ops"))
        # The card of THIS turn already brought the answer, so a web search next to it is the second-best
        # source (full15 M1: the Apple chart was up with its price, and «the search results only gave me quote
        # pages, so I can't tell you» was what he heard). The card answers; the search does not run.
        if _op_answer is not None and search_req["v"] is not None:
            emit("brain", "🔎 la tarjeta ya trae la respuesta — la búsqueda web sobra", role="system",
                 text=f"{_op_answer[0]} ← {search_req['v'][:100]}", extra={"cat": "flash"})
            search_req["v"] = None
    # A QUESTION answered by a lens alone gets its answer read from that card (C1/Z1, `question_left_to_a_lens`).
    if _op_answer is not None:
        import json as _json_oa
        from nucleo.flash import widget_read as _wread_oa
        emit("brain", "📖 la data-op DEVOLVIÓ datos y el turno debe palabras — contesto con ellos",
             text=f"{_op_answer[0]} ← {_op_text[:100]}", role="system", extra={"cat": "flash", "widget": _op_answer[0]})
        await speak(_wread_oa.compose_system(_prompt_mod._lang_lock(), _op_text, _op_answer[0], _op_text,
                                             _json_oa.dumps(_op_answer[1], ensure_ascii=False, default=str)[:3500],
                                             answered=True, on_screen=_pst._direct_action.on_screen_now(_op_answer[0])),
                    _op_text, 220, "op answer compose")
        spoken_text = "".join(spoken).strip()
    elif read_req["v"] is None and escalate_req["v"] is None and search_req["v"] is None and not clarify["msg"]:
        from nucleo.flash import card_commission as _cardc3
        _qlens = _cardc3.question_left_to_a_lens(_brief, ops=list(_data_ops_hechas), acted=acted,
                                                 operator_text=_op_text)
        if _qlens:
            read_req["v"] = {"widget_id": _qlens, "question": _op_text}
            emit("brain", "📖 una pregunta contestada solo con una vista — leo la tarjeta y contesto",
                 text=f"{_qlens} ← {_op_text[:100]}", role="system", extra={"cat": "flash", "widget": _qlens})
    _out = locals()
    return {k: _out[k] for k in ('_named_by_verdict', '_no_tool', '_op_text', 'spoken_text', ) if k in _out}
