"""The turn's ERRANDS — what its close launches after the reply (V2-851 F5: the last stage of `nucleo/turn/pipeline`).

Moved out of `voice/engine/llm/providers/turn_after.py` (the end of `_run_inner`) with no change of behaviour: the
irreversible-order backstop, the errand the turn commissions (and the rest of the same sentence), a spec he stated
reaching its sheet, our own «which one?» kept, the endings a view held. Names the channel owns are read through
`motor` (the channel's module, handed in), so a patch on the provider still governs them.
"""
from __future__ import annotations

from nucleo.acts import message as _message   # our own «which one?» over his word is remembered (V2-850)
from nucleo.circuit import spec as _spec_mod   # the brief's END verdict travels with the errand (T-19 R6)
from nucleo.request import model as _request   # his words travel with the ONE errand his sentence commissions
from nucleo.request import stop as _stop_decision   # V2-820: a replace stops X and starts Y in one act
from nucleo.turn import his_spec_to_sheet as _his_spec   # a spec he stated about one errand reaches its sheet
from nucleo.turn import reply as _reply   # the turn's one mouth: a door's start line on a silent turn (V2-851 F1)
from nucleo.turn import split_by_errand as _sbe   # one sentence about several errands: each one said (2.643)


async def launch_the_errands(*, motor, send, speech, emit, brain, _brief, _op_text, _escalate_mod, _prev_pending,
                             _router, _did_act, _acted_elsewhere, acted, confirm_state, data_done, escalate_req,
                             spoken_text, worker_acted) -> dict:
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
        _escalate_mod.escalate_to_slowbrain(
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
        _reply.say_started(escalate_req.pop("say", ""), spoken_text, send, speech)   # a silent start says so (V2-794)

        # The extra errands of the same sentence (V2-118/V2-155) and the one the pool could not take (three-tasks).
        motor._turn_errands.launch_the_rest(escalate_req, req, _op_text=_op_text, prev_pending=_prev_pending, router=_router,
                                      escalate=_escalate_mod.escalate_to_slowbrain, similar_pending=motor._similar_pending,
                                      emit=emit, spoken_text=spoken_text, send=send, speech=speech)

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
            from nucleo.request import own_question as _own_q   # F2d — and it is durable: the row waits on it
            _own_q.held(_asked_out, spoken_text, _op_text)
    _ending.close_turn()               # the endings a view held are written now, unless the row waits on our question
    if (_each := _sbe.each_line(spoken_text, _op_text)):      # one sentence about several errands: each one said (2.643)
        send(speech.sanitize(_each, drop_metadata=False))
    return {}
