"""The text channel BEFORE the model answers: memory ingest, the composed prompt and the turn brief, then the
model spec, the relay chain and the tool set the stream will offer (V2-778 F1, 2026-10-01).

Moved out of `nucleo/flash/probe.py::run_turn` with no behaviour change. Every name the blocks read from `probe` is
read through the module (`_probe.<name>`), so a patch on `probe` still governs them.
"""
from __future__ import annotations

from nucleo.flash import probe as _probe


async def compose_the_turn(*, build_flash_system, compose_recent_block, dialog, ingest, lists, needs_recall, needs_recent, sess, sid, text) -> dict:
    t0 = _probe.time.time()
    timings: dict = {}

    # (a) INGESTA a memoria como el turno real (el CORAZÓN clasifica en background) — así el probe reproduce la
    # polución/actualización de estado que denuncia el informe. Desactivable para charla aislada.
    # ESPEJO del provider (nucleo.py:205, impl PARALELA): fire-and-forget vía create_task, NUNCA await directo —
    # ingest_utterance llama al CORAZÓN (LLM síncrono, cientos de ms a varios s según el proveedor) y un await aquí
    # bloqueaba el turno ENTERO del probe hasta que esa clasificación terminaba (bug real 2026-07-22: el canal
    # pensado para iterar RÁPIDO se volvía el más LENTO de los tres, con ingest=True por defecto).
    if ingest:
        try:
            from nucleo import memory_agent as _mem
            _probe.asyncio.create_task(_mem.ingest_utterance(text, role="operator"))
        except Exception:
            pass

    # V2-1xx: la petición REAL, ANTES de anteponer notas del sistema — ESPEJO del mismo fix en el provider de
    # voz (nucleo.py). El recall busca por esto, nunca por el turno con la nota pegada delante.
    operator_text = text
    try:
        from nucleo import request_row as _rq
        _rq.begin(operator_text, parent=_rq.step_parent(sid), origin="chat")     # V2-776 M1
    except Exception:  # noqa: BLE001
        pass

    # JEV CANVAS VERDICT (T-jev-show-close, ESPEJO del provider): una pregunta Choice barata
    # (show/close/neither) en su propio hilo mientras se monta el prompt y corre el modelo, lista en los
    # guardas de canvas. Consultiva: un "close" seguro licencia un [[close]] que la gramática no ve;
    # lo demás mantiene el camino de hoy. Nunca rompe el turno (None = solo gramática).
    # V2-770 — the WHOLE turn brief, as the voice provider fires it (`_brief = canvas_h = ask_for_turn`): it
    # carries the canvas verb too, and without it this channel had no verdict about WHICH action of an open
    # card was meant, so what it measured was a product voice does not run.
    canvas_h = _tbrief = None
    try:
        from nucleo.flash import turn_brief as _tb_probe
        canvas_h = _tbrief = _tb_probe.ask_for_turn(operator_text)
    except Exception:
        canvas_h = _tbrief = None
    if canvas_h is None:
        try:
            from nucleo.flash import show_target as _st_cnv
            canvas_h = _st_cnv.ask_canvas_async(operator_text)
        except Exception:
            canvas_h = None

    # (a2) DRENA brain_notes como el provider (paridad voz/probe, V2-053): las notas [SISTEMA] pendientes
    # (SlowBrain, proactive, Susurro repair_say) se anteponen al turno — sin esto el canal de prueba no podía
    # verificar el circuito nota→respuesta y las notas se quedaban esperando a un turno de VOZ.
    try:
        from voice import brain_notes as _bn
        from voice.observer import emit as _emit_note
        _notes = _bn.drain() if lists else []    # V2-771: a list step never eats HIS notes (see runner)
        if _notes:
            for _n in _notes:
                _emit_note("brain", "📩 system note → FlashBrain (probe)", text=_n, role="system")
            text = "\n".join(_notes) + "\n\n" + text
    except Exception:
        pass

    # (b) PROMPT real: estado+memoria+recall (bajo demanda) + 2º pase de CORTO (contexto reciente ampliado si el
    #     turno lo referencia) + BREAK-LOOP si el asistente se estaba repitiendo.
    # El recall DURABLE se compone FUERA del event loop y con presupuesto (`nucleo/turn/recall_budget`), igual
    # que en la voz. Antes se pasaba `recall_query=`, que es la ruta de COMPATIBILIDAD PARA TESTS —lo dice el
    # docstring de `build_flash_system`— y compone en línea: con la memoria lenta (medido el 2026-08-23 durante
    # una descarga de 1,1 GB) bloqueaba el proceso ENTERO y la tanda moría como «INFRA: timed out», sin nombrar
    # a la memoria por ningún sitio. Pasado el presupuesto el turno sigue SIN recall durable, que es peor
    # respuesta y no un agente muerto.
    from nucleo.turn import recall_budget as _recall
    recall_block, _rc_ids = await _recall.compose(operator_text if needs_recall(operator_text) else "", timings)
    recent_block = compose_recent_block() if needs_recent(text) else ""
    timings["recent_fired"] = bool(recent_block)
    system, _used = build_flash_system(directive=sess.directive, recall_block=recall_block,
                                       recent_block=recent_block, timings=timings, turn_text=text)
    nudge = dialog.loop_nudge(sess.window)
    if nudge:
        system += nudge

    messages = [{"role": "system", "content": system}]
    # V2-778 F2-21 — what the agent said out loud is part of THIS conversation too (the voice turn does the same)
    dialog.drain_spoken(sess.window, channel=f"text:{id(sess)}")
    messages += dialog.prune_window(sess.window)[-_probe._WINDOW_MAX:]
    messages.append({"role": "user", "content": text})
    # The prompt for THIS turn is now assembled from the window as it was, so the line can go in without
    # appearing twice — and from here on every exit path, including the ones added later, keeps it.
    dialog.remember_what_was_said(sess, text, _probe._WINDOW_MAX)

    # (c) captura de tool calls y tags (en vez de ejecutarlos)
    tool_calls: list[dict] = []
    tags: list[dict] = []
    _out = locals()
    return {k: _out[k] for k in ('_tbrief', 'canvas_h', 'messages', 'operator_text', 'system', 't0', 'tags', 'text', 'timings', 'tool_calls', ) if k in _out}


