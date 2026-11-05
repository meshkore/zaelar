"""The turn's ADMISSION — the brief, the memory heart, the window seed, the clamp and his words (V2-851 F5: stage 2 of
`nucleo/turn/pipeline`).

Moved out of `voice/engine/llm/providers/turn_admit.py` with no change of behaviour, less the notes mailbox F5 removed.
Names the channel owns are read through `motor` (the channel's module, handed in): a patch on the provider still
governs them, and nothing here imports the motor.
"""
from __future__ import annotations


async def admit_the_turn(*, motor, attention, brain, emit, first_turn, text) -> dict:
    from nucleo.turn import brief as _turn_brief
    from nucleo.input import stt as _acc
    # V2-820 T-06 — the verdict judges what the model answers: a turn his own barge-in cut before its first word is
    # still in the window, so it is part of THIS turn's sentence for the brief too (`accumulator.whole_turn`).
    _judged = _acc.whole_turn(brain, text)
    if _judged != (text or "").strip():
        emit("brain", "🧩 el turno cortado sin respuesta entra en el veredicto", text=_judged[:160], role="system",
             extra={"cat": "flash", "tail": (text or "")[:80]})
        from nucleo.turn import turn_marks
        from voice import trace as _trace
        turn_marks.cut(_trace.current(), _judged, text)   # V2-844: an errand named by the tail is about the whole
    _brief = canvas_h = _turn_brief.ask_for_turn(
        _judged, running_goals=motor._show_target._running_goals(),
        last_reply=getattr(brain, "_last_reply", "") or "",
        turn_id=f"{id(brain):x}-{getattr(brain, '_acc_gen', 0)}")
    _turn_brief.remember_for_the_turn(_brief)    # readers no caller hands it to (an unnamed close) find it by trace
    from nucleo.turn import flow_of as _flow
    _flow.begin(_judged, brief=_brief)    # V2-844 F2: the turn's route, beside its model call; awaited before acting

    # V2-013: the memory agent files what he said in the background (fire-and-forget, zero cost to the first byte).
    # V2-802: the CHANNEL travels with it — a typed/pasted line is read as written, a document whole.
    try:
        from nucleo import memory_agent as _mem_agent
        _ch = "typed" if attention.typed_line(text) else "voice"
        motor.asyncio.create_task(_mem_agent.ingest_utterance(text, role="operator", channel=_ch))
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
                _seed = _memory.recent_window(limit=int(motor.os.getenv("ZAELAR_WINDOW_SEED", "6")))
                if _seed:
                    brain._window[:0] = _seed
                    emit("brain", "🌱 ventana sembrada desde memoria", role="system",
                         extra={"turns": len(_seed)})
            except Exception:
                pass

    # LATENCY GUARD + T135: acota lo que ve la capa rápida (turnos-parrafada) PRESERVANDO un comando
    # explícito — nunca truncar a ciegas los últimos N chars (así se perdía el "cierra los widgets").
    _max_in = int(motor.os.getenv("ZAELAR_FAST_MAX_INPUT", "1600"))
    text, _clipped = attention.clamp_input(text, _max_in)
    if _clipped:
        emit("brain", "✂️ input recortado (comando preservado)", text=f"→{_max_in} chars")
    if first_turn:
        text = motor._say().kickoff_prompt   # V2-682 — it impersonates HIM, so it is in HIS language

    # V2-1xx: la petición REAL del operador, capturada ANTES de que se le antepongan notas del sistema —
    # el recall semántico (más abajo) tiene que buscar por ESTO, nunca por el turno completo. Confirmado en
    # vivo (auditoría 2026-08-17): una nota de Telegram pegada delante ("...Near our tp1 we take out
    # 20-30%...") dominaba el vector de la query y enterraba los hechos de familia/coche que SÍ existían en
    # el largo plazo — el modelo respondió sin ningún dato delante y rellenó el hueco inventando uno.
    operator_text = text

    # The system notes mailbox (`brain_notes`) that glued pending [SISTEMA] lines under his words went in V2-851 F5:
    # a task's news is its task's event, a notice is the out-of-turn mouth's, and the turn reads his words alone.
    _out = locals()
    return {k: _out[k] for k in ('_brief', 'canvas_h', 'operator_text', 'text', ) if k in _out}
