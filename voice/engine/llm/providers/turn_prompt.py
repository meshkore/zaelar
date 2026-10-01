"""The voice turn's PROMPT: the model spec for this turn, recall and recent conversation on demand, the system
prompt, the loop nudge and the message list (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no behaviour change. Every name the block
read from the provider module is read through it (`_p.<name>`), so a patch on the provider still governs it.
`compose_the_prompt` takes the turn's locals it read as keyword arguments and returns the ones the rest of
`_run_inner` reads, only when bound.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p


async def compose_the_prompt(*, brain, emit, operator_text, self, text) -> dict:
    from nucleo.flash import dialog as _dialog
    from nucleo.flash import escalate as _escalate_mod
    from nucleo.flash import frontend as _frontend
    from nucleo.flash.fast_client import FastClient, spec_from_config
    from nucleo.flash.prompt import build_flash_system
    from nucleo.flash import router as _router

    # EL SPEC SE RESUELVE POR TURNO, contra la cadena de relevo (V2-094). Antes se cogía el titular fijo de la
    # config, así que un proveedor lento o sin cuota se repetía igual turno tras turno: no había a dónde ir.
    # `pick()` es O(1) contra un dict de cooldowns en memoria — no reprueba la cadena en cada turno — y devuelve
    # el titular mientras esté sano, que es el 99% del tiempo. En self-host la cadena es solo el titular (sin
    # relevo por defecto), así que esto es idéntico al comportamiento anterior. Fail-open duro: cualquier
    # problema resolviendo la cadena y se usa la config, como siempre.
    spec = spec_from_config()
    try:
        from nucleo.flash import provider_chain as _pchain0
        _tier = _pchain0.pick(_pchain0.ROLE_VOICE)
        if _tier and _tier.get("name") not in ("", "titular"):
            spec = _pchain0.spec_for(_tier)
    except Exception as _e_pc:  # noqa: BLE001
        _p.logger.warning(f"provider_chain(voice) no resolvió; sigo con la config: {_e_pc!r}")
    emit("brain", "⚡ Nucleo(flash): prompt", text=text, role="user",
         extra={"engine": spec.provider, "model": spec.model})

    self._phase = "montando el prompt"
    timings: dict = {}
    _t_prompt = _p.time.time()
    # RECALL semántico BAJO DEMANDA y FUERA del event loop (T115+T116): `compose_recall` hace embeddings HTTP
    # a Ollama — meterlo en el loop, cada turno, era la regresión de V2-004. Ahora (a) solo se dispara cuando
    # el turno PIDE recordar algo (`needs_recall`, heurística ligera) — la charla normal ni toca el retriever,
    # así que cierra en ~1s; y (b) cuando se dispara, corre en un hilo (`to_thread`) → el event loop nunca se
    # para. El bloque de estado (nombre/trato/…) sale SIEMPRE del caché (T114); el resto del prompt es de ms.
    from nucleo.flash import prompt as _prompt_mod
    recall_block = ""
    recall_ids: list = []
    timings["recall_fired"] = _prompt_mod.needs_recall(operator_text)
    if timings["recall_fired"]:
        # TIME-BOX del recall (regla dura "nunca lento"): el retriever suele cerrar en ~0.4-1.5s, pero en el
        # turno vivo puede dispararse a 4s+ (recarga del modelo de embedding tras un desalojo por el CORAZÓN
        # qwen2.5:14b, o contención de Metal con STT/TTS). El recall está en el CAMINO CRÍTICO del turno (su
        # bloque alimenta el prompt), así que un pico lo paga el usuario en tiempo real. Lo acotamos: si no
        # cierra dentro del presupuesto, el turno SIGUE SIN el bloque durable — el ESTADO (nombre/misión/
        # conversación reciente) YA va en el prompt desde el caché (µs), así que la degradación es suave, no
        # amnesia total. Presupuesto configurable (ZAELAR_RECALL_BUDGET_MS, def 800). 2026-07-13: bajado de
        # 2000→800 tras medir en la sesión manual que el embedding en frío (desalojo por el CORAZÓN) hacía
        # timeout SIEMPRE a 2000ms → +2s tirados por turno. Con 800ms, caliente entra (round-trip ~50-150ms) y
        # en frío corta rápido (pierde 0.8s, no 2s). El fix DE RAÍZ (residencia de embeddinggemma) va por el
        # workflow de memoria.
        # La guarda vive en `nucleo/turn/recall_budget` desde F1: era la protección que ESTE canal tenía y
        # el de texto no, y una protección que existe en un canal y no en el otro no se distingue de no
        # tenerla — el fallo sale por el canal que nadie recordó.
        from nucleo.turn import recall_budget as _recall
        recall_block, recall_ids = await _recall.compose(operator_text, timings)
    # 2º PASE DE CORTO PLAZO (C, 2026-07-14): si el turno referencia la interacción RECIENTE ("de qué
    # hablábamos", "lo que te dije antes", "repite eso"), inyectamos el buffer conversacional AMPLIADO
    # (verbatim, más turnos que la ventana normal). Lectura DIRECTA µs, pero la corremos igualmente en un
    # hilo por consistencia con V2-011 (nunca I/O de memoria en el event loop). El prompt por defecto NO lo
    # lleva → cero tokens extra en charla normal; solo se carga bajo demanda.
    recent_block = ""
    timings["recent_fired"] = _prompt_mod.needs_recent(text)
    if timings["recent_fired"]:
        try:
            recent_block = await _p.asyncio.wait_for(
                _p.asyncio.to_thread(_prompt_mod.compose_recent_block), timeout=0.5)
        except Exception:
            recent_block = ""
    # `turn_text` (V2-085): la frase del operador entra en el build para que la SELECCIÓN PROGRESIVA de widgets
    # promocione al top-K el que él nombra. NO clasifica la intención (invariante: sin tablas de verbos), solo
    # recupera candidatos — así el bloque de widgets es O(K) aunque el catálogo tenga miles.
    system, _used_ids = build_flash_system(
        directive=brain._directive, recall_block=recall_block, recent_block=recent_block, timings=timings,
        turn_text=text)
    # BREAK-LOOP (V2-032): si el cerebro llevaba ≥2 respuestas casi idénticas, añade una instrucción que le
    # OBLIGA a cambiar de estrategia — corta el bucle de repetición/negación (bloqueante #1 del informe).
    _nudge = _dialog.loop_nudge(brain._window)
    if _nudge:
        system += _nudge
        emit("brain", "🔁 break-loop: nudge anti-repetición inyectado", role="system")
    timings["prompt_ms"] = round((_p.time.time() - _t_prompt) * 1000, 1)
    emit("timing", "⏱ turn breakdown (prompt build)", extra=timings)
    self._phase = "eligiendo qué hacer"

    # OBSERVABILIDAD DE MEMORIA (V2-014 Task 2): una fila por CAPA leída este turno, con módulo=memory,
    # capa (state/short/slow), la petición y el resultado (nº de tarjetas/chars) + su tiempo. Alimenta la
    # columna ◷ de logs; las tarjetas del mapa las sigue iluminando el pulso `memory.query`/`memory.updated`.
    try:
        from nucleo.flash import memory_cache as _mc
        ms = _mc.stats()
        emit("memory", "estado", role="system",
             text=(f"perfil del operador → {ms.get('state_fields', 0)} campos" if ms.get("has_state")
                   else "perfil del operador → vacío (sin poblar)"),
             extra={"layer": "state", "mem_ms": timings.get("mem_state_ms")})
        emit("memory", "corto", role="system",
             text=f"working set entero → {ms.get('short_count', 0)} tarjetas · {ms.get('short_chars', 0)} chars",
             extra={"layer": "short", "mem_ms": timings.get("mem_state_ms")})
        if timings.get("recall_fired"):
            emit("memory", "recall", role="system",
                 text=f"«{text[:60]}» → {len(recall_ids)} tarjetas del largo plazo",
                 extra={"layer": "slow", "mem_ms": timings.get("mem_query_ms")})
    except Exception:
        pass
    messages = [{"role": "system", "content": system}]
    _dialog.drain_spoken(brain._window)      # what we said on our own since the last turn (a list's end, a report)
    messages += _dialog.prune_window(brain._window)[-_p._WINDOW_MAX:]   # colapsa turnos gemelos (anti-degeneración)
    messages.append({"role": "user", "content": text})
    _out = locals()
    return {k: _out[k] for k in ('FastClient', '_dialog', '_escalate_mod', '_frontend', '_prompt_mod', '_router', 'messages', 'spec', 'system', 'timings') if k in _out}
