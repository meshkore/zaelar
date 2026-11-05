"""The turn's GATE — attention, before anything reads his words (V2-851 F5: stage 1 of `nucleo/turn/pipeline`).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no change of behaviour: the hard interrupt, the
echo, the closed microphone, the missing language, the attention judge, the fragment guard, the fast lane, the phrase
accumulator and the vault. `open_the_turn` returns the turn's opening state, or None when the turn ends here (a lane
answered it, or it was never his). The motor's own seams (the chat context, the fast lane, the accumulator's notices,
the flow lifecycle) are reached through `motor` — the channel's module, handed in — so nothing here imports the motor
(the dependency-direction ratchet, 7.32).
"""
from __future__ import annotations

import os
import time

from loguru import logger

from nucleo.turn import mouth as _mouth


async def open_the_turn(self, motor) -> dict | None:
    """Stage 1 of one turn. `self` is the channel's stream (its `_llm`, `_chat_ctx`, `_out`, `_superseded`)."""
    brain = self._llm
    try:
        from voice.observer import emit
    except Exception:
        emit = lambda *a, **k: None

    text = motor._last_user_text(self._chat_ctx)
    if not text:
        emit("brain", "⚠️ Nucleo triggered but no user text in context")
        return None

    # PRE-TURN CLOCK (2026-09-01). The LENTO verdict's `t0` starts AFTER the attention judge, the fragment
    # accumulator and the recall wait, so our own serial pre-work was invisible and its cost got blamed on the
    # provider's TTFT ("razonamiento oculto o cola"). These three numbers make the pre-turn segment visible in
    # `_reply_extra`/turn_perf WITHOUT moving `t0`: `total_ms` keeps its meaning (provider_chain.note_slow and
    # SLOW_MS are calibrated on it, and relaying a provider over OUR preflight would punish the wrong party).
    _t_entry = time.time()
    _gate_ms = 0.0
    _acc_ms = 0.0
    _amap_ms = 0.0

    # GATE DE ATENCIÓN (V2-015): el micro está SIEMPRE abierto — un turno que no va DIRIGIDO a zaelar no
    # produce acción ni respuesta (solo se registra como `ambient`, visible en /debug). El kickoff
    # ("I just connected") y el chat/paste (marcados `note_directed()` en agent.py) sí van dirigidos.
    from voice import attention, mic_input
    first_turn = "I just connected" in text

    # TRAZABILIDAD (V2-044): cada frase del operador nace con un trace id — ANTES del gate, así los descartes
    # (ambient/eco/interrupción dura) también quedan encadenados a su frase y son evaluables. Todo lo que este
    # turno derive (tools, tags, rails, escaladas, memoria) hereda el id por ContextVar (create_task/to_thread).
    # Una continuación de la MISMA frase (V2-096 addenda, ver `_begin_or_adopt_trace`) ADOPTA el trace de la
    # cadena en vez de abrir uno nuevo por trozo.
    try:
        motor._begin_or_adopt_trace(brain, text, first_turn)
    except Exception:
        pass
    _mouth.open_for()   # V2-851 F5: a door that speaks while this turn is live says it through the turn's mouth
    # What this turn ACTUALLY did, for the flow-merge decision at the end (V2-123, `_merge_target`). Lives on
    # `brain` because `_close_flow_now` only receives that object — same ownership (and same overlapping-turn
    # caveat under preemptive generation) as `_acc_trace_id`/`_escalated_trace_id` right next to it.
    brain._turn_tools = set()
    brain._turn_calls = []   # the model's raw calls this turn, for the forensic capture (V2-776 F)

    # T136 — interrupción DURA: "cierra los widgets / para / silencio" se atiende SIEMPRE (salta el gate)
    # y se ejecuta de forma DETERMINISTA, nunca enterrada en un turno gigante. Fue el bug real (el `close`
    # quedó fuera del recorte de un turno de 14k chars). La decisión entera —worker vs música vs canvas, y
    # si cerrar era TODO lo que se dijo (V2-688)— vive en `nucleo/flash/hard_turn.py`: son cuatro preguntas
    # que se confunden entre sí, y aquí solo queda lo que este turno tiene que hacer con la respuesta.
    if not first_turn:
        hard = attention.hard_interrupt(text)
        if hard:
            from nucleo.flash import hard_turn as _hard_turn
            _cont = await _hard_turn.handle(text, hard, emit, brain)
            if _cont is None:
                motor._release_acc_trace_if_fresh(brain)      # ver docstring — este turno no llega a offer()
                return None
            text = _cont

    # (V2-726 A2) The turn brief is NOT fired here any more — this line runs before echo
    # suppression and before the accumulator, so it classified a fragment. Search for
    # «JEV TURN BRIEF» below; the why is in `nucleo/turn/brief.py`'s docstring.
    _brief = canvas_h = None

    # (V2-726 A5) The Jev ROUTE pre-choice was fired here and is gone; its epitaph, with the
    # measurement that retired the question, is at the end of `nucleo/flash/tool_selection.py`.

    # SUPRESIÓN DE ECO (FASE 2, 2026-07-14): con el micro SIEMPRE abierto y sin AEC perfecto, el mic capta el
    # TTS de zaelar y el STT lo transcribe como si fuera el operador → zaelar "se responde a sí mismo" (las
    # respuestas ZOMBIE / la frase del tiempo re-emitida del test). Si el turno se PARECE MUCHO a lo que zaelar
    # ACABA de decir y cae dentro de la ventana de eco, lo descartamos (determinista, no depende del LLM).
    # Observabilidad: evento `ambient` con reason=echo → visible en /debug para medir cuánto eco hay.
    # V2-038 §v3·N: si un Brain Worker ESPERA respuesta, el turno inmediato (a menudo monosilábico: "enduro")
    # queda EXENTO de la supresión de eco — si no, "sí"/una palabra contenida en lo último dicho se descartaría
    # y la respuesta al worker moriría.
    _ask_waiting = False
    if not first_turn:
        try:
            from nucleo.cli import worker_api as _wapi0
            _ask_waiting = _wapi0.has_pending_ask()
        except Exception:
            _ask_waiting = False
    if not first_turn and brain._last_spoken and not _ask_waiting:
        _echo_win = float(os.getenv("ZAELAR_ECHO_WINDOW_S", "12"))
        _gap = time.time() - brain._last_spoke_at
        if _gap < _echo_win:
            try:
                from nucleo.flash import dialog as _dlg
                _is_echo = _dlg.similar(text, brain._last_spoken, thr=0.82)
            except Exception:
                _is_echo = False
            if _is_echo:
                emit("ambient", "🔇 eco descartado (zaelar se oyó a sí mismo)", text=text[:160], role="user",
                     extra={"reason": "echo", "gap_s": round(_gap, 1), "cat": "flash"})
                motor._release_acc_trace_if_fresh(brain)          # ver docstring — este turno no llega a offer()
                return None

    # T134 — un turno no dirigido no se atiende (ni siquiera drena notas: se preservan para el próximo).
    # El kickoff (saludo de zaelar) NO abre la ventana a propósito: es zaelar quien habla, no el operador
    # dirigiéndose a él — así, si la sesión arranca en mitad de una reunión, no hay un hueco inicial en el
    # que la voz ambiente se cuele como dirigida y auto-extienda la ventana. El operador abre la conversación
    # con la wake-word ("zaelar") y a partir de ahí la ventana la mantiene viva (o chat/paste, ya marcados).
    # V2-654 — el micro cerrado manda sobre TODO, y por eso va ANTES del gate: el porqué, en `mic_input`.
    if not first_turn and mic_input.blocks_turn(text):
        motor._release_acc_trace_if_fresh(brain)   # este turno no llega a offer() — ver docstring
        return None
    # V2-765 — no language, no turn. The session should not even exist (the token is refused), so this is
    # the backstop for one that outlived the gate: nothing heard before the picker is used reaches the brain.
    if not first_turn:
        from nucleo import runstate as _rs_lang
        if _rs_lang.language_pending():
            emit("mic", "🌐 turno DESCARTADO — falta elegir el idioma", text=text[:200], role="user",
                 extra={"reason": "language"})
            motor._release_acc_trace_if_fresh(brain)
            return None

    if not first_turn:
        # T134 — un turno no dirigido no se atiende. El bloque entero vive en `attention_turn.judge`
        # (V2-655): qué decide, por qué el juez recibe `_last_reply`, y por qué AMBOS veredictos llevan
        # la ventana («el sonido ambiente no interrumpe para nada los contadores») están escritos allí.
        _directed, text, _gate_ms = await motor._attention_turn.judge(
            text, context=brain._last_reply, emit=emit)
        if not _directed:
            motor._release_acc_trace_if_fresh(brain)   # ver docstring: este turno no llega a offer()
            return None

    # GUARDA DE FRAGMENTOS (2026-08-10). La frase de este turno queda registrada como la utterance EN CURSO. Si
    # mientras trabajamos llega una versión MÁS LARGA de la misma frase (el operador seguía hablando), este turno
    # es un fragmento viejo y hay que abandonarlo ANTES de gastar modelo o —sobre todo— de disparar una tool.
    # Incidente de la sesión 13:20:50: una sola petición de ferry se partió en 8 transcripciones finales y cada
    # trozo abrió su propio turno; uno de ellos («…de Denia a») llegó a HABLAR, preguntando por el destino que el
    # operador estaba diciendo en ese momento. Un fragmento no debe poder abrir widgets ni lanzar un worker.
    if not first_turn:
        brain._utterance = {"text": text, "at": time.time()}
        self._turn_text = text
        try:
            from nucleo.request import model as _rq
            _rq.begin(text)          # V2-776 M1 — the words the row of this request will carry
        except Exception:  # noqa: BLE001
            pass

    # ACTION MAP (V2-539) + PRESENCE knock (V2-640) + SMALL TALK (V2-674) skip the model: see
    # fast_lane.py (mirrors in probe.py).
    try:
        _fast_lane = motor._fast_lane_mod()
        if (await _fast_lane.task_list(brain, text, emit, first_turn=first_turn, window_max=motor._WINDOW_MAX,
                                       say=self._out)
                or await _fast_lane.handled(brain, text, emit, first_turn=first_turn,
                                     t_entry=_t_entry, window_max=motor._WINDOW_MAX)
                or await _fast_lane.presence(brain, text, emit, first_turn=first_turn,
                                             window_max=motor._WINDOW_MAX)
                or await _fast_lane.wall_tab(brain, text, emit, first_turn=first_turn,
                                             window_max=motor._WINDOW_MAX)
                or await _fast_lane.small_talk(brain, text, emit, first_turn=first_turn,
                                               window_max=motor._WINDOW_MAX, ask_waiting=_ask_waiting)):
            motor._release_acc_trace_if_fresh(brain)   # same situation as the hard interrupt: no offer()
            return None
    except Exception as _e_am:  # noqa: BLE001
        logger.warning(f"fast lane skipped (fail-open): {_e_am!r}")

    # ACUMULADOR DE FRASE PARTIDA (V2-096). Hermano de la guarda de arriba, para el caso que ella NO cubre: la
    # guarda mata un fragmento cuando ya llegó su continuación; esto decide qué hacer cuando la continuación
    # AÚN NO ha llegado. Antes se actuaba sobre el trozo.
    #
    # V2-095 lo intentaba RETRASANDO el turno, y eso es un tiempo fijo: medido sobre 372 pausas reales, el
    # `max_delay` de 2,2 s solo cubría el 48,7% (p50 2,3 s · p90 4,9 s · max 19,5 s). Acumular saca el reloj de
    # la ecuación — la pausa puede durar lo que quiera, porque lo que se juzga son los trozos JUNTOS.
    #
    # Va AQUÍ, y el sitio es la mitad del arreglo: por delante ya pasaron la interrupción DURA (una orden de
    # parar nunca se retiene) y el gate de atención; por detrás viene `ingest_utterance`, así que un trozo a
    # medias tampoco entra en la MEMORIA. Un fragmento no habla, no actúa y no se recuerda.
    # V2-778 F1 — the phrase accumulator (a fragment waits for the rest) lives in
    # `voice/engine/llm/providers/turn_fragment.py`.
    _blk = await motor._turn_fragment.hold_a_fragment(
        brain=brain,
        emit=emit,
        first_turn=first_turn,
        text=text,
    )
    if _blk.get('__return__'):
        return None
    if '_acc_ms' in _blk:
        _acc_ms = _blk['_acc_ms']
    if 'text' in _blk:
        text = _blk['text']

    # The VAULT before anything reads his words (refactor2710-01) — `vault_intercept.vault_first`.
    _vault_done, text = await motor._vault_first(text, first_turn, emit, self._event_ch, brain)
    if _vault_done:
        return None

    return {"brain": brain, "emit": emit, "text": text, "first_turn": first_turn, "attention": attention,
            "_t_entry": _t_entry, "_gate_ms": _gate_ms, "_acc_ms": _acc_ms, "_amap_ms": _amap_ms,
            "_ask_waiting": _ask_waiting, "_brief": _brief, "canvas_h": canvas_h}
