"""The turn's ERRANDS — what its close launches after the reply (V2-851 F5: the last stage of `nucleo/turn/pipeline`).

Moved out of `voice/engine/llm/providers/turn_after.py` (the end of `_run_inner`) with no change of behaviour: the
irreversible-order backstop, the errand the turn commissions (and the rest of the same sentence), a spec he stated
reaching its sheet, our own «which one?» kept, the endings a view held. Names the channel owns are read through
`motor` (the channel's module, handed in), so a patch on the provider still governs them.
"""
from __future__ import annotations

from loguru import logger

from nucleo.acts import message as _message   # our own «which one?» over his word is remembered (V2-850)
from nucleo.circuit import spec as _spec_mod   # the brief's END verdict travels with the errand (T-19 R6)
from nucleo.request import model as _request   # his words travel with the ONE errand his sentence commissions
from nucleo.request import stop as _stop_decision   # V2-820: a replace stops X and starts Y in one act
from nucleo.turn import his_spec_to_sheet as _his_spec   # a spec he stated about one errand reaches its sheet
from nucleo.turn import reply as _reply   # the turn's one mouth: a door's start line on a silent turn (V2-851 F1)
from nucleo.turn import errands_of_a_turn as _eot   # the errand the pool could not take is said (three-tasks)
from nucleo.turn import split_by_errand as _sbe   # one sentence about several errands: each one said (2.643)


def _irreversible_backstop(escalate_req, worker_acted, confirm_state, data_done, _op_text, emit) -> None:
    # BACKSTOP DE ORDEN IRREVERSIBLE (V2-128, medido). «Paga la factura de la luz antes del día 5» acabó
    # creando un RECORDATORIO: el operador tuvo que corregir («no quiero un recordatorio, quiero que la
    # pagues tú»). Una orden de pagar/comprar/cancelar es del mundo real y su sitio es una tarea — que
    # además pasa por el confirm-gate, que es la conducta que estos casos puntúan BIEN. Apuntarla en la
    # agenda no la ejecuta y deja al operador creyendo que sí.
    # `danger.is_dangerous` es el MISMO clasificador que decide el gate, así que backstop y puerta no pueden
    # discrepar; y ya recorta los recados («recuérdame pagar…» NO es una orden de pagar). …AND `data_done` IS WHY IT NO LONGER OVERRULES THE SCREEN (V2-748, session 48e85cd5): the turn escalated on the word «comprar» — inside the TITLE of the row it was writing — had ALREADY dispatched `agenda:add_task`, arbiter and all. A data-op is not the open world; it went through `widgets/server_api._dispatch`, the V2-705 contract and `store.save`'s snapshot. The gate is for what has NO funnel, which `danger.py` says next to `_DESTROY_OBJECT_RE` and nothing enforced until now; and unlike the pattern half of this repair, this half does not depend on any pattern being right.
    if escalate_req["v"] is None and not worker_acted["v"] and not confirm_state.get("opened") and not data_done["v"]:
        try:
            from nucleo import danger as _danger_bk
            if _danger_bk.is_dangerous(_op_text):
                escalate_req["v"] = _op_text
                emit("brain", "🛑 orden irreversible sin escalar → tarea (pasará por el confirm-gate)",
                     text=_op_text[:120], role="system", extra={"cat": "flash"})
            elif _danger_bk.about_a_past_act(_op_text):
                # V2-707 F6 — said out loud so the timeline shows WHY nothing escalated (three complaints, three tasks).
                emit("brain", "🗣️ queja sobre lo ya hecho — no es un encargo nuevo",
                     text=_op_text[:120], role="system", extra={"cat": "flash"})
        except Exception:
            pass


