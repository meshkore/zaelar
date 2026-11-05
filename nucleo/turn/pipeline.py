"""ONE pipeline for every turn — attention → admission → prompt → the model → its acts → the reply → the record
(V2-851 F5, V2-826 §3).

It was `voice/engine/llm/providers/nucleo.py::_run_inner` (972 lines with its helpers in `voice/`): the voice provider
and the typed channel (`voice/typed_turn.py` ← `nucleo/cli/turn.py`) both run THIS function now; the provider is a thin
adapter. Each stage is a module of its own, read in order:

  · `pipeline_gate`    — hard interrupt, echo, microphone, language, attention, fragment, fast lane, accumulator, vault
  · `pipeline_admit`   — the brief (the one Jev trip), the memory heart, the window, the clamp
  · `pipeline_state`   — the turn's mouth (`send`), its tag buffer and its tool rounds (`speak`)
  · `pipeline_stream`  — the ONE model call, its silence deadline, the Hold, the barge-in; an unreadable sentence
  · `pipeline_failure` — the turn the model did not answer
  · the post-stream chain (`nucleo/flash/post_stream`) — the acts the model called, their verdicts, the mouth's lines
  · `pipeline_close`   — the window, the fallbacks, the reply event; `pipeline_errands` — what the close launches

After the main stream no model runs again (target of V2-851 §13: zero re-runs): the second trip, the deliberate second
look, the second passes, the detached follow-up, the write harness and the late catalogue went in F5. A tool the model
called is said by its own round (`speak`), inside the turn. A SURE «escalate» verdict routes the request to its task
before the model is trusted (`route_by_verdict`, CRIT-E27): its inline calls, tags and words do not run.

The channel's own seams — the chat context, the chunk on its stream (`self._out`), the fast lane, the accumulator's
notices, the flow lifecycle, the widget-intent readers, the filler — are reached through `motor`, the channel's module
handed in: a patch on the provider still governs them, and nothing here imports the motor (ratchet 7.32).
"""
from __future__ import annotations

import inspect
import time

from nucleo.flash import follow_up_pass as _fup, post_stream as _post_stream, tool_executor as _tool_executor
from nucleo.turn import pipeline_admit as _turn_admit
from nucleo.turn import pipeline_close as _turn_after
from nucleo.turn import pipeline_failure as _turn_failure
from nucleo.turn import pipeline_gate as _gate
from nucleo.turn import pipeline_state as _state
from nucleo.turn import pipeline_stream as _turn_unclear
from nucleo.turn import route_by_verdict as _route
from widgets import confirm as _wconfirm


def _kw(fn, *scopes: dict) -> dict:
    """The keyword arguments `fn` declares, taken from the turn's scopes (later scopes win)."""
    names = inspect.signature(fn).parameters
    merged: dict = {}
    for s in scopes:
        merged.update(s)
    return {k: merged[k] for k in names if k in merged}


