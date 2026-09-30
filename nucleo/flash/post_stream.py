"""What the voice turn does AFTER the model has streamed: the post-stream chain (V2-778 F1-10b, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner`: the ordered backstops and second passes that
run once the fast model has answered — the pure-show guard, the commission and picture passes, the escalation
fragment drop, the promise and act repairs, the close license, vault reveal, memory recall, web search, listings,
music, the confirm gates, the acks — up to the holding line of an escalation with no words. The code is the SAME,
byte for byte apart from one indentation level and the turn's tag buffer: `buf` belongs to the provider (its
`take`/`speak` rebind it), so the two places that reset it and the listing pass that feeds it call
`_buf_reset()` / `_buf_add()` instead.

`run()` receives, as keyword arguments, exactly the names the chain used to read from the turn, plus the motor
helpers it used (injected, so this module never imports `voice.engine`). It returns what the rest of the turn
reads from it: `spoken_text` and `_op_text`. It is ONE module for now; splitting it by family is owed (the size
ratchet names it).
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from nucleo.flash import (canvas_license as _canvas_lic, canvas_visibility as _cvis, close_guards as _closeg,
                          data_ops as _data_ops, direct_action as _direct_action,
                          escalation_guard as _eguard, harness_turn as _ht, image_turn as _image_turn,
                          listing_turn as _lt, reminder_guards as _rg, show_target as _show_target,
                          task_recall as _trecall)
from nucleo.flash.panel_canon import wall_tab_for as _wall_tab_for
from voice import brain_notes as _bnotes
from widgets import confirm as _wconfirm


async def run(*, FastClient, _apply_widget_data, _ask_waiting, _auth_pending, _brief, _cover_work, _data_ops_hechas, _dialog, _filler_audio, _has_workers, _prev_pending, _prompt_mod, _repeat_repair, _resolve_confirm, _router, _shown_ids, _tag_emit, _tool_fired, _turn_op_tasks, acted, aside, attention, brain, canvas_h, clarify, confirm_state, cron_seen, data_done, emit, escalate_req, had_pending_confirm, images_req, listing_req, llm_metrics, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, send, speak, spec, speech, spoken, style_fired, take, text, worker_acted,
              _say, _close_target, _identify, _identify_system, _show_guard_target, _show_target_instance, with_also_named, _buf_reset, _buf_add) -> dict:
    """The post-stream chain of ONE turn. Returns `{"spoken_text", "_op_text"}`."""
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
                _guard_wid, _guard_src = _show_target.show_from_verb(text, canvas_h)
            except Exception:
                _guard_wid, _guard_src = None, "none"
        if _guard_wid:
            _was_search = search_req["v"] is not None
            escalate_req["v"] = None
            search_req["v"] = None
            acted["widget"] = True
            # V2-773 — a show the door SUPPRESSES (already open) is not the act: the turn's order was inside
            # the card («Open the most important one»), and `card_commission.after_show` asks for the call.
            acted["show_suppressed"] = not _cvis.present(_guard_wid, reason="turn-order", src="flash", emit=emit)
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
    _eguard.drop_if_fragment(escalate_req, operator_text=operator_text, brief=_brief,
                             last_reply=brain._last_reply or "", emit=emit)

    # V2-741 · THE THIRD RUNG — a declared action BEFORE anything may cost minutes: a catalogue of
    # videos became a worker that took 195 s to reach the `youtube:search` the brief had named.
    if escalate_req["v"] is not None and not acted["widget"] and not data_done["v"]:
        if _direct_action.take_rung(escalate_req, brief=_brief, operator_text=operator_text,
                                    emit=emit, present=_cvis.present,
                                    apply_widget_data=_apply_widget_data):
            acted["widget"] = True
        # V2-770 — the rung fills ONE key; a data-op of two («a partir de noviembre ya no hay piano» →
        # cancel_meeting {title, from}) gets one pass with the named card's fields before a worker.
        elif (_esc_owner := _direct_action.from_brief(_brief)[0]):
            from nucleo import danger as _danger_esc
            from nucleo.flash import act_repair as _act_repair_esc
            _ar = (None if _danger_esc.is_dangerous(operator_text) else   # full44 E3: + the verdict's call
                   await _act_repair_esc.call_for_promise_or_order(operator_text, str(escalate_req.get("v") or ""),
                                                                   _esc_owner, _direct_action.from_brief(_brief)[1],
                                                                   spec=spec, window=list(brain._window)))
            if _ar:
                _cvis.present(_ar["widget_id"], reason="turn-order", src="flash", emit=emit)
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
                                          spec=spec, emit=emit, present=_cvis.present,
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
        _eguard.settle_commission(
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
        _guard_text = _eguard.escalation_text(operator_text, text)
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
    _no_tool = (not acted["widget"] and not data_done["v"] and not music_req["v"] and not worker_acted["v"]
                and escalate_req["v"] is None and search_req["v"] is None
                and all(r["v"] is None for r in (images_req, listing_req, recall_req, read_req, reopen_req,
                                                 reveal_req)))
    _op_text = _router.operator_words(operator_text, text)   # a note is CONTEXT, never the errand
    # V2-754 — sin tool del modelo y con una ORDEN sobre una tarjeta abierta en el brief («Sí, el catálogo» →
    # `show_tab` 0,88 y «te dejo el catálogo» sobre nada): el veredicto completa el turno por la misma puerta.
    if _no_tool and not clarify["msg"] and (
            _direct_action.complete_canvas(_brief, tag_emit=_tag_emit, emit=emit, operator_text=_op_text)
            or _direct_action.complete(_brief, operator_text=_op_text, emit=emit, present=_cvis.present,
                                       apply_widget_data=_apply_widget_data)):
        acted["widget"] = True
        _no_tool = False
    # …and a data-op INSIDE a card he also told to close by its name («stop the video and close youtube»): the
    # card closes after the op (`closes_the_named_card`).
    if data_done["v"] and not clarify["msg"] and "close_widget" not in _tool_fired:
        _cn = _direct_action.closes_the_named_card(_brief, _op_text, data_done.get("ops"))
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
        if _ar_wid and _direct_action.sure_canvas(_brief) == "close":
            # the promise was to CLOSE it: the card's own close, never a data action (S4 emptied the sheet)
            _tag_emit("close", {"id": _show_target.close_target(_ar_wid)})
            acted["widget"] = True
            _no_tool = False
            emit("brain", "🔁 prometió cerrar sin tool — cierra la tarjeta", text=_ar_wid, role="system",
                 extra={"cat": "flash", "widget": _ar_wid, "action": "close"})
            _ar_wid = ""
        _ar_vo, _ar_va = _direct_action.from_brief(_brief)    # full41 E3: a refusal of the verdict's declared act
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
            _cvis.present(_ar["widget_id"], reason="turn-order", src="flash", emit=emit)
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
        _missed = _direct_action.order_card_after_read(_brief, _op_text, next(iter(_ops_cards)))
        if _missed and _missed not in _ops_cards:
            from nucleo.flash import act_repair as _act_repair_oc
            _oc = await _act_repair_oc.call_after_read(_op_text, next(iter(_ops_cards)), _missed, spec=spec,
                                                       window=list(brain._window))
            if _oc:
                _cvis.present(_oc["widget_id"], reason="turn-order", src="flash", emit=emit)
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
                                    emit=emit, present=_cvis.present, apply_widget_data=_apply_widget_data,
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
                await asyncio.wait(_pend, timeout=6.0)
            _got = []
            for _w, _t in _turn_op_tasks:
                try:
                    _got.append((_w, _data_ops.answer_of(_t.result()) if _t.done() and not _t.cancelled() else {}))
                except Exception:  # noqa: BLE001
                    pass
            _op_answer = _data_ops.answer_to_speak(_got, data_done.get("ops"))
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
                                             answered=True, on_screen=_direct_action.on_screen_now(_op_answer[0])),
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
    # U2 (demo passes 34-51, 2026-09-29): «Sure — putting on Like a Prayer now» and no call — an ENGLISH promise
    # of playback, read here with the same gate the branch below applies (music card open, or a music word).
    _playback = _router.promises_playback(spoken_text, _op_text, music_open=_direct_action.on_screen_now("musica"))
    if (_no_tool and spoken_text
            and (_router.promises_action(spoken_text) or _playback
                 or _direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))
                 or _direct_action.verdict_shows(_brief))
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
               if (_router.looks_like_show_strict(_op_text) or _direct_action.verdict_shows(_brief)) else "")
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
            _cvis.present(_pw, reason="turn-order", src="flash", emit=emit)
            emit("brain", "🪟 show por backstop de promesa (prometió mostrar sin tool)", text=_pw, role="system")
        elif _playback:
            # BEFORE any worker or show: the song is on the player, not on the web. The query is the title the
            # words carry, never his sentence whole («no, put like a prayer» is not a song).
            music_req["v"] = {"query": _router.music_query(spoken_text, _op_text), "action": "play"}
            emit("brain", "🎵 música por backstop (prometió ponerla sin tool, en inglés)",
                 text=music_req["v"]["query"][:80], role="system")
        elif (_router.looks_like_create_widget(_op_text) or _router.looks_like_escalate_task(_op_text) or _win_goal
                or _direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))
                or _direct_action.order_over_a_card_left_undone(_brief)):
            # crear widget (o sinónimo: panel/gadget) = código → escala; marketplace/informe = navegador → escala
            escalate_req["v"] = _win_goal or _op_text
            emit("brain", "🧭 escalada por backstop (prometió crear/gestionar sin escalar)",
                 text=(_win_goal or _op_text)[:80], role="system")
        elif _router.looks_like_show_strict(_op_text):    # it named no card: a TAB of the wall, or nothing
            _wtab = _wall_tab_for(_identify_system(_op_text), _op_text)
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
        if _show_target.fullscreen_exit_backstop(
                _bnotes.operator_half(text), fired="fullscreen_widget" in _tool_fired,
                tag_emit=_tag_emit, emit=emit):
            _tool_fired.add("fullscreen_widget")
    except Exception:  # noqa: BLE001 — a backstop never adds an exception to a turn
        pass
    if (not acted.get("closed")) and _canvas_lic.close_license(text, brief=_brief) \
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
        _vc = _direct_action.verdict_card(_brief) if _direct_action.sure_canvas(_brief) == "close" else ""
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
        if not _cw and not _vc and _closeg.is_short_order(text) and len(_openw) == 1:
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
                _canvas_lic.note_operator_close(_cid)                     # V2-650b
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
        _cardc.present_if_show(read_req, brief=_brief, operator_text=operator_text, is_open=_cvis.is_open,
                               present=_cvis.present, emit=emit)
        _cover_work("widget", _wread.cover_target(read_req["v"] or {}, operator_text))
        # A card this turn just changed is read AFTER the change lands (demo pass 2026-09-28, full11 M3: the chart
        # was switched to the Nasdaq and the read, a few ms later, answered «the only thing on the chart is Apple»).
        _rw = str((read_req["v"] or {}).get("widget_id") or "").split("::")[0]
        _pending = [t for w, t in _turn_op_tasks if str(w).split("::")[0] == _rw and not t.done()]
        if _pending:
            await asyncio.wait(_pending, timeout=6.0)
        # A read that serves an ORDER on another card (full20 C5: «send rowan a telegram with the new time» read
        # the agenda for the time) — the order is carried out with what was read, instead of a words-only pass
        # that has no tools and says it cannot.
        _after = None
        _order_card = _direct_action.order_card_after_read(_brief, _op_text, _rw)
        if _order_card:
            from nucleo.flash import act_repair as _act_repair_rd
            _after = await _act_repair_rd.call_after_read(_op_text, _rw, _order_card, spec=spec,
                                                          window=list(brain._window))
        if _after:
            _cvis.present(_after["widget_id"], reason="turn-order", src="flash", emit=emit)
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
        _re = await asyncio.to_thread(_trecall.voice_turn, reopen_req["v"])
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
        _t_s = time.time()
        try:
            from nucleo import websearch as _ws
            res = await asyncio.to_thread(_ws.search, query)
            ctx = _ws.format_results(res)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"web_search falló (voz sigue): {e}")
            res, ctx = {"source": "none", "results": []}, ""
        # EVIDENCIA (2026-08-10): además del proveedor y el número, se guarda QUÉ VOLVIÓ — título, URL y un
        # trozo del snippet de cada resultado, más la respuesta sintetizada si el proveedor la dio. Sin esto
        # se podía auditar que el sistema BUSCÓ, nunca si respondió con lo que traía: la fila decía «7
        # resultados» y el contenido que el modelo leyó se perdía para siempre. Presupuestada en
        # `observability.evidence` (se recorta, no se resume) y best-effort: si falla, el evento sale igual.
        _ev = {"source": res.get("source"), "ai": bool(res.get("ai")), "ms": round((time.time() - _t_s) * 1000),
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
                                  today=time.strftime("%A %d %b %Y (%Y-%m-%d)"), on_screen=_cf_s.this_turn_cards())
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

        await _lt.voice_turn(listing_req["v"], operator_text or text, spec=spec, on_delta=_listing_delta,
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
        _parte_img, _say_img = await _image_turn.voice_turn(images_req["v"], silent=not spoken_text)
        emit("brain", "🖼️ fotos ↩", text=str(_parte_img)[:200], role="system")
        if _say_img:
            send(speech.sanitize(_say_img, drop_metadata=False))
            spoken_text = "".join(spoken).strip()

    if music_req["v"] is not None:
        mq = music_req["v"]
        emit("brain", "🎵 música", text=f"{mq.get('action')} {mq.get('query')}".strip(), role="system")
        _t_m = time.time()

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
            logger.warning(f"play_music falló (voz sigue): {e}")
            res = None
        # Ejecuta el FOLLOWUP de control (volumen/pausa) tras un play/queue OK — en SECUENCIA, nunca antes
        # (bug real 2026-07-23, ver comentario en el collapse de arriba). Fail-open: si falla, el play ya
        # dicho/hecho no se deshace; solo no se aplica el ajuste.
        if music_req.get("followup") and bool(getattr(res, "ok", False)):
            try:
                await _mflow.run(music_req["followup"]["action"], "", extract=None)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"play_music followup falló: {e}")
        ok = bool(getattr(res, "ok", False))
        msg = (getattr(res, "message", "") or "").strip()
        _extra = getattr(res, "extra", {}) or {}
        _resolved = bool(_extra.get("resolved_from"))
        emit("music", "🎵 acción de música", text=mq.get("query") or mq.get("action"), role="system",
             extra={"provider": getattr(res, "provider", ""), "action": mq.get("action"),
                    "ok": ok, "reason": getattr(res, "reason", ""), "surface": _extra.get("surface", ""),
                    "resolved_from": _extra.get("resolved_from", ""),
                    "ms": round((time.time() - _t_m) * 1000)})
        # V2-721/V2-723 — `surface` says WHERE the audio is, never what must be on SCREEN. The door
        # checks the claim against the widget's own declaration and refuses to raise an open card.
        if ok and str(_extra.get("surface") or "") == "widget":
            _cvis.present(str(_extra.get("widget") or ""), reason="producer-mount",
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

    # RED DETERMINISTA de confirmación (V2-017): si había un borrado pendiente y el modelo NO lo resolvió por
    # tool, pero el operador dijo claramente sí/no → resuélvelo igual (no depende del LLM, como hard_interrupt).
    if had_pending_confirm and not confirm_state["handled"]:
        try:
            verdict = _wconfirm.answers_pending(text)
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
        _ans = _gates.resolve_all(text)
        if _ans:
            escalate_req["v"] = None      # contesta a lo PARADO; ni abre tarea nueva ni pide nada más
            escalate_req["more"] = []
            _r = _ans.result if isinstance(_ans.result, dict) else {}
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
            if _disp2.has_active() and _router.looks_like_stop_work(text) and not _direct_action.aims_at_a_card(_brief):
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
        _ht.note_shown(_shown_ids, _router.operator_words(operator_text, text), trace=_ht.current_trace())
        _owed = await _ht.rescue(
            spoken_text, data_done=bool(data_done["v"]), turn_text=text,
            metrics=(None if (acted["widget"] or data_done["v"] or search_req["v"] is not None
                              or music_req["v"] is not None) else llm_metrics),
            may_escalate=(escalate_req["v"] is None and not aside["v"]))
        if _owed:
            escalate_req["v"] = _owed["request"]
            escalate_req["surface"][_owed["request"]] = _owed["surface"]
            if _owed["reason"] == _ht.OVERSIZED:
                emit("brain", "🧾 widget_data cortada por el tope → escalada con superficie documento",
                     text=_owed["head"][:120], role="system")
            else:
                _fix = _rg.follow_up_line()
                send(speech.sanitize(_fix, drop_metadata=False))
                spoken_text = (spoken_text + " " + _fix).strip()
    except Exception as _e_h:  # noqa: BLE001
        logger.warning(f"turn repairs skipped: {_e_h}")

    # Escalada sin texto hablado → frase de espera neutral (V2-029/V2-189): varía turno a turno y esquiva
    # la apertura si un filler ya sonó — en `harness_turn.holding_line`, con su historia.
    if escalate_req["v"] is not None and not spoken_text:
        spoken_text = _rg.holding_line_now(brain._window, _prev_pending,
                                           after_filler=_filler_audio.played_recently())
        send(speech.sanitize(spoken_text, drop_metadata=False))
    return {"spoken_text": spoken_text, "_op_text": _op_text}
