"""The voice turn ADMITTED: the turn brief (one Jev trip), the memory heart, the dialog window seeded once, the
input clamp, the operator's own words, and the system notes composed behind them (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no behaviour change. Every name the block
read from the provider module is read through it (`_p.<name>`), so a patch on the provider still governs it.
`admit_the_turn` takes the turn's locals it read as keyword arguments and returns the ones the rest of
`_run_inner` reads, only when bound.
"""
from __future__ import annotations

from voice.engine.llm.providers import nucleo as _p


async def admit_the_turn(*, attention, brain, emit, first_turn, text) -> dict:
    from nucleo.flash import turn_brief as _turn_brief
    _brief = canvas_h = _turn_brief.ask_for_turn(
        text, running_goals=_p._show_target._running_goals(),
        last_reply=getattr(brain, "_last_reply", "") or "",
        turn_id=f"{id(brain):x}-{getattr(brain, '_acc_gen', 0)}")

    # V2-013: el "corazón" (agente de memoria) clasifica en background lo que dijo el operador y, si es
    # perfil (nombre/ubicación/trato/hardware/coche) o deseo durable, lo lleva a `state`/`long` sin
    # bloquear el turno. Fire-and-forget: regex µs + escritura por la cola async → cero coste en TTFB.
    try:
        from nucleo import memory_agent as _mem_agent
        _p.asyncio.create_task(_mem_agent.ingest_utterance(text, role="operator"))
    except Exception:
        pass

    # CIRCUITO DE CORTO PLAZO (B, 2026-07-14): la ventana de diálogo vive en RAM y arranca VACÍA en cada
    # instancia del brain (reinicio/reconexión) → el FlashBrain perdía "de qué hablábamos". La SEMBRAMOS una
    # sola vez desde el buffer conversacional persistente (`memory.recent_window`, lectura directa µs, sin LLM
    # ni retriever) → el PRIMER turno tras reconectar ya está situado. Cero coste de tokens en régimen normal
    # (la ventana ya está capada a _WINDOW_MAX). Best-effort.
    if not brain._seeded:
        brain._seeded = True
        if not brain._window:
            try:
                from memory import api as _memory
                _seed = _memory.recent_window(limit=int(_p.os.getenv("ZAELAR_WINDOW_SEED", "6")))
                if _seed:
                    brain._window[:0] = _seed
                    emit("brain", "🌱 ventana sembrada desde memoria", role="system",
                         extra={"turns": len(_seed)})
            except Exception:
                pass

    # LATENCY GUARD + T135: acota lo que ve la capa rápida (turnos-parrafada) PRESERVANDO un comando
    # explícito — nunca truncar a ciegas los últimos N chars (así se perdía el "cierra los widgets").
    _max_in = int(_p.os.getenv("ZAELAR_FAST_MAX_INPUT", "1600"))
    text, _clipped = attention.clamp_input(text, _max_in)
    if _clipped:
        emit("brain", "✂️ input recortado (comando preservado)", text=f"→{_max_in} chars")
    if first_turn:
        text = _p._say().kickoff_prompt   # V2-682 — it impersonates HIM, so it is in HIS language

    # V2-1xx: la petición REAL del operador, capturada ANTES de que se le antepongan notas del sistema —
    # el recall semántico (más abajo) tiene que buscar por ESTO, nunca por el turno completo. Confirmado en
    # vivo (auditoría 2026-08-17): una nota de Telegram pegada delante ("...Near our tp1 we take out
    # 20-30%...") dominaba el vector de la query y enterraba los hechos de familia/coche que SÍ existían en
    # el largo plazo — el modelo respondió sin ningún dato delante y rellenó el hueco inventando uno.
    operator_text = text

    # Notas del sistema (resultados async, subidas de fichero…) — se anteponen al turno para que el
    # FlashBrain las vea como CONTEXTO de esta respuesta; NUNCA como parte de lo que el operador pidió.
    try:
        from voice import brain_notes
        notes = brain_notes.drain()
    except Exception:
        notes = []
    if notes:
        for n in notes:
            emit("brain", "📩 system note → FlashBrain", text=n, role="system")
        # V2-666: his words FIRST, the notes AFTER — see `brain_notes.compose_turn` for the measured turn.
        text = brain_notes.compose_turn(text, notes)
    _out = locals()
    return {k: _out[k] for k in ('_brief', 'canvas_h', 'operator_text', 'text', ) if k in _out}