async def run(self, motor) -> None:
    """ONE turn. `self` is the channel's stream (its `_llm`, `_chat_ctx`, `_out`, `_phase`, `_superseded`)."""
    # V2-851 F5 — the gate (interrupt, echo, microphone, language, attention, fragment, fast lane, vault) lives in
    # `nucleo/turn/pipeline_gate.py`.
    g = await _gate.open_the_turn(
        self, motor,
    )
    if g is None:
        return
    brain, emit, text, first_turn, attention = g["brain"], g["emit"], g["text"], g["first_turn"], g["attention"]
    _brief, canvas_h, _ask_waiting = g["_brief"], g["canvas_h"], g["_ask_waiting"]

    # JEV TURN BRIEF (V2-726 F1, moved here by A2): ONE call carrying every question this turn
    # reads AFTER the model — canvas verb, escalate pair, which action of which open card, and
    # what KIND of turn it is (which the filler used to ask on a second socket of its own).
    # HERE because here the sentence is FINAL: past the hard interrupt, past echo suppression,
    # past the accumulator. Not later either — the readers are 2-4 s away and this takes ~800 ms,
    # which is the overlap that makes it free. Assembly, bounds and fail-soft: `turn_brief`.
    # V2-778 F1 — admitting the turn (brief, memory heart, window seed, clamp, his words) lives in
    # `nucleo/turn/pipeline_admit.py`.
    _blk = await _turn_admit.admit_the_turn(
        motor=motor,
        attention=attention,
        brain=brain,
        emit=emit,
        first_turn=first_turn,
        text=text,
    )
    _brief, canvas_h = _blk.get('_brief', _brief), _blk.get('canvas_h', canvas_h)
    operator_text, text = _blk['operator_text'], _blk.get('text', text)

    # V2-778 F1 — the turn's prompt (spec, recall, recent, system, loop nudge, messages) lives in
    # `voice/engine/llm/providers/turn_prompt.py`.
    p = await motor._turn_prompt.compose_the_prompt(
        brain=brain,
        emit=emit,
        operator_text=operator_text,
        self=self,
        text=text,
    )
    FastClient, _dialog, _escalate_mod, _router = p['FastClient'], p['_dialog'], p['_escalate_mod'], p['_router']
    messages, spec = p['messages'], p['spec']

    from voice import speech
    from voice.tag_protocol import strip_tags

    t0 = time.time()
    # FASE 3: foto de CONTENCIÓN al arrancar el LLM del turno (¿estaba el CORAZÓN/embed/rerank ocupando la
    # máquina?). Se adjunta al `reply` → correlacionamos si el TTFT sube bajo carga local. TTFT es CLOUD, así
    # que si sube con carga LOCAL activa, es contención de CPU/event-loop, no de GPU.
    try:
        from voice import observer as _obs
        _busy_at_start = _obs.busy_snapshot()
    except Exception:
        _busy_at_start = {}
    # ¿había una confirmación de borrado en el aire al empezar el turno? Solo entonces interpretamos un
    # "sí/no" suelto como respuesta a ELLA (red determinista, por si el modelo no llama a la tool).
    try:
        had_pending_confirm = bool(_wconfirm.pending())
    except Exception:
        had_pending_confirm = False
    req = _state.the_turn_requests(had_pending_confirm)
    # V2-851 F5 — the turn's mouth, its tag buffer and its tool rounds live in `nucleo/turn/pipeline_state.py`.
    m = _state.open_the_mouth(
        self, motor, brain=brain, attention=attention, first_turn=first_turn, emit=emit,
        FastClient=FastClient, spec=spec, t0=t0, speech=speech, strip_tags=strip_tags,
        typed=attention.typed_line(text),
    )
    send, take, speak, spoken = m.send, m.take, m.speak, m.spoken

    # A PENDING CONFIRMATION is resolved NOW, before any slow work (V2-090): the backstop below runs only after the
    # whole stream, and a barge-in in between lost his «yes» silently (the confirmation stayed pending for good).
    # A CLEAR yes/no is resolved here, deterministically, before the model; an ambiguous one goes to the backstop.
    if not first_turn and had_pending_confirm:
        try:
            _verdict_early = _wconfirm.answers_pending(text, _brief)
        except Exception:
            _verdict_early = None
        if _verdict_early:
            if motor._resolve_and_end_the_turn(_verdict_early, text):   # p129 C3: a judged «no» serves the rest
                # V2-743 — a yes is answered with a START, never a completion: «Done.» was once said 7 s before
                # the op settled; the outcome arrives from `op_receipt`, this line only says it has begun.
                _ack_early = (motor._say().work_started if _verdict_early == "yes" else motor._say().confirm_cancelled)
                send(speech.sanitize(_ack_early, drop_metadata=False))
                return

    # V2-029: escaladas YA en vuelo al EMPEZAR el turno — para (a) deduplicar si el operador insiste con la
    # MISMA petición mientras el SlowBrain trabaja (no abrir tareas ni entregas duplicadas) y (b) variar el
    # filler ("sigo con ello" en vez de repetir el mismo "dame un momento" turno a turno).
    # V2-038 §v3·G: la FUENTE DE VERDAD de "qué hay en marcha" es el registro RAM de dispatch (no escalate._tasks).
    try:
        from nucleo import dispatch as _disp0
        _prev_pending = _disp0.pending_summaries()
    except Exception:
        try:
            _prev_pending = _escalate_mod.pending()
        except Exception:
            _prev_pending = []

    # V2-778 F1-10 — the tool executor lives in `nucleo/flash/tool_executor.py`; built here, after the last
    # rebinding of anything it captures (the vault intercept above may redact `text`).
    _seams = {k: getattr(motor, k) for k in (
        "_spawn", "_say", "_resolve_pending_confirm", "_confirm_decide", "_close_target", "_identify",
        "_identify_is_widget", "_identify_system", "_is_meta_widget_question", "_norm_nfkd", "_show_guard_target",
        "_show_target_instance", "with_also_named")}
    _turn = {"self": self, "brain": brain, "emit": emit, "text": text, "operator_text": operator_text,
             "_brief": _brief, "canvas_h": canvas_h, "_frontend": p['_frontend'], "_router": _router}
    _tx = _tool_executor.build(**_kw(_tool_executor.build, _seams, req, _turn))
    _apply_widget_data = _tx.apply_widget_data
    # CRIT-E27 (V2-851 F5) — a SURE «escalate» verdict routes the request to its task before the model is trusted:
    # its calls and its inline tags do not run, its words are held unsaid (`route_by_verdict`, the Hold).
    _routing = time.monotonic()
    _on_tool_call = _route.gate_calls(_tx.on_tool_call, brief=_brief, escalate_req=req["escalate_req"],
                                      operator_text=operator_text, emit=emit, t0=_routing, wait=_route.wait_s())
    m.late["tag_emit"] = lambda *a, **k: None if _route.sure_escalate(_brief) else _tx.tag_emit(*a, **k)

    llm_metrics: dict = {}   # totalizadores de tamaño/tokens/latencia del modelo (observabilidad, FASE 0)
    # SET CONTEXTUAL DE TOOLS (V2-035): omite las situacionales que no aplican este turno (confirmar-borrado sin
    # borrado en el aire, login-hecho sin login en curso) → prompt más corto y menos ruido de decisión.
    # V2-778 F1 — the turn's tool set (situational tools, the turn's direction, the budget) lives in
    # `voice/engine/llm/providers/turn_tools.py`.
    tools = await motor._turn_tools_mod.choose_the_tools(
        _router=_router, brain=brain, emit=emit, first_turn=first_turn,
        had_pending_confirm=had_pending_confirm, llm_metrics=llm_metrics, self=self, text=text,
    )
    # NO en el kickoff: el saludo lo inicia zaelar (nadie espera) → un "Pues…" antes de saludar suena raro.
    # Último corte ANTES de pagar el modelo: si la frase ya creció, este fragmento no tiene nada que decir.
    if self._superseded():
        self._death_logged = True
        emit("brain", "🧩 fragmento descartado — la frase seguía", text=text[:200], role="system",
             extra={"cat": "flash", "phase": self._phase, "spent_model": False})
        return

    # LEAD-IN FILLER (V2-529, 2026-08-31 — replaces the say-path `LeadInFiller`, V2-093/V2-114/V2-122):
    # the filler is pre-synthesized AUDIO yielded as the first frames of the reply's OWN speech, by
    # the tts_node wrapper in `voice/engine/pipeline/agent.py`. Here we only ARM it: the wrapper fires
    # only when the model's first token is later than ZAELAR_FILLER_MS (default 1100 ms — a reply within
    # ~a second gets no filler, operator's rule), and a turn that never armed (kickoff, probe, a `say`)
    # can never sound one. A barge-in interrupts the reply speech and the filler dies with it.
    _filler_audio = None
    try:
        _filler_audio = motor._filler_audio_mod()
        if _filler_audio.enabled() and not first_turn:
            _filler_audio.arm(brain, text, messages=messages, brief=_brief)  # V2-640 cover, V2-726 A2 verdict
    except Exception:
        pass
    self._phase = "generando la respuesta"
    # V2-851 F5 — the ONE model call of the turn (pump, silence deadline, Hold, barge-in) lives in
    # `nucleo/turn/pipeline_stream.py`.
    s = await _turn_unclear.stream_the_reply(
        self, motor, FastClient=FastClient, messages=messages, spec=spec, _turn_tools=tools['_turn_tools'],
        _on_tool_call=_on_tool_call, llm_metrics=llm_metrics, _brief=_brief, send=send, take=take,
        _buf_add=m._buf_add, speech=speech, emit=emit, brain=brain, text=text, spoken=spoken, first_ms=m.first_ms,
        t0=t0, _dialog=_dialog, data_done=req['data_done'], _turn_op_tasks=req['_turn_op_tasks'],
        _filler_audio=_filler_audio,
    )
    errored, _hold = s["errored"], s["_hold"]
    if getattr(_hold, "routed", False):
        _route.route(req["escalate_req"], operator_text, emit, why="verdict")   # nothing called: the verdict decides
    # V2-778 F1 — the turn the model did not answer (whose fault, the relay, the line he hears) lives in
    # `nucleo/turn/pipeline_failure.py`.
    _blk = await _turn_failure.say_the_turn_failed(
        emit=emit, err_exc=s["err_exc"], err_text=s["err_text"], errored=errored, llm_metrics=llm_metrics, send=send,
        spec=spec, stalled=s["stalled"], first_turn=first_turn, brain=brain, text=text,
    )
    if _blk.get('__return__'):
        return

    # V2-833 F7/F8 — the brief read the sentence as unreadable and the reflex pass did not act (its words were held
    # unsaid), or the model said so itself with `not_understood`: one line asks him (`turn_unclear`), no model.
    _turn_unclear.say_unread(hold=_hold, marked=getattr(self, "_not_understood", False),
                             errored=errored, window=brain._window, send=send, emit=emit, spoken=spoken)

    # V2-778 F1-10b — the post-stream chain lives in `nucleo/flash/post_stream.py`; it resets and feeds the turn's
    # tag buffer through the mouth's two accessors.
    _scope = {**_seams, **req, **_turn, **tools, "FastClient": FastClient, "_apply_widget_data": _apply_widget_data,
              "_ask_waiting": _ask_waiting, "_cover_work": m._cover_work, "_dialog": _dialog,
              "_filler_audio": _filler_audio, "_prev_pending": _prev_pending, "_prompt_mod": p['_prompt_mod'],
              "_resolve_confirm": _tx.resolve_confirm, "_tag_emit": _tx.tag_emit, "attention": attention,
              "llm_metrics": llm_metrics, "send": send, "speak": speak, "spec": spec, "speech": speech,
              "spoken": spoken, "take": take, "_buf_reset": m._buf_reset, "_buf_add": m._buf_add}
    _ps = await _post_stream.run(**_kw(_post_stream.run, _scope))
    spoken_text, _op_text = _ps["spoken_text"], _ps["_op_text"]
    spoken_text = _fup.flush(_hold, spoken, emit, spoken_text)   # pass 9 C2: deferred words

    # BACKSTOP GENÉRICO — turno MUDO que no hizo NADA (qué cuenta como «hecho algo»: `turn_handled`).
    # V2-778 F1 — the end of the turn (dialog window, reply event, extra escalations) lives in
    # `nucleo/turn/pipeline_close.py`.
    _close = {**_scope, "motor": motor, "_acc_ms": g["_acc_ms"], "_amap_ms": g["_amap_ms"],
              "_busy_at_start": _busy_at_start, "_escalate_mod": _escalate_mod, "_gate_ms": g["_gate_ms"],
              "_op_text": _op_text, "_start_web_auth": _tx.start_web_auth, "_t_entry": g["_t_entry"],
              "first_ms": m.first_ms(), "first_turn": first_turn,
              "spoken_text": spoken_text, "system": p['system'], "t0": t0, "timings": p['timings']}
    await _turn_after.close_the_turn(
        **_kw(_turn_after.close_the_turn, _close),
    )