async def launch_the_errands(*, motor, send, speech, emit, brain, _brief, _op_text, _escalate_mod, _prev_pending,
                             _router, _did_act, _acted_elsewhere, acted, confirm_state, data_done, escalate_req,
                             spoken_text, worker_acted) -> dict:
    _irreversible_backstop(escalate_req, worker_acted, confirm_state, data_done, _op_text, emit)

    # Escalates after the TTS; not when the turn addressed a live worker (inject/answer/stop) — save a REPLACE (V2-820).
    _replacing = _stop_decision.start_beside_the_stop(_brief, escalate_req, _op_text, worker_acted, emit=emit)
    if escalate_req["v"] is not None and (not worker_acted["v"] or _replacing):
        req = escalate_req["v"] or _op_text
        # V2-844 F2: a request that belongs to an open errand is ROUTED at the portal (`flow_door`) by the turn's one
        # route, settled here before the first launch — no second yardstick in this branch any more.
        from nucleo.turn import flow_of as _flow
        await _flow.settled()
        # V2-113: mark THIS trace as just-escalated BEFORE publishing, so `_maybe_close_flow` (moments later, in
        # this same turn) doesn't close the flow before `dispatch.run_listener` registers it (`_flow_should_close`).
        try:
            from voice import trace as _trace5
            brain._escalated_trace_id = _trace5.current()
        except Exception:
            pass
        _heard = "" if escalate_req.get("more") else _request.heard()
        _started = _escalate_mod.escalate_to_slowbrain(
            req, context={"src": "voice", "surface": motor._surfaces_mod.pick(escalate_req["surface"].get(req, ""),
                                                                       motor._surfaces_mod.from_brief(_brief)),
                          "done_when": ((escalate_req.get("done_when") or {}).get(req)   # V2-776 L1
                                        or _escalate_mod.done_when_from_brief(_brief)),   # else the brief's END
                          # …and a SURE «none» from it, so the errand's birth never re-infers one from his words
                          _spec_mod.END_KEY: _spec_mod.end_state_declared(_brief),   # (T-19 R6)
                          "heard": _heard,     # his sentence, to the ONE errand it commissions (two: neither)
                          "errand_class": _escalate_mod.class_verdict(_brief),   # the consent class it carries
                          "asked": spoken_text,   # V2-655: si el turno pidió permiso, se APARCA
                          **({"replaces": escalate_req["replaces"]} if _replacing else {}),
                          **({"part": 0} if escalate_req.get("more") else {})})   # V2-844: one of several
        emit("brain", "🧭 Flash → Brain Worker (escalada registrada)", text=req, role="system", extra={"heard": _heard})
        _say = escalate_req.pop("say", "")
        if _started:   # V2-852 T21 — a door that refused said why; «I'm on it» is a start's line, never a refusal's
            _reply.say_started(_say, spoken_text, send, speech)   # a silent start says so (V2-794)

        # The extra errands of the same sentence (V2-118/V2-155) and the one the pool could not take (three-tasks):
        # the second and third of one sentence, and the one it could not start (folded in from the voice provider's
        # `turn_errands.launch_the_rest`, its only caller). An errand the worker pool could not take this turn
        # (`escalate_req["dropped"]`, recorded by the executor's cap and by the listing that rides) is SAID, in his
        # language (`nucleo/turn/errands_of_a_turn.not_started_line`) — the text channel says the same sentence.
        #
        # The ADDITIONAL errands of the same turn (V2-118). They go AFTER the main one and only if it survived: the
        # guards above clear `v` when the turn turns out not to be an errand (a show, a close, an answer to a worker),
        # and then the others were not errands either. Each goes through the SAME dedup as the main one — two similar
        # requests are injected into the one already running instead of opening a second session of the same thing.
        # CREATE-WIDGET BACKSTOP (V2-118 round 2, measured): of three errands, one was «móntame un widget de un juego»;
        # the model called the tool once, for the report, and the task registry of that run held NO `code` task in 14
        # turns while the turn said it was loading a platform game. The create-widget guard only covered a turn that
        # fired NOTHING; here it covers the turn that escalated something else, with the same deterministic
        # classifier, and only when none of the outgoing requests is already a create-widget one.
        # V2-155: what is added is the CLAUSE that asks for the widget, never the whole turn — with «informe» inside,
        # the dedup gave it the report's target widget and ate it by its strongest signal
        # (`router_guards.create_widget_request` has the measurement).
        _w_req = (_router.create_widget_request(_op_text)
                  if not any(_router.looks_like_create_widget(r)
                             for r in [req, *escalate_req["more"]]) else "")
        if _w_req:
            escalate_req["more"].append(_w_req)
            emit("brain", "🏗️ crear-widget del mismo turno, sin lanzar → escalada añadida (backstop)",
                 text=_w_req[:120], role="system", extra={"cat": "flash"})
        _launched = list(_prev_pending) + [{"request": req}]
        for _n, _extra_req in enumerate(escalate_req["more"], start=1):
            try:
                if motor._similar_pending(_extra_req, _launched):
                    from nucleo import dispatch as _disp4
                    _disp4.relay_his_words(_extra_req, _extra_req) and emit("brain", "↪️ tarea adicional → inyección a worker vivo", text=_extra_req, role="system")
                else:
                    _escalate_mod.escalate_to_slowbrain(
                        _extra_req,
                        context={"src": "voice", "surface": escalate_req["surface"].get(_extra_req, ""),
                                 "asked": spoken_text, "part": _n})   # V2-844: one request of several, its own errand
                    emit("brain", "🧭 Flash → Brain Worker (tarea adicional del mismo turno)",
                         text=_extra_req, role="system")
                _launched.append({"request": _extra_req})
            except Exception as _e_more:  # noqa: BLE001
                logger.warning(f"an additional escalation failed (the others go on): {_e_more!r}")
        if (_not_started := _eot.not_started_line(escalate_req.get("dropped") or [])):
            send(speech.sanitize(_not_started, drop_metadata=False))
            emit("brain", "🚫 errands this turn did not start (worker pool)", text="; ".join(escalate_req["dropped"])[:200],
                 role="system", extra={"cat": "flash", "not_started": list(escalate_req["dropped"])})

    # A task that started or waits is visible from its row (V2-851 F1): no later line re-promises or says «not done».
    _his_spec.carry(_op_text)          # every voice turn: a spec he stated about one errand reaches its sheet
    if not _did_act:
        _sbe.routed(_op_text)          # a sentence about several errands goes part by part (node 2.643)
    from nucleo.request import ending as _ending   # V2-851 F2e — a view of the card never reached the send
    if not (_acted_elsewhere or (acted["widget"] and not _ending.only_held())):
        # our «which Raquel?» is a question, and his answer is kept like the card's (V2-850, `directory.asked`)
        _which = _message.asked_which(spoken_text, (str((_brief or {}).get("judged") or "") if isinstance(_brief, dict)
                                                    else "") or _op_text)   # no judged text yet: his own words
        # V2-851 F2c — a question about a door's act that no door asked is counted (never repaired)
        from nucleo.request import ask_outside_door as _aod
        if (_asked_out := _aod.measure(_brief, spoken_text, did_act=False, asked_which=_which, emit=emit)):
            _aod.held(_asked_out, spoken_text, _op_text)   # F2d — and it is durable: the row waits on it
        elif escalate_req["v"] is None:                    # a sure leaving act its words claimed: it is a task
            _aod.claimed(_brief, spoken_text, _op_text, emit=emit)
    _ending.close_turn()               # the endings a view held are written now, unless the row waits on our question
    if (_each := _sbe.each_line(spoken_text, _op_text)):      # one sentence about several errands: each one said (2.643)
        send(speech.sanitize(_each, drop_metadata=False))
    return {}
