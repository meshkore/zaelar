"""The voice turn AFTER its post-stream chain: the dialog window, the reply event, the extra escalations and the
promise backstop (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` (1,428 lines) with no behaviour change. Every
name the block read from the provider module is read through it (`_p.<name>`), so a patch on the provider still
governs it. `close_the_turn` takes the turn's locals it read as keyword arguments and returns the ones the rest of
`_run_inner` reads, only when bound.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p, turn_errands as _turn_errands


async def close_the_turn(*, send, _acc_ms, _amap_ms, _brief, _busy_at_start, _dialog, _escalate_mod, _filler_audio, _gate_ms, _op_text, _prev_pending, _router, _shown_ids, _start_web_auth, _t_entry, _t_stream0, _tool_fired, _turn_tools, acted, aside, attention, brain, clarify, confirm_state, data_done, deduped, emit, escalate_req, first_ms, first_turn, images_req, listing_req, llm_metrics, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, spec, speech, spoken_text, style_fired, system, t0, text, timings, worker_acted) -> dict:
    _typed_turn = False
    try:
        _typed_turn = attention.was_typed()
    except Exception:
        _typed_turn = False
    _tool_handled = _p._ht.turn_handled(
        typed=_typed_turn, widget=acted["widget"], data=data_done["v"], worker=worker_acted["v"],
        style=style_fired["v"], deduped=deduped["v"], aside=aside["v"],
        escalated=escalate_req["v"] is not None, searched=search_req["v"] is not None,
        music=music_req["v"] is not None, video=("play_video" in _tool_fired),
        images=images_req["v"] is not None,
        confirm=bool(confirm_state.get("opened") or confirm_state.get("handled")))
    if not spoken_text and not _tool_handled:
        try:
            from voice.engine.core import langs                      # V2-603: the shared decision
            spoken_text = _p._rg.mute_backstop(brain._window, langs.current_language(), _prev_pending,
                                              operator_text=_op_text)
        except Exception:
            spoken_text = _p._say().still_on_it if _prev_pending else _p._say().say_again
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # push_user (no append pelado): si el turno ANTERIOR se canceló por solape, su frase ya está registrada y
    # ésta suele ser su versión acumulada por el STT → se sustituye en vez de duplicar el prefijo.
    # fix08 (6d19df41): the window keeps HIS words (`operator_text`, captured before the notes), NOT the
    # composed turn. Notes are ONE-SHOT (`brain_notes.drain`): the model sees them THIS turn and the reply
    # records what was said; persisting them in the window turned them into permanent context, and every later
    # turn re-read them as pending news ("meanwhile, on the Scarborough search..." with the worker at 0%). The
    # barge-in path above still stores the composed text: that turn never answered, so its notes were never
    # consumed and must stay visible.
    _dialog.push_user(brain._window, operator_text)
    if spoken_text:
        # Guarda la respuesta SANEADA (anti-degeneración V2-032): si el modelo empalmó/repitió, no reinyectamos
        # esa basura al turno siguiente → cortamos el bucle de realimentación que degrada al modelo pequeño.
        brain._window.append({"role": "assistant", "content": _dialog.sanitize_reply(spoken_text)})
    elif _p._ht.turn_handled(typed=_typed_turn, widget=acted["widget"], data=data_done["v"],
                          worker=worker_acted["v"], style=style_fired["v"], deduped=False, aside=False,
                          escalated=escalate_req["v"] is not None, searched=search_req["v"] is not None,
                          music=music_req["v"] is not None, video=("play_video" in _tool_fired),
                          images=images_req["v"] is not None,
                          confirm=bool(confirm_state.get("opened") or confirm_state.get("handled"))):
        # The ack closes an order that was CARRIED OUT. `_tool_handled` above is a wider question («may
        # this turn stay mute?») and says yes to a turn whose only act was a re-emitted op the anti-drag
        # guard threw away, or an aside — writing «Done.» after those records a thing that never happened,
        # and the next turn believes it (V2-773 audit: «Make it fullscreen» + a dropped replay = «Done.»).
        _dialog.record_silent_action(brain._window, _p._say().data_ack)
    del brain._window[:-_p._WINDOW_MAX]
    if not first_turn:
        brain._turn_count += 1   # INI-018 T6: solo turnos conversacionales reales cuentan para el cap demo

    # GATE de los FALLBACKS deterministas: el safety-net de widget y el login-fallback son SOLO para PURA CHARLA
    # en la que el modelo se olvidó de emitir la tag. Si el turno YA se resolvió por CUALQUIER tool (música,
    # vídeo, data-op, escalada, búsqueda, worker, estilo, confirm), NO deben re-adivinar nada — ese doble-disparo
    # abría un widget que nadie pidió (bug 17-jul: «necesito que PONgas a Bruce Springsteen» → play_music OK,
    # pero el safety-net corrió igual, el regex `\bpon` casó "pongas" e `_identify` fuzzy-casó ruido → show:clock
    # espurio). music/video no marcaban acted["widget"], por eso hay que mirar TODAS las señales de tool.
    # `_tool_handled` computed above (V2-634), before the mute backstop that also reads it.

    # SAFETY NET (PRIMERO): el modelo a veces DICE que abre/cierra un widget sin emitir la tag → la emitimos
    # nosotros. Va ANTES del login-fallback a propósito (V2-023): "abre mensajería y dime si WhatsApp está
    # conectado" es un SHOW de widget, NUNCA un login — así el login-fallback no roba un turno de widget.
    if not _tool_handled:
        if _p._widget_fallback(_p._bnotes.operator_half(text), emit, ask=lambda m: clarify.__setitem__("msg", m), last_spoken=brain._last_spoken or ""):
            acted["widget"] = True

    # LOGIN FALLBACK (V2-022): "conéctame a X" / "inicia sesión en mi Y" que el modelo NO accionó (se despistó
    # y solo charló) → abrimos el login igualmente (determinista, espejo del guard auth-vs-tarea). Solo si no
    # hubo ya otra acción de widget (el safety-net de arriba ya resolvió un show/close) y NO es una tarea.
    _login_started = False
    if not _tool_handled and not acted["widget"]:
        try:
            from nucleo.flash import router as _router
            if _router.looks_like_login_request(text) and _start_web_auth(_router.login_site(text)):
                _login_started = True
                emit("brain", "🔐 login por fallback (el modelo no disparó la tool)", text=text[:80], role="system")
        except Exception as e:  # noqa: BLE001
            _p.logger.warning(f"login fallback skipped: {e}")

    # BUFFER CONVERSACIONAL de CORTO (V2-013 T131): guardamos el par turno↔respuesta como working set EFÍMERO
    # (`kind='conv'`, TTL corto, importancia baja) — alimenta la ruta de lectura entera de CORTO (T146,
    # `recent_short`) para que el FlashBrain vea "de qué hablábamos", pero NO es un recuerdo durable. El
    # CORAZÓN que DESTILA lo memorable (nombre, hechos, preferencias) es `memory_agent.ingest_utterance`
    # (arriba, off-hot-path). El consolidador (V2-019) poda este buffer por TTL. Reemplaza el write crudo 0.3
    # a ciegas que inflaba la memoria. Best-effort: la memoria no está en el camino crítico de tiempo real.
    # V2-049: se escribe TAMBIÉN en los turnos que ESCALAN (antes se excluían con `escalate_req is None`) — así
    # el turno que LANZA la tarea (y el dato que el operador soltó en él: matrícula, email…) entra en
    # `recent_window` y el worker lo VE en su bloque de CONVERSACIÓN RECIENTE. Ese hueco hacía que el worker
    # investigara sin el dato y lo re-preguntara (bug ITV 17-jul). Si escaló sin hablar, guardamos igual el
    # turno del operador (con lo que dijera zaelar, aunque sea un filler).
    if spoken_text or escalate_req["v"] is not None:
        try:
            from memory import api as memory
            _a = spoken_text or "(me pongo con ello)"
            # HIS words, not the composed turn: `text` carries the one-shot system notes prepended above, and
            # a «[SISTEMA] Avisos pendientes…» block landed in the conversation record (demo run 2026-09-26) —
            # the same leak fix08 closed for the window.
            memory.write(f"Operador: {operator_text[:200]} · zaelar: {_a[:200]}",
                         kind="conv", level="short", importance=0.2, ttl_days=2.0,
                         # u/a estructurados → `memory.recent_window` reconstruye la ventana verbatim sin
                         # parsear el string (circuito de corto plazo, 2026-07-14).
                         meta={"source": "conv", "u": operator_text[:400], "a": _a[:400]})
        except Exception:
            pass

    # (el `health_state.clear("llm")` que había aquí se movió a `fast_client.stream`, al primer chunk que llega:
    #  este punto solo lo alcanza el turno CONVERSACIONAL, y los de solo-tool/show/fragmento se lo saltaban)
    # OBSERVABILIDAD DEL MODELO (FASE 0): TTFT + latencia + TOTALIZADORES de tamaño (chars/tokens de entrada y
    # salida) + cold/warm. Con esto distinguimos «lento por el modelo» de «lento por prompt gigante» y «frío por
    # cold-start». El desglose de QUÉ infla el prompt (system/memoria/reciente/recall/recursos) va en `timings`.
    _fast_ms = round((_p.time.time() - t0) * 1000)
    _filler_audio.note_latency(first_ms)   # V2-716: feeds the cover's adaptive flag; None is refused there
    _reply_extra = {
        # Who resolved this turn. The map stamps `origin: actionmap` on its own event (V2-539); a model
        # turn says so here, so counting turns by origin is one field on both surfaces instead of a
        # label-text heuristic.
        "origin": "flash",
        "ttft_ms": first_ms, "fast_ms": _fast_ms,
        "gen_ms": llm_metrics.get("total_ms"),
        "prompt_ms": timings.get("prompt_ms"), "mem_state_ms": timings.get("mem_state_ms"),
        # Pre-turn attribution (2026-09-01): what this turn spent BEFORE `t0` — the segment the verdict
        # could not see. gate = attention judge (0 inside the active window), acc = fragment/completeness
        # judge (0 on the lexical fast path), the rest is recall wait + prompt build + bookkeeping.
        "pre_ms": round((t0 - _t_entry) * 1000, 1), "gate_ms": _gate_ms, "acc_ms": _acc_ms,
        "amap_ms": _amap_ms,   # action-map lookup on the MISS path (V2-539) — a hit never reaches here
        "mem_query_ms": timings.get("mem_query_ms"), "briefs_ms": timings.get("briefs_ms"),
        "live_ms": timings.get("live_ms"),
        # TOTALIZADORES de tamaño (premisa del operador)
        "prompt_chars": llm_metrics.get("prompt_chars"), "system_chars": llm_metrics.get("system_chars"),
        "prompt_tokens": llm_metrics.get("prompt_tokens", llm_metrics.get("prompt_tokens_est")),
        "completion_tokens": llm_metrics.get("completion_tokens", llm_metrics.get("completion_tokens_est")),
        "completion_chars": llm_metrics.get("completion_chars"),
        "n_tools": llm_metrics.get("n_tools"), "tools_chars": llm_metrics.get("tools_chars"),
        "n_msgs": llm_metrics.get("n_msgs"), "usage_source": llm_metrics.get("usage_source"),
        # Prefix-cache hit (DeepSeek usage). fast_client captured it for billing since 2026-08-14; the
        # latency verdict needs it too — a cold prefill of a ~10k-token prompt is the one TTFT cause
        # that is OURS (prefix instability), and without this field it was indistinguishable from
        # hidden reasoning or provider queueing (see turn_perf.verdict).
        "prompt_cache_hit_tokens": llm_metrics.get("prompt_cache_hit_tokens"),
        # desglose de QUÉ hace grande el prompt (chars por bloque)
        "sz_memory": timings.get("sz_memory"), "sz_recent": timings.get("sz_recent"),
        "sz_recall": timings.get("sz_recall"), "sz_resources": timings.get("sz_resources"),
        "sz_live": timings.get("sz_live"), "window_msgs": len(brain._window),
        # cold-start (FASE 1)
        "cold_estimate": llm_metrics.get("cold_estimate"), "gap_since_last_s": llm_metrics.get("gap_since_last_s"),
        # tokens/seg (throughput del modelo, independiente del tamaño)
        "tok_per_s": (round((llm_metrics.get("completion_tokens") or llm_metrics.get("completion_tokens_est") or 0)
                            / max(0.001, (llm_metrics.get("total_ms") or 0) / 1000.0), 1)
                      if llm_metrics.get("total_ms") else None),
        "escalated": bool(escalate_req["v"] is not None),
        "searched": bool(search_req["v"] is not None),
        "recent_fired": timings.get("recent_fired"), "recall_fired": timings.get("recall_fired"),
        # FASE 3: contención local activa al arrancar el turno (para correlacionar con el TTFT)
        "busy_at_start": _busy_at_start or None, "contended": bool(_busy_at_start),
        "engine": spec.provider, "model": spec.model,
        # WHAT THE MODEL RETURNED, raw (demo pass 2026-09-28, C2: 127 tokens, 0 chars, no call — unreadable).
        "finish_reason": llm_metrics.get("finish_reason"), "raw_text": llm_metrics.get("raw_text"),
        "raw_tool_calls": llm_metrics.get("raw_tool_calls"), "reasoning_chars": llm_metrics.get("reasoning_chars"),
        "dropped_tool_calls": llm_metrics.get("dropped_tool_calls"),
    }
    # V2-587 — this turn's «did anything actually run» fact, computed ONCE and read by the empty-wait
    # guard here and by the promise backstop below (two copies of a nine-flag expression is how they drift).
    # …and a READ is an act (V2-773 audit): «Let me check your calendar» followed by a `read_widget` and its
    # answer was judged «promised to look and did not», read AGAIN with the raw sentence, and the second
    # answer — over the summary this time — contradicted the first out loud.
    _did_act = bool(acted["widget"] or data_done["v"] or worker_acted["v"] or escalate_req["v"] is not None
                    or search_req["v"] is not None or music_req["v"] is not None or confirm_state.get("opened")
                    or clarify.get("msg") or read_req["v"] is not None
                    # every other door a turn acts through (full27 A1: `search_listings` launched the monitor
                    # errand and the promise guard, not counting it, added «I haven't looked, nothing is running»)
                    or any(r["v"] is not None for r in (listing_req, images_req, recall_req, reopen_req,
                                                        reveal_req)))
    # The three HOLLOW-turn repairs — V2-572 bare «Hecho.» · V2-587 empty wait · V2-642 MUTE after a
    # sounded cover («Déjame que mire…» then silence forever, session 651c25ac) — live in ONE seam:
    # `second_pass.hollow_repairs`. The turn always closes; failing everything, the honest closer speaks.
    _aside_turn = bool(aside["v"] and not _typed_turn)   # V2-657 — see the [[aparte]] branch in _tag_emit
    if not _aside_turn:
        try:
            from voice.engine.core import langs as _lg_cl
            from voice.engine.speech import filler_audio as _fa_cl
            from nucleo.flash import second_pass as _second
            spoken_text = await _second.hollow_repairs(
                text, spoken_text, brain._window, spec, did_act=_did_act,
                covered=bool(_fa_cl.last_fired_at() and _fa_cl.last_fired_at() >= _t_stream0),
                # a delta after what was already said is never glued to it («…for tomorrow.Tomorrow, Tuesday»)
                speak=lambda _r, _sp=spoken_text: send((" " if (_sp or "").strip() else "")
                                                     + speech.sanitize(_r, drop_metadata=False)),
                emit=emit, pick_closer=_lg_cl.pick_closer)
        except Exception:
            pass
    elif not spoken_text and not _did_act:
        _p._ht.note_aside(text, attention=attention, emit=emit)
    emit("brain", "⚡ Nucleo(flash): reply", text=spoken_text, role="assistant", extra=_reply_extra)
    # …y el VEREDICTO en una línea legible: si el turno pasó del listón, POR QUÉ (prompt grande / proveedor /
    # frío / trabajo real). Los números ya estaban todos en `_reply_extra`, pero enterrados en el extra: había
    # que exportar el jsonl para saber si un turno de 8 s fue culpa nuestra o del proveedor.
    try:
        from nucleo.flash import turn_perf as _perf
        _v_perf = _perf.emit_verdict({**_reply_extra, "total_ms": _fast_ms})
        # …y ese veredicto ALIMENTA el relevo por latencia (V2-094). El circuito no vuelve a medir nada: lee la
        # causa que acaba de decidirse. `note_slow` exige turnos lentos SEGUIDOS, tiene cooldown corto y techo
        # de turnos en el escalón de relevo — un turno lento no puede convertirse en una factura sorpresa.
        # Cambia el titular para los turnos SIGUIENTES; el actual ya está entregado.
        from nucleo.flash import provider_chain as _pchain
        _pchain.note_slow(_v_perf, role=_pchain.ROLE_VOICE)
    except Exception:
        pass

    # CAPTURA FORENSE del turno (V2-040): prompt + ventana + tools + decisión, en categoría `system` (fichero,
    # no floodea el visor) — para diagnosticar a futuro cosas como la re-escalada en un turno ambiente.
    try:
        emit_turn = getattr(__import__("voice.observer", fromlist=["turn_detail"]), "turn_detail")
        emit_turn(system=system, window=_dialog.prune_window(brain._window)[-_p._WINDOW_MAX:], tools=_turn_tools,
                  user=text, decision={
                      "escalated": bool(escalate_req["v"] is not None), "escalate_req": (escalate_req["v"] or "")[:200],
                      "searched": bool(search_req["v"] is not None), "widget_acted": acted["widget"],
                      "worker_acted": worker_acted["v"], "data_done": data_done["v"],
                      "confirm_opened": bool(confirm_state.get("opened")), "clarify": bool(clarify["msg"]),
                      "shown_ids": sorted(_shown_ids), "reply": (spoken_text or "")[:400],
                      # WHAT the model asked for, verbatim — a call a guard ate or a completion replaced is
                      # otherwise invisible (demo pass 2026-09-28, S3: `results:detail {}` with no trace of
                      # whether the model or the verdict wrote the empty payload).
                      "model_calls": list(getattr(brain, "_turn_calls", None) or [])[:12]},
                  extra={"turn_ms": _reply_extra.get("total_ms")})
    except Exception:
        pass

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
                # V2-707 F6 — said out loud so the timeline shows WHY nothing escalated: on 2026-09-16
                # three of his complaints became three Brain Worker tasks, invisibly.
                emit("brain", "🗣️ queja sobre lo ya hecho — no es un encargo nuevo",
                     text=_op_text[:120], role="system", extra={"cat": "flash"})
        except Exception:
            pass

    # Escala DESPUÉS de que el texto del turno rápido va camino de TTS. NO escala si ya se dirigió a un worker
    # vivo (inject/stop/answer) este turno.
    if escalate_req["v"] is not None and not worker_acted["v"]:
        req = escalate_req["v"] or _op_text
        # V2-038 §v3·G: si una tarea MUY parecida ya está EN CURSO, esto es un REFINAMIENTO → se INYECTA a esa
        # sesión (no se descarta como antes, ni se abre otra). Reemplaza el dedup-descartar de V2-029.
        if _p._similar_pending(req, _prev_pending):
            try:
                from nucleo import dispatch as _disp3
                _disp3.inject_soon(req, req)
                emit("brain", "↪️ refinamiento → inyección a worker vivo (no relanza)", text=req, role="system")
            except Exception:
                emit("brain", "🧭 escalada duplicada ignorada", text=req, role="system")
        else:
            # V2-113: mark THIS trace as just-escalated BEFORE publishing, so `_maybe_close_flow` (which runs
            # moments later, still inside this same turn) doesn't close the flow while `dispatch.run_listener`
            # hasn't had a scheduler turn to register/reject/dedup it yet — see `_flow_should_close`.
            try:
                from voice import trace as _trace5
                brain._escalated_trace_id = _trace5.current()
            except Exception:
                pass
            _escalate_mod.escalate_to_slowbrain(
                req, context={"src": "voice", "surface": _p._surfaces_mod.pick(escalate_req["surface"].get(req, ""),
                                                                           _p._surfaces_mod.from_brief(_brief)),
                              "done_when": (escalate_req.get("done_when") or {}).get(req),   # V2-776 L1
                              "asked": spoken_text})   # V2-655: si el turno pidió permiso, se APARCA
            emit("brain", "🧭 Flash → Brain Worker (escalada registrada)", text=req, role="system")

        # The extra errands of the same sentence (V2-118/V2-155) and the one the pool could not take (three-tasks).
        _turn_errands.launch_the_rest(escalate_req, req, _op_text=_op_text, prev_pending=_prev_pending, router=_router,
                                      escalate=_escalate_mod.escalate_to_slowbrain, similar_pending=_p._similar_pending,
                                      emit=emit, spoken_text=spoken_text, send=send, speech=speech)

    # Promise-without-action, and the forced escalation behind it (V2-049 + V2-534). The DECISION moved to
    # `promise_backstop.py` (architecture ratchet, same pattern as `vault_intercept.py`); `_did_act` is
    # computed ONCE above the answer guards (V2-587) — it reads nine dicts of THIS turn's closure.
    from voice.engine.llm.providers import promise_backstop as _promise_backstop
    _promise_backstop.run(spoken_text, did_act=_did_act, op_text=_op_text, prev_pending=_prev_pending,
                          emit=emit, escalate=_escalate_mod.escalate_to_slowbrain,
                          similar_pending=_p._similar_pending, brief=_brief)
    _out = {}
    return _out
