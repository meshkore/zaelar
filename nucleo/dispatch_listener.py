"""The SlowBrain's escalation listener — what turns a `escalate.requested` into a worker (V2-778 F1-11, 2026-10-01).

Moved out of `nucleo/dispatch.py`, which stays the facade: `dispatch.run_listener` delegates here. The body is the
SAME code; the one change is that every name it read from the dispatcher (its registry, `_run_session`, `inject`,
the dedup and continuity gates…) is read THROUGH the module — `_d.<name>` — so a test or a caller that patches
`dispatch.<name>` still governs the listener exactly as before the move.
"""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo import dispatch as _d


async def run_listener(stop: "asyncio.Event | None" = None) -> None:
    import bus

    sub = bus.subscribe("escalate.requested")
    logger.info("dispatch: listener de escalados (Brain Workers) arrancado")
    try:
        while stop is None or not stop.is_set():
            try:
                ev = await asyncio.wait_for(sub.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
            payload = ev if isinstance(ev, dict) else {}
            tid = payload.get("id")
            request = (payload.get("request") or "").strip()
            ctx = payload.get("context") or {}
            if not request:
                continue
            key = str(tid or "?")
            kind = str(ctx.get("kind", "generic"))
            # V2-092: with the agent PARADO (⏻) NO is opens work new. Los workers that already estaban is congelan and
            # continuan al start (pause_all/resume_all), but start uno DESDE CERO sobre a agent parado es
            # it contrario of parar. Se rechaza VISIBLE (evento `task/blocked`), never in silencio: a escalada that
            # desaparece without rastro es the clase of failure that cuesta a session of diagnostico.
            from nucleo import runstate
            _halted = runstate.blocks_new_work(who="dispatch")   # V2-655: falla CERRADO, ver ese docstring
            if _halted:
                try:
                    from voice.observer import emit
                    emit("task", "blocked", role="system", text=request[:120],
                         extra={"id": key, "reason": "el agente está parado (⏻): no se abre trabajo nuevo"})
                except Exception:
                    pass
                _d._close_escalated_flow(ctx, ok=False, status="rejected_halted")
                logger.info(f"dispatch: escalada RECHAZADA (agente parado): {request[:80]}")
                continue
            # DEDUP in the FUENTE DE VERDAD (§session 2026-07-15): if already there is a session live atendiendo this same
            # request, NO abrimos a 2º worker (the bug of the two «creando a widget…»). Se INYECTA como
            # refinamiento (the generador of widgets, build atomico, it ignora with gracia; a worker live it aprovecha).
            dup, _ev = _d.dedup_scan(request, kind if kind != "generic" else _d._classify_kind(request))
            # `by` now comes from the deciding loop instead of being assumed here: a same-widget hit used to
            # be filed as «containment», which is a number it never computed.
            _dup_by = _ev.get("by") or ""
            _model = "skipped"          # the second half only runs with something live to compare against
            if not dup:
                # SEGUNDA MITAD DEL DEDUP, off-loop. `find_duplicate` responds «¿es a reformulacion of it
                # same?» and no can responder «¿es esto a errand siquiera?» — ver `about_a_live_errand`.
                # Only corre with something live, so that the first errand of a conversacion no it paga; and va in
                # a hilo because `chat_sync` es sincrono and this bucle es the of the servidor.
                _live = _d._live_errands()
                if _live:
                    try:
                        dup = await asyncio.to_thread(_d.about_a_live_errand, request, _live)
                        _dup_by = "model" if dup else _dup_by
                        _model = "about" if dup else "separate"
                    except Exception as e:  # noqa: BLE001
                        dup = ""
                        # A model half that CRASHED used to be indistinguishable from one that answered
                        # «separate» — the same confusion as the mute miss, one layer in. Recorded, not
                        # changed: the fail-open stays, an unreachable judge must never block an errand.
                        _model = f"error:{type(e).__name__}"
            if dup:
                try:
                    from voice.observer import emit
                    # `by` separa the DOS mitades of the dedup, and without el no is can medir by separado:
                    # `containment` es a reformulacion of the same errand, `model` es a turn that no era a
                    # errand (a question by how va). Contarlas juntas esconde which of the two falla.
                    emit("task", "dedup", role="system", text=request[:120],
                         extra={"id": dup, "dropped_id": key, "by": _dup_by,
                                "reason": ("no es un encargo nuevo: va sobre una tarea viva"
                                           if _dup_by == "model" else
                                           "escalada duplicada de una tarea viva")})
                except Exception:
                    pass
                try:
                    await _d.inject(dup, request)      # refinamiento a la sesión viva (no relanza)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"dispatch: inject de dedup a {dup} falló: {e}")
                # Same task, proven by the dedup match → ONE flow (V2-123). Only when the fuse didn't happen does
                # this trace still need its own explicit close, or `just_escalated` would keep it open forever.
                if not _d._merge_dedup_flow(ctx, dup):
                    _d._close_escalated_flow(ctx, ok=True, status="dedup_injected")
                continue
            # A PARKED ERRAND IS STILL THE ERRAND HE IS TALKING ABOUT (2026-09-29, session 81095d8d). The gate
            # pops the record when it parks, so the live dedup above cannot see it — and every repetition of
            # the order («provide the link», «give me the link and don't ask me again») opened another task,
            # another sheet and asked the same question again: four errands for one intention. Same yardstick
            # and same model half as the live dedup, over `parked_errands()`; a hit is folded into the parked
            # one (`absorb_refinement`) and the brain is told which question is still waiting, so the next
            # turn repeats the QUESTION instead of the work. A confirmed relaunch carries `confirmed` and is
            # never compared here: it IS the parked errand coming back through the door.
            if not bool(ctx.get("confirmed")):
                _parked = _d.parked_errands()
                pdup = None
                if _parked:
                    pdup, _pev = _d._dedup.scan(request, kind if kind != "generic" else _d._classify_kind(request),
                                             _parked)
                    if not pdup:
                        try:
                            pdup = await asyncio.to_thread(_d.about_a_live_errand, request, _parked) or None
                        except Exception:  # noqa: BLE001 — fail-open, like the live half
                            pdup = None
                if pdup:
                    question = _d.absorb_refinement(pdup, request)
                    try:
                        from voice.observer import emit
                        emit("task", "dedup", role="system", text=request[:120],
                             extra={"id": pdup, "dropped_id": key, "by": "parked",
                                    "reason": "va sobre una tarea APARCADA esperando su respuesta: no se abre otra"})
                    except Exception:
                        pass
                    try:
                        from voice import brain_notes
                        brain_notes.push(
                            "[SISTEMA] Eso es la MISMA tarea que está aparcada esperando su respuesta"
                            + (f": «{question[:160]}»" if question else "")
                            + ". No has abierto nada nuevo. Repítele la pregunta en una frase corta y espera "
                              "su sí o su no.")
                    except Exception:  # noqa: BLE001
                        pass
                    _d._close_escalated_flow(ctx, ok=True, status="dedup_parked")
                    continue
            # THE NEGATIVE DECISION, SAID OUT LOUD (V2-507). Only the hit was emitted, so «the dedup did not
            # fire» could not be told from «there was nothing live to fire against» — opposite fixes, and the
            # round of 20260830-114302 spent a full replay of the event log without settling it. `live` is the
            # one that decides: 0 means nobody was there to match, and no yardstick can be blamed for that.
            try:
                from voice.observer import emit
                emit("task", "dedup_miss", role="system", text=request[:120],
                     extra={"id": key, "live": _ev.get("live", 0), "best": _ev.get("best", 0.0),
                            "against": _ev.get("against", ""), "bar": _ev.get("bar", 0.0), "model": _model,
                            # V2-570 — a fresh fast-pass delivery is named HERE too: «nothing live» with a
                            # just-delivered hunt on screen was how two boxes looked like a clean miss.
                            "listing_recent": [r["id"] for r in _d._ended.recent_listing_deliveries()][:3],
                            "reason": ("encargo NUEVO: no había ninguna tarea viva contra la que comparar"
                                       if not _ev.get("live") else
                                       "encargo NUEVO: no casa con ninguna tarea viva")})
            except Exception:
                pass
            # V2-566/V2-570 — A FOLLOW-UP IS NOT A NEW ERRAND, and a follow-up of a DELIVERED listing fast
            # pass does not spawn a parallel worker. Both decisions live in `nucleo/errand_continuity.py`
            # (extracted: dispatch sat one line under its ratchet ceiling): the escalation may come back with
            # an inherited sheet, or redirected entirely to a refined fast re-run in the same box — in which
            # case there is no session to open and the module already owns the errand's next step.
            ctx, _redirected = _d._continuity.inherit_and_maybe_rerun(
                request, kind if kind != "generic" else _d._classify_kind(request), ctx, key)
            if _redirected:
                _d._close_escalated_flow(ctx, ok=True, status="linear_rerun")
                continue
            # V2-049 CONTINUIDAD: without session live that casar, ¿there is a operation web INCOMPLETA reciente that ESTA
            # request resumes? (nudge «continues with the ITV», or the operator aportando the dato that was missing). Reanuda esa
            # same tab + razonamiento in vez of start of cero.
            _k = kind if kind != "generic" else _d._classify_kind(request)
            if _k == "web":
                # take=True: the reanudacion is CONSUME al entregarla. Sin eso, two escaladas of the same
                # request is llevan the same id of session of the CLI and the second dies in the arranque.
                _res = _d._find_resume(request, take=True)
                if _res and (_res.get("nav_task") or _res.get("native_sid")):
                    ctx = dict(ctx)
                    ctx["resume"] = _res
                    try:
                        from voice.observer import emit
                        emit("task", "resume", role="system", text=request[:120],
                             extra={"id": key, "nav_task": _res.get("nav_task", ""),
                                    "reason": "reanuda gestión web incompleta (no re-lanza de cero)"})
                    except Exception:
                        pass
            task = _d.Task(id=key, request=request, kind=kind,
                        trusted=bool(ctx.get("trusted", True)), context=ctx)
            rec = _d.SessionRecord(task_id=key, goal=request[:200], kind=task.kind,
                                parent_task_id=str(ctx.get("parent_task_id", "")),
                                depth=int(ctx.get("depth", 0) or 0),
                                # La GENERACIÓN of relevo viaja with the cadena. Sin esto the cap of `_finish` no
                                # exists: each relevo estrena record and su contador vuelve a cero.
                                relay_gen=int(ctx.get("relay_gen", 0) or 0),
                                # …and the SHEET with it, for the same reason: a relay continues the errand, so
                                # it keeps writing where the operator is already looking instead of opening a
                                # second box beside it.
                                sheet=str(ctx.get("sheet", "") or ""),
                                # …and HOW SUCCESS IS MEASURED (V2-707 F2): a relay that dropped the condition
                                # would deliver the half-done work the harness had just caught.
                                done_when=dict(ctx.get("done_when") or {}),
                                trace_id=str(ctx.get("trace", "") or ""))   # V2-044: encadena a la frase origen
            # V2-227 — the SUPERFICIE is sella here, that es the only point by the that pasan TODAS the puertas of
            # entrada al dispatcher (the cerebro with su `surface`, the auto-resume, the confirm-gate, the cluster, the
            # Susurro). Lo that declaro the cerebro manda; if no declaro nothing —or said something that no es of the
            # vocabulario— is deriva of the kind. Sellar tarde significaria open the sheet when already there is response,
            # that es exactamente it that this cambio exists for no do.
            _d.surfaces.set_once(rec, ctx.get("surface"))
            # …and if esa superficie es the sheet, is ABRE YA, empty and with the tab of proceso. Aqui, and no in the
            # entrega, es donde the operator leaves of mirar a pantalla in blanco.
            if _d.surfaces.opens_sheet(getattr(rec, "surface", "")):
                _d._sheet_open(rec)
            elif _d.surfaces.opens_doc(getattr(rec, "surface", "")):   # a REPORT opens the DOCUMENT sheet (V2-644)
                _d._docsheet.doc_open(rec)
            _d._SESSIONS[key] = rec
            # V2-728 — the DURABLE row. `_SESSIONS` is RAM and a restart empties it, so the commission the
            # operator just handed over would stop existing the moment the engine bounced. Written HERE, at
            # the one point every door into the dispatcher passes through, for the same reason the surface is
            # sealed here. Best-effort and off the hot path: a store that failed must not lose the worker.
            try:
                from nucleo import tasks as _tasks
                _tasks.opened(rec, ctx)
            except Exception:  # noqa: BLE001
                logger.debug("dispatch: no pude registrar la tarea durable", exc_info=True)
            _d._name_errand(rec)          # V2-530 — asynchronous; the sheet is already open under its brief

            rec.task = asyncio.create_task(_d._run_session(task), name=f"worker-session-{key}")
            _d.sync_state()
    finally:
        sub.close()
        logger.info("dispatch: listener de escalados detenido")