async def prepare_the_stream(*, _router, model, spec_from_config) -> dict:
    buf = ""
    raw = ""
    spec = spec_from_config()
    # V2-307 — si el titular fijado por config está en COOLDOWN (acaba de fallar de verdad: un cooldown solo
    # existe porque `note_failure`/`note_stall` anotaron un fallo real), el turno ARRANCA ya en el escalón sano
    # que elegiría la cadena. Sin esto, cada turno quemaba un 402 en el titular seco antes de poder relevar —
    # medido a las 03:13-03:15 (2026-08-25): cuatro turnos mudos con el broker con fondos esperando al lado.
    # Con el titular sano (lo normal), esto no toca nada: el pin de config sigue mandando.
    try:
        from nucleo.flash import provider_chain as _pc0
        from nucleo.flash import provider_failure as _pf0
        _t0 = _pf0.tier_for(spec, _pc0.ROLE_VOICE)
        if _t0 is not None and not _pc0.tier_available(_t0):
            _n0 = _pc0.pick(_pc0.ROLE_VOICE)
            if _n0 and _n0.get("name") != _t0.get("name"):
                spec = _pc0.spec_for(_n0)
    except Exception:
        pass
    if model:
        import dataclasses
        spec = dataclasses.replace(spec, model=model)   # A/B de modelos: mismo proveedor/base/key, otro modelo
    llm_metrics: dict = {}   # totalizadores de tamaño/tokens/latencia (observabilidad, FASE 0) — igual que la voz
    _ttft = None
    # set CONTEXTUAL de tools, igual que la voz (V2-035): situacionales fuera si no aplican
    _cpend = _apend = False
    try:
        from widgets import confirm as _cf
        _cpend = bool(_cf.pending())
    except Exception:
        pass
    try:
        from widgets.navegador import tasks as _nt
        _apend = bool(_nt.login_waiting_id())
    except Exception:
        pass
    # V2-038: mismas señales que la voz (impl PARALELA — cablear en AMBOS): workers vivos / ask pendiente.
    _hw = _akp = False
    try:
        from nucleo import dispatch as _disp_p, worker_api as _wapi_p
        _hw = _disp_p.has_active()
        _akp = _wapi_p.has_pending_ask()
    except Exception:
        pass
    # V2-086: espejo de la voz (impl PARALELA — cablear en AMBOS). El gate por widget desapareció con el propio
    # widget: las tools de cluster se ofrecen siempre y la protección es el confirm Sí/No determinista.
    try:
        from connectors import meshkore as _mk_p
        _cl_conn_p = any(c.get("connected") for c in _mk_p.get_manager().clusters())
    except Exception:
        _cl_conn_p = False
    _turn_tools = _router.tools(_router.tool_context(confirm_pending=_cpend, auth_pending=_apend,
                                                     has_workers=_hw, ask_pending=_akp,
                                                     cluster_widget_open=True, cluster_connected=_cl_conn_p))
    llm_metrics["n_tools_offered"] = len(_turn_tools)
    # UN FALLO DE PROVEEDOR SE DICE, Y ADEMÁS SE RELEVA — ESTE MISMO TURNO (V2-252). Reportarlo ya se hacía
    # (2026-08-15); relevar, no: el turno moría con un escalón sano esperando al lado. Medido por el arnés el
    # 2026-08-21 y es lo que le tuvo OCHO HORAS sin poder medir — con la cadena real sembrada, un turno devolvía
    # `{"ok":false,"error":"modelo: 402 Insufficient Balance"}` en el MISMO SEGUNDO en que el log decía
    # «`deepseek-directo` SIN SALDO → relevo a `aimlapi-failover`». La voz relevaba, i18n relevaba, el texto no.
    #
    # Mismo patrón que el canal de CLUSTER, que lleva haciéndolo desde 2026-08-03 (`connectors/meshkore/brain.py`):
    # un intento, un relevo, un reintento — y no más, para que un proveedor roto no se convierta en un bucle.
    #
    # SOLO se reintenta si el turno no había dicho NADA todavía. Con un 402 el stream muere antes del primer
    # delta, que es el caso real; pero si ya había salido texto o una tool, repetir el turno lo diría dos veces.
    _relay_done = False
    _out = locals()
    return {k: _out[k] for k in ('_akp', '_hw', '_relay_done', '_ttft', '_turn_tools', 'buf', 'llm_metrics', 'raw', 'spec', ) if k in _out}
