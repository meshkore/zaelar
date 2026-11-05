"""The turn's CLOSE — the dialog window, the fallbacks, the reply event and its verdict (V2-851 F5: stage of
`nucleo/turn/pipeline`).

Moved out of `voice/engine/llm/providers/turn_after.py` with no change of behaviour, less what F5 removed (the hollow
repairs). The errands the close launches live in `pipeline_errands`. Every name the block read from the provider
module is read through `motor` (the channel's module, handed in), so a patch on the provider still governs it and
nothing here imports the motor.
"""
from __future__ import annotations

from loguru import logger

from nucleo.turn import mouth as _mouth   # V2-851 F5: what the turn's doors owe is said before it closes
from nucleo.turn import pipeline_errands as _errands
from nucleo.turn import wait_lines as _wait_lines


async def close_the_turn(*, motor, send, _acc_ms, _amap_ms, _brief, _busy_at_start, _dialog, _escalate_mod, _filler_audio, _gate_ms, _op_text, _prev_pending, _router, _shown_ids, _start_web_auth, _t_entry, _tool_fired, _turn_tools, acted, aside, attention, brain, clarify, confirm_state, data_done, deduped, emit, escalate_req, first_ms, first_turn, images_req, listing_req, llm_metrics, music_req, operator_text, read_req, recall_req, reopen_req, reveal_req, search_req, spec, speech, spoken_text, style_fired, system, t0, text, timings, worker_acted) -> dict:
    _typed_turn = False
    try:
        _typed_turn = attention.was_typed()
    except Exception:
        _typed_turn = False
    _tool_handled = motor._ht.turn_handled(
        typed=_typed_turn, widget=acted["widget"], data=data_done["v"], worker=worker_acted["v"],
        style=style_fired["v"], deduped=deduped["v"], aside=aside["v"],
        escalated=escalate_req["v"] is not None, searched=search_req["v"] is not None,
        music=music_req["v"] is not None, video=("play_video" in _tool_fired),
        images=images_req["v"] is not None,
        confirm=bool(confirm_state.get("opened") or confirm_state.get("handled")))
    if not spoken_text and not _tool_handled:
        try:
            from i18n import langs                      # V2-603: the shared decision
            spoken_text = _wait_lines.mute_backstop(brain._window, langs.current_language(), _prev_pending,
                                              operator_text=_op_text)
        except Exception:
            spoken_text = motor._say().still_on_it if _prev_pending else motor._say().say_again
        send(speech.sanitize(spoken_text, drop_metadata=False))

    # push_user, not a bare append: a turn cancelled by an overlap is replaced by its accumulated STT version. The window
    # keeps HIS words (fix08): notes are one-shot, and kept in the window they read as pending news on every later
    # turn. The barge-in path above keeps the composed text: that turn never answered, so its notes stay visible.
    _dialog.push_user(brain._window, operator_text)
    if spoken_text:
        # Guarda la respuesta SANEADA (anti-degeneración V2-032): si el modelo empalmó/repitió, no reinyectamos
        # esa basura al turno siguiente → cortamos el bucle de realimentación que degrada al modelo pequeño.
        brain._window.append({"role": "assistant", "content": _dialog.sanitize_reply(spoken_text)})
    elif motor._ht.turn_handled(typed=_typed_turn, widget=acted["widget"], data=data_done["v"],
                          worker=worker_acted["v"], style=style_fired["v"], deduped=False, aside=False,
                          escalated=escalate_req["v"] is not None, searched=search_req["v"] is not None,
                          music=music_req["v"] is not None, video=("play_video" in _tool_fired),
                          images=images_req["v"] is not None,
                          confirm=bool(confirm_state.get("opened") or confirm_state.get("handled"))):
        # The ack closes an order that was CARRIED OUT. `_tool_handled` above is a wider question («may
        # this turn stay mute?») and says yes to a turn whose only act was a re-emitted op the anti-drag
        # guard threw away, or an aside — writing «Done.» after those records a thing that never happened,
        # and the next turn believes it (V2-773 audit: «Make it fullscreen» + a dropped replay = «Done.»).
        _dialog.record_silent_action(brain._window, motor._say().data_ack)
    _dialog.source_last_reply(brain._window, search_req["v"])   # V2-834 T11: a searched reply keeps its source
    del brain._window[:-motor._WINDOW_MAX]
    if not first_turn:
        brain._turn_count += 1   # only real conversational turns count toward the per-session turn limit

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
        if motor._widget_fallback(text, emit, ask=lambda m: clarify.__setitem__("msg", m), last_spoken=brain._last_spoken or "", brief=_brief):
            acted["widget"] = True

    # LOGIN FALLBACK (V2-022): "conéctame a X" / "inicia sesión en mi Y" que el modelo NO accionó (se despistó
    # y solo charló) → abrimos el login igualmente (determinista, espejo del guard auth-vs-tarea). Solo si no
    # hubo ya otra acción de widget (el safety-net de arriba ya resolvió un show/close) y NO es una tarea.
    _login_started = False
    if not _tool_handled and not acted["widget"]:
        try:
            from nucleo.flash import router as _router, web_auth as _wa_fb
            if _router.looks_like_login_request(text) and _start_web_auth(_wa_fb.fallback_site(text)):
                _login_started = True
                emit("brain", "🔐 login por fallback (el modelo no disparó la tool)", text=text[:80], role="system")
        except Exception as e:  # noqa: BLE001
            motor.logger.warning(f"login fallback skipped: {e!r}")

    # SHORT conversational buffer (V2-013 T131): the turn↔reply pair as an EPHEMERAL working set (`kind='conv'`, short
    # TTL) so the next turn sees «what we were talking about»; what is memorable is distilled by `ingest_utterance`.
    # V2-049: written on ESCALATING turns too, so the worker sees the datum he gave in the turn that launched it.
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
    _fast_ms = round((motor.time.time() - t0) * 1000)
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
    # V2-851 F2e — data-ops that only VIEWED a card whose act leaves (their ending held) did not act on his request: a
    # «which Rachel?» after `mensajeria:show_view` is our own question, measured and made durable (battery C1 en).
    from nucleo.request import ending as _ending
    _held_views = bool(data_done["v"]) and _ending.only_held()
    _acted_elsewhere = bool((data_done["v"] and not _held_views) or worker_acted["v"] or escalate_req["v"] is not None
                    or search_req["v"] is not None or music_req["v"] is not None or confirm_state.get("opened")
                    or clarify.get("msg") or read_req["v"] is not None
                    # every other door a turn acts through (full27 A1: `search_listings` launched the monitor
                    # errand and the promise guard, not counting it, added «I haven't looked, nothing is running»)
                    or any(r["v"] is not None for r in (listing_req, images_req, recall_req, reopen_req,
                                                        reveal_req)))
    _did_act = bool(acted["widget"] or _acted_elsewhere or _held_views)
    # The hollow-turn repairs (V2-572 bare «Hecho.» · V2-587 empty wait · V2-642 mute after a cover · V2-717 a promise
    # to look) composed a second answer with the model after the reply; they went in V2-851 F5 with every re-run after
    # the main stream. A turn with no words at all still closes through the mute backstop above.
    _aside_turn = bool(aside["v"] and not _typed_turn)   # V2-657 — see the [[aparte]] branch in _tag_emit
    if _aside_turn and not spoken_text and not _did_act:
        motor._ht.note_aside(text, attention=attention, emit=emit)
    spoken_text = _mouth.close(spoken_text, send, speech)   # V2-851 F5: the lines the turn's doors still owe, then shut
    emit("brain", "⚡ Nucleo(flash): reply", text=spoken_text, role="assistant", extra=_with_usage(_reply_extra, spec))
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
        from nucleo.llm import provider_chain as _pchain
        _pchain.note_slow(_v_perf, role=_pchain.ROLE_VOICE)
    except Exception:
        pass

    # CAPTURA FORENSE del turno (V2-040): prompt + ventana + tools + decisión, en categoría `system` (fichero,
    # no floodea el visor) — para diagnosticar a futuro cosas como la re-escalada en un turno ambiente.
    try:
        emit_turn = getattr(__import__("voice.observer", fromlist=["turn_detail"]), "turn_detail")
        emit_turn(system=system, window=_dialog.prune_window(brain._window)[-motor._WINDOW_MAX:], tools=_turn_tools,
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

    # V2-851 F5 — the errands the close launches (the irreversible-order backstop, the commission, the rest of the
    # sentence, his spec to its sheet, our own question kept) live in `nucleo/turn/pipeline_errands.py`.
    _blk = await _errands.launch_the_errands(
        motor=motor, send=send, speech=speech, emit=emit, brain=brain, _brief=_brief, _op_text=_op_text,
        _escalate_mod=_escalate_mod, _prev_pending=_prev_pending, _router=_router, _did_act=_did_act,
        _acted_elsewhere=_acted_elsewhere, acted=acted, confirm_state=confirm_state, data_done=data_done,
        escalate_req=escalate_req, spoken_text=spoken_text, worker_acted=worker_acted,
    )
    _out = {}
    return _out


def _with_usage(extra: dict, spec) -> dict:
    """V2-837 — the reply's fields, completed IN PLACE with the ONE usage shape every model call carries
    (`observability/usage.py`): `provider`, `cached_tokens`, `reply_chars`, `ms`, `outcome`. What the reply already
    says is never overwritten. Returns the same dict, so the verdict read after the emit sees them too."""
    try:
        from observability import usage as _usage
        fin = str(extra.get("finish_reason") or "")
        u = _usage.shape(model=spec.model, provider=spec.provider, prompt_tokens=extra.get("prompt_tokens"),
                         completion_tokens=extra.get("completion_tokens"),
                         cached_tokens=extra.get("prompt_cache_hit_tokens"), prompt_chars=extra.get("prompt_chars"),
                         reply_chars=extra.get("completion_chars"), ms=extra.get("gen_ms") or extra.get("fast_ms"),
                         ttft_ms=extra.get("ttft_ms"), finish_reason=fin,
                         outcome="truncated" if fin == "length" else "ok")
        extra.update({k: v for k, v in u.items() if extra.get(k) is None})
    except Exception as e:  # noqa: BLE001 — observability never breaks a turn
        logger.debug(f"turn_after._with_usage: {e!r}")
        pass
    return extra
