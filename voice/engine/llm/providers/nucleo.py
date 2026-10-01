#
# NUCLEO brain (zaelar v2 «Colmena») as a LiveKit LLM provider (EPIC-v2-colmena, V2-004).
#
# FlashBrain (the OWN implementation, `nucleo/flash/`) is plugged into the voice engine through the SAME seam as
# `duo`: LLMStream reads the latest turn from ChatContext, runs FlashBrain, and emits ALREADY CLEANED ChatChunks
# (they pass through strip_tags→side-effects→speech). The engine-agnostic contract is preserved.
#
# Difference from `duo`: there is NO Hermes. Startup memory and context come from the application's own central
# memory (`memory/`, injected into the prompt by `nucleo/flash/prompt.py`). Escalation goes to
# `nucleo/flash/escalate.py` (STUB in V2-004: records + publishes on the bus; the real SlowBrain arrives in
# V2-006/V2-007). Degradation does NOT fall back to Hermes—it speaks a fallback phrase.
#
# Enabled with BRAIN=nucleo (opt-in, alongside duo/hermes; zero regression until the V2-009 cutover).
#
from __future__ import annotations

import asyncio
import os
import time

from loguru import logger
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, llm, utils
from livekit.agents.llm import ChatChunk, ChoiceDelta

from .. import registry
from nucleo.flash.panel_canon import wall_tab_for as _wall_tab_for
from nucleo.flash import (build_decision as _build_decision, canvas_license as _canvas_lic,  # V2-750 grammar only proposes / V2-650 a replay can be an order
                          canvas_visibility as _cvis,                          # V2-723: ONE door to present
                          close_guards as _closeg,                             # V2-635: close needs the words
                          data_ops as _data_ops, escalation_guard as _eguard,  # V2-391 / V2-677
                          direct_action as _direct_action,                     # V2-741: the third rung
                          image_turn as _image_turn,                           # V2-402
                          listing_turn as _lt, show_target as _show_target,    # V2-609: one target decision
                          task_recall as _trecall,                             # V2-728: «lo del piso que te dije»
                          video_turn as _video_turn)                           # V2-556 / V2-457: no cycles
# V2-515 (ratchet): ONE import replaces eight lazy `from widgets import confirm` — confirm.py never imports voice.
from voice import brain_notes as _bnotes          # V2-678: his words, never the composed turn
from widgets import confirm as _wconfirm, lifecycle as _wlifecycle
# The pending-confirmation pair moved to `confirm_gate.py` (2026-09-02 ratchet pass): they needed nothing
# from this file, so the dependency runs one way. Imported back under their own names — every call site
# in this module keeps working unchanged, and so does anything that reads them from here.
from .confirm_gate import _human_confirm_question, _similar_pending, decide as _confirm_decide  # noqa: F401

_WINDOW_MAX = 10
_TAG_TASKS: set = set()


def _say():
    """The language table (V2-682) — ONE home for this file's reads of it (the coupling ratchet counts
    lazy imports: moving a sentence INTO the table must not cost a new one each time)."""  # noqa: D401
    from voice.engine.core import langs as _lg
    return _lg.current_language()


def _last_user_text(chat_ctx) -> str:
    """Last user turn from ChatContext (FlashBrain composes its own window + memory)."""
    try:
        items = list(chat_ctx.items)
    except Exception:
        items = []
    for it in reversed(items):
        if getattr(it, "role", None) != "user":
            continue
        txt = getattr(it, "text_content", None)
        if txt:
            return str(txt).strip()
        content = getattr(it, "content", None)
        if isinstance(content, list):
            return " ".join(c for c in content if isinstance(c, str)).strip()
        return str(content or "").strip()
    return ""


def _turn_budget_ms() -> int:
    """How much SILENCE the model is allowed within a voice turn before it is considered stuck.

    This is not the maximum turn duration: it renews with every speakable chunk (see the streaming loop), so a long
    response is delivered in full. It is the deadline for SOMETHING to begin coming out. 9 s is already a long time
    to speak aloud; the only previous limit was httpx's 60 s network timeout. Hot-adjustable; 0 disables it.
    """
    try:
        v = int(os.getenv("ZAELAR_TURN_QUIET_MS", "9000"))
    except ValueError:
        return 9000
    return v if v > 0 else 10 ** 9


def stream_advancing(metrics: dict, quiet_ms: int, now: float | None = None) -> bool:
    """Is the model stream ADVANCING even when no speakable content is emitted?

    This is the 2026-08-12 fix, prompted by killing three HEALTHY turns in two minutes. `fast_client.stream()` only
    `fast_client.stream()` yields only chunks WITH TEXT: tool-call chunks (dripping arguments, empty `content`) are
    consumed internally and never leave it. Thus a turn whose response is an ACTION —“show me the results”, “close
    that”— looks, from the turn loop, exactly like a hung model. Measured at the 13:49 incident: `ttft=1.50s` (the
    model had answered in a second and a half) with zero speakable characters; the deadline guillotined it at 9 s
    and the operator heard “I’ve gone away for a moment” without ever seeing the results.

    Therefore the deadline checks the stream's HEARTBEAT (`last_chunk_ts`, stamped by the code that sees each chunk),
    not the voice. Without a stamp yet → False: nothing has arrived, so it is genuinely stuck. Pure and deliberately
    free of I/O."""
    last = float((metrics or {}).get("last_chunk_ts") or 0)
    if not last:
        return False
    return ((now if now is not None else time.time()) - last) * 1000.0 < quiet_ms


def _norm_utt(s: str) -> str:
    return " ".join((s or "").lower().split())


def _extends(prev: str, cur: str) -> bool:
    """Is `cur` THE SAME phrase as `prev`, only longer?

    A purely STRUCTURAL, not semantic, signal: STT provides the ACCUMULATED transcription of the current phrase, so
    that a fragment of what the operator is still saying is a PREFIX of the next turn. Detecting it this way needs
    neither verb tables nor language heuristics — it works equally in Spanish, Japanese, or when dictating code.
    """
    p, c = _norm_utt(prev), _norm_utt(cur)
    return bool(p) and len(c) > len(p) and c.startswith(p)


# ── the accumulator's NOTICES — extracted to `providers/acc_notices.py` (ratchet, 2026-09-03, V2-567). The
# historical names stay as ALIASES to the same functions; the voice tests and the call sites below are
# untouched. What does NOT move is `_spawn`: the provider owns its background-task registry.
from voice.engine.llm.providers import acc_notices as _accn
from voice.engine.llm.providers import attention_turn as _attention_turn
from nucleo.flash import harness_turn as _ht   # V2-661: what a turn OWES (shared with the probe)
from nucleo.flash import reminder_guards as _rg   # its canned lines: holding, mute backstop, follow-up
from nucleo.flash import accumulator as _acc_mod   # V2-776 D0: a turn that died unanswered is un-consumed
from nucleo import surfaces as _surfaces_mod   # demo A1 2026-09-28: an errand nobody labelled takes the brief's surface

_ACC_NUDGE_S = _accn._ACC_NUDGE_S
_acc_notice_plan = _accn._acc_notice_plan
_speak_acc_drop = _accn._speak_acc_drop
_schedule_acc_nudge = _accn._schedule_acc_nudge



# ── FLOW LIFECYCLE (V2-096/V2-113/V2-116/V2-123) — extracted to `flow_lifecycle.py` (ratchet, 2026-09-05).
# Historical names stay as ALIASES; `_PENDING_FLOW_CLOSES` is the same dict object (mutated, never rebound).
from .flow_lifecycle import (  # noqa: F401 — re-export, not a local use
    _CHAIN_GRACE_S, _PENDING_FLOW_CLOSES, _WORKER_CONTROL_TOOLS, _begin_or_adopt_trace, _close_flow_now,
    _flow_should_close, _maybe_close_flow, _merge_target, _release_acc_trace_if_fresh, _resolve_acc_chain,
    drain_pending_flow_closes)


def _resolve_pending_confirm(ok: bool) -> bool:
    """Resolve the pending confirmation (any widget). If `ok`, EXECUTE what was confirmed: a widget DELETION
    (deterministic, including memory) or an irreversible DATA-OP (dispatched by `apply_action`, NEVER code).
    Return True if there was something to resolve.

    MODULE function (not a closure of `_run_inner`, V2-090 addendum 2026-08-15), specifically so it can be called
    ANTES de que el turno haga ningún trabajo lento — ver el hueco real que arregla en el sitio donde se llama
    early, inside `_run_inner`: the old deterministic backstop ran only AFTER the model’s COMPLETE streaming, and a
    turn cancelled by barge-in before reaching it silently lost the “yes” — the confirmation remained pending forever
    and the widget was never touched (real session: “Yes, empty the whole thing.” was cancelled because the operator
    kept speaking; the operator saw “confirm” and the agenda did not change)."""
    try:
        from voice.observer import emit
        p = _wconfirm.resolve("", ok)
        if p is None:
            return False
        # Observability (V2-090 addenda): esta respuesta nació en SU PROPIO turno (trace fresco) — antes de
        # ejecutar/cancelar, adopta el trace de la pregunta para que ask→respuesta→acción sean UN flujo, no dos.
        try:
            _ptid = str(p.get("trace_id") or "")
            if _ptid:
                from voice import trace as _trace4
                _trace4.adopt(_ptid)
        except Exception:
            pass
        if not ok:
            emit("brain", "↩️ acción cancelada", text=p.get("widget_id", ""), role="system")
        elif p.get("action") == "data" and isinstance(p.get("op"), dict) \
                and p["op"].get("action") == "connect_cluster":
            try:
                from connectors import meshkore as _mk
                _pl = p["op"].get("payload") or {}
                _spawn(_mk.dispatch_tag("cluster.connect", {"data": _pl}), "cluster")
                emit("brain", "🛰 conectando cluster MeshKore (confirmado)", text=_pl.get("name", ""),
                     role="system")
            except Exception:
                pass
        elif p.get("action") == "data" and isinstance(p.get("op"), dict):
            try:
                # V2-743 — `receipt=True`: this is the CONFIRMED path, the one where a false «done» costs
                # something, so the outcome is witnessed against the widget's own view before anything is said.
                _spawn(_data_ops.dispatch_and_report(p["widget_id"], str(p["op"].get("action") or ""),
                                                     p["op"].get("payload") or {}, receipt=True),
                       "widget-data-confirmed")
                emit("brain", "✅ acción irreversible confirmada", role="system",
                     text=f"{p['widget_id']}:{p['op'].get('action')}")
            except Exception:
                pass
        elif p.get("action") == "delete":
            _spawn(_wlifecycle.delete_widget(p["widget_id"], "flash"), "widget-delete")
            emit("brain", "🗑️ widget borrado (confirmado)", text=p["widget_id"], role="system")
        elif p.get("action") == "restore":
            _spawn(_wlifecycle.restore_widget(p["widget_id"], "flash"), "widget-restore")
            emit("brain", "⟲ widget restaurado a la versión de sistema (confirmado)", text=p["widget_id"],
                 role="system")
        return True
    except Exception:
        return False


# V2-669: the body moved to `flash/surface_ack.saved_state_is_empty` — the SAME decision was written there too
# (`nothing_to_show`'s docstring cited this copy by name), and the ratchet asks for a module, never a taller
# ceiling. The name stays here because callers and tests reach for it through this module.
from nucleo.flash.surface_ack import saved_state_is_empty as _surface_is_empty  # noqa: E402
# V2-778 F1-10 — the turn's tool executor and post-stream chain live in their own modules.
from nucleo.flash import post_stream as _post_stream, tool_executor as _tool_executor  # noqa: E402


def _spawn(coro, label: str):
    task = asyncio.create_task(coro)
    _TAG_TASKS.add(task)
    task.add_done_callback(lambda t: _TAG_TASKS.discard(t))
    return task


@registry.register("nucleo")
def build(model: str = "") -> llm.LLM:
    return NucleoLLM()


class NucleoLLM(llm.LLM):
    def __init__(self) -> None:
        super().__init__()
        self._window: list[dict] = []      # ventana de diálogo corta del FlashBrain
        self._seeded = False               # ¿ya sembrada la ventana desde memoria? (circuito de corto plazo)
        self._directive = ""               # preferencia de estilo fijada esta sesión (set_style_directive)
        self._last_spoken = ""             # última frase que DIJO zaelar (anti-eco, FASE 2) — INCLUYE fillers
        self._last_spoke_at = 0.0          # cuándo la dijo (epoch s) → ventana de eco
        self._last_reply = ""              # última respuesta con CONTENIDO real (nunca un filler) — contexto
        #                                    de `attention.evaluate_content()` (ver el `send()` de más abajo)
        self._last_dataop = None           # (wid, action, payload, ts) última data-op EJECUTADA — guard anti
        #                                    context-bleed (round headless V2-038 #1: re-emisión cross-turno)
        self._utterance: dict = {"text": "", "at": 0.0}   # frase EN CURSO del operador (guarda de fragmentos, _extends)
        self._acc_trace_id: str = ""       # trace del flujo mientras el acumulador (V2-096) tiene trozos a medias
        self._chain_grace: tuple[str, float] = ("", 0.0)   # (trace, ts) de la última cadena RESUELTA (V2-116):
        #                                    sigue adoptable unos segundos para que el trozo siguiente de la
        #                                    misma frase no abra un flujo nuevo — ver `_begin_or_adopt_trace`
        self._escalated_trace_id: str = "" # trace que ACABA de publicar escalate.requested este turno (V2-113):
        #                                    bridges the sync race before dispatch.run_listener gets a scheduler
        #                                    turn to register/reject/dedup it — see `_flow_should_close`
        self._turn_tools: set = set()      # tools this turn actually RAN (V2-123): tells a turn that merely talked
        #                                    about the running task apart from one that started something else —
        #                                    see `_merge_target`. Reset per turn in `_run_inner`.
        self._acc_gen: int = 0             # accumulator chain generation (2026-08-15, see `_schedule_acc_nudge`):
        #                                    bumped every time a chain resolves or gets dropped, so a nudge
        #                                    scheduled for it and now stale doesn't fire late
        self._turn_count = 0                # turnos conversacionales completados esta sesión (INI-018 T6, demo cap)
        self._last_action = ""              # route/surface del turno anterior para referencias deícticas
        self._session_started_at = time.time()  # arranque de la sesión (INI-018 T6, demo TTL)

    @property
    def label(self) -> str:
        return "zaelar.nucleo"

    @property
    def model(self) -> str:
        return "nucleo-flash"

    def set_briefing(self, text: str) -> None:
        """Compat con el entrypoint (duo lo usa). En nucleo la memoria de arranque sale de `memory.state()` en el
        prompt cada turno, así que aquí no hace falta — se acepta y se ignora para no romper una llamada genérica."""
        return None

    def chat(self, *, chat_ctx, tools=None, conn_options=DEFAULT_API_CONNECT_OPTIONS,
             parallel_tool_calls=None, tool_choice=None, extra_kwargs=None) -> llm.LLMStream:
        return NucleoLLMStream(self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options)


class NucleoLLMStream(llm.LLMStream):
    # ── UN TURNO QUE MUERE DEJA RASTRO (2026-08-10) ───────────────────────────────────────────────────────────────
    # Incidente real (sesión 13:20:50): el operador dictó una petición larga —ferry Dénia→Ibiza, fechas, medidas del
    # coche, 4 pasajeros— y su turno (T6) se quedó SIN RESPUESTA. 13 ms después entró el turno siguiente
    # («muéstrame los resultados») y LiveKit canceló T6 en pleno montaje del prompt. Dos daños, los dos invisibles:
    #   (a) el TEXTO se perdió — el `push_user` que conserva la frase del operador vivía SOLO en el `except` del
    #       stream, así que una cancelación ANTES de llegar al stream se llevaba los criterios por delante y el
    #       turno siguiente hablaba de «los resultados» sin saber de qué; y
    #   (b) no quedaba ni una línea en la observabilidad: el evento `prompt` salía y luego NADA. Mirando el log se
    #       veía la petición entrar y no salir, sin motivo — el mismo pecado que un micrófono encendido con el
    #       agente muerto (ver la regla «estado visible, no silencioso»).
    # Por eso el cuerpo del turno pasa a `_run_inner` y `_run` queda como ENVOLTURA: cualquier cancelación, en
    # cualquier fase, conserva la frase y deja su rastro con la FASE en la que murió. No cambia el camino feliz.
    async def _run(self) -> None:
        self._phase = "arranque"
        self._death_logged = False
        try:
            await self._run_inner()
        except asyncio.CancelledError:
            self._note_death("superado por otro turno")
            raise
        else:
            _maybe_close_flow(self._llm)

    def _superseded(self) -> bool:
        """True si ya llegó una versión MÁS LARGA de la misma frase que este turno está atendiendo — o sea, el
        operador seguía hablando y esto es un fragmento viejo. Ver `_extends` para el porqué de la señal."""
        mine = getattr(self, "_turn_text", "")
        if not mine:
            return False
        return _extends(mine, (getattr(self._llm, "_utterance", None) or {}).get("text", ""))

    def _note_death(self, reason: str) -> None:
        """Conserva la frase del operador y registra DÓNDE murió el turno. Idempotente: el `except` del stream ya
        emite su propia línea (con métricas de barge-in), así que marca la bandera y esta no duplica."""
        if getattr(self, "_death_logged", False):
            return
        self._death_logged = True
        try:
            from voice.observer import emit
        except Exception:
            return
        text = _last_user_text(self._chat_ctx)
        kept = False
        if text:
            # Cancelar la RESPUESTA no borra la FRASE (misma regla que el barge-in del stream, ahora en TODAS las
            # fases): sin esto, el turno siguiente llega al modelo sin el contexto que el operador acababa de dar.
            try:
                from nucleo.flash import dialog as _dialog
                _dialog.push_user(self._llm._window, text)
                del self._llm._window[:-_WINDOW_MAX]
                kept = True
            except Exception:
                pass
        _acc_mod.unanswered_by(self._llm, text)   # V2-776 D0 — pre-stream: nothing of it was answered
        emit("brain", "✂️ turno descartado — sin respuesta", text=text[:200], role="system",
             extra={"cat": "flash", "reason": reason, "phase": getattr(self, "_phase", "?"),
                    "text_kept": kept})

    async def _run_inner(self) -> None:
        brain: NucleoLLM = self._llm  # type: ignore[assignment]
        try:
            from voice.observer import emit
        except Exception:
            emit = lambda *a, **k: None

        text = _last_user_text(self._chat_ctx)
        if not text:
            emit("brain", "⚠️ Nucleo triggered but no user text in context")
            return

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
            _begin_or_adopt_trace(brain, text, first_turn)
        except Exception:
            pass
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
                _cont = await _hard_turn.handle(text, hard, emit)
                if _cont is None:
                    _release_acc_trace_if_fresh(brain)      # ver docstring — este turno no llega a offer()
                    return
                text = _cont

        # (V2-726 A2) The turn brief is NOT fired here any more — this line runs before echo
        # suppression and before the accumulator, so it classified a fragment. Search for
        # «JEV TURN BRIEF» below; the why is in `nucleo/flash/turn_brief.py`'s docstring.
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
                from nucleo import worker_api as _wapi0
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
                    _release_acc_trace_if_fresh(brain)          # ver docstring — este turno no llega a offer()
                    return

        # T134 — un turno no dirigido no se atiende (ni siquiera drena notas: se preservan para el próximo).
        # El kickoff (saludo de zaelar) NO abre la ventana a propósito: es zaelar quien habla, no el operador
        # dirigiéndose a él — así, si la sesión arranca en mitad de una reunión, no hay un hueco inicial en el
        # que la voz ambiente se cuele como dirigida y auto-extienda la ventana. El operador abre la conversación
        # con la wake-word ("zaelar") y a partir de ahí la ventana la mantiene viva (o chat/paste, ya marcados).
        # V2-654 — el micro cerrado manda sobre TODO, y por eso va ANTES del gate: el porqué, en `mic_input`.
        if not first_turn and mic_input.blocks_turn(text):
            _release_acc_trace_if_fresh(brain)   # este turno no llega a offer() — ver docstring
            return
        # V2-765 — no language, no turn. The session should not even exist (the token is refused), so this is
        # the backstop for one that outlived the gate: nothing heard before the picker is used reaches the brain.
        if not first_turn:
            from nucleo import runstate as _rs_lang
            if _rs_lang.language_pending():
                emit("mic", "🌐 turno DESCARTADO — falta elegir el idioma", text=text[:200], role="user",
                     extra={"reason": "language"})
                _release_acc_trace_if_fresh(brain)
                return

        if not first_turn:
            # T134 — un turno no dirigido no se atiende. El bloque entero vive en `attention_turn.judge`
            # (V2-655): qué decide, por qué el juez recibe `_last_reply`, y por qué AMBOS veredictos llevan
            # la ventana («el sonido ambiente no interrumpe para nada los contadores») están escritos allí.
            _directed, text, _gate_ms = await _attention_turn.judge(
                text, context=brain._last_reply, emit=emit)
            if not _directed:
                _release_acc_trace_if_fresh(brain)   # ver docstring: este turno no llega a offer()
                return

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
                from nucleo import request_row as _rq
                _rq.begin(text)          # V2-776 M1 — the words the row of this request will carry
            except Exception:  # noqa: BLE001
                pass

        # ACTION MAP (V2-539) + PRESENCE knock (V2-640) + SMALL TALK (V2-674) skip the model: see
        # fast_lane.py (mirrors in probe.py).
        try:
            from voice.engine.llm.providers import fast_lane as _fast_lane
            if (await _fast_lane.task_list(brain, text, emit, first_turn=first_turn, window_max=_WINDOW_MAX)
                    or await _fast_lane.handled(brain, text, emit, first_turn=first_turn,
                                         t_entry=_t_entry, window_max=_WINDOW_MAX)
                    or await _fast_lane.presence(brain, text, emit, first_turn=first_turn,
                                                 window_max=_WINDOW_MAX)
                    or await _fast_lane.rename(brain, text, emit, first_turn=first_turn,
                                               window_max=_WINDOW_MAX)
                    or await _fast_lane.wall_tab(brain, text, emit, first_turn=first_turn,
                                                 window_max=_WINDOW_MAX)
                    or await _fast_lane.small_talk(brain, text, emit, first_turn=first_turn,
                                                   window_max=_WINDOW_MAX, ask_waiting=_ask_waiting)):
                _release_acc_trace_if_fresh(brain)   # same situation as the hard interrupt: no offer()
                return
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
        if not first_turn:
            from nucleo.flash import accumulator as _acc
            if getattr(brain, "_acc", None) is None:
                brain._acc = _acc.Accumulator()
            _n_before = len(brain._acc.fragments)
            _ta = time.time()
            _action, _merged, _why, _dropped = await brain._acc.offer(text)
            _acc_ms = round((time.time() - _ta) * 1000, 1)

            # BUG FIX (2026-08-15, session d4b2bc35): a stale chain that got silently discarded (gap > MAX_GAP_S)
            # used to only ever surface — muted, in `extra`, never spoken — when the CALL AFTER the drop happened
            # to land on "act". The far more common case is that the fragment causing the drop is itself
            # incomplete and falls to "hold" a few lines below, which carried no drop info at all: the operator's
            # words vanished with zero trace anywhere, timeline included. `Accumulator.offer()` now reports
            # `_dropped` on EITHER branch, so this fires every time regardless of what this call goes on to do.
            _speak_drop, _fresh_chain = _acc_notice_plan(_action, _dropped, _n_before)
            if _dropped:
                emit("brain", "🕳️ frase anterior descartada por el hueco", text=_dropped[:200], role="system",
                     extra={"cat": "flash", "gap_s": _acc.MAX_GAP_S})
            if _speak_drop:
                _spawn(_speak_acc_drop(_dropped), "acc_drop_notice")

            if _action == "hold":
                # Callar es la conducta CORRECTA aquí, no un efecto colateral que haya que compensar con un
                # temporizador. Norma del operador, con su propio ejemplo: «si digo "oye, ¿qué tal? ahora vamos
                # a…" y me paro ahí, obviamente esa frase no genera absolutamente nada NI DEBE GENERARLO».
                # Por eso no hay flush por tiempo: un fragmento abandonado se queda sin respuesta a propósito, y
                # las válvulas del acumulador (hueco máximo, nº de trozos, tamaño) son solo para que el buffer no
                # crezca ni contamine una petición posterior que no tiene nada que ver.
                # Y se VE: el trozo retenido y el motivo salen al timeline (⏸), que es la diferencia entre «está
                # esperando a que acabes» y «se ha quedado colgado».
                # 2026-08-15: and if the wait drags on, it's now also HEARD (`_schedule_acc_nudge` below) — the
                # real session's 64s gap had neither signal.
                if _fresh_chain:
                    brain._acc_gen += 1
                    _schedule_acc_nudge(brain, brain._acc_gen)
                emit("brain", "⏸ frase a medias — espero a que termines", text=text[:200], role="system",
                     extra={"cat": "flash", "why": _why, "trozos": len(brain._acc.fragments),
                            "acumulado": brain._acc.text()[:300]})
                return

            if _action == "ask":
                # V2-102: layer 2 (the LLM judge) says this looks actionable but is missing something concrete
                # enough that a real assistant would ASK rather than guess or wait in silence. `_why` carries the
                # question text here (repurposed — see `Accumulator.offer`'s docstring). Speaks it exactly like
                # the drop-notice/nudge do (`voice.proactive.speaker()`, never over the operator mid-sentence)
                # and RETURNS — the question IS this turn's response, no FlashBrain dispatch, no memory ingest.
                brain._acc_gen += 1
                brain._acc_trace_id = ""
                emit("brain", "❓ pidiendo aclaración", text=_why[:200], role="system",
                     extra={"cat": "flash", "acumulado": _merged[:300]})
                try:
                    from voice import proactive
                    speak = proactive.speaker()
                    if speak is not None and not proactive.user_speaking():
                        r = speak(_why)
                        if asyncio.iscoroutine(r):
                            await r
                except Exception:
                    pass
                return

            if _n_before and not _dropped:
                emit("brain", "🧩 frase completada en varios tiempos", text=_merged[:300], role="user",
                     extra={"cat": "flash", "trozos": _n_before + 1, "motivo": _why})
            brain._acc_gen += 1          # cadena resuelta — un aviso pendiente para ella queda obsoleto
            _resolve_acc_chain(brain)    # el trace pasa a GRACIA, no se tira (V2-116)
            text = _merged

        # JEV TURN BRIEF (V2-726 F1, moved here by A2): ONE call carrying every question this turn
        # reads AFTER the model — canvas verb, escalate pair, which action of which open card, and
        # what KIND of turn it is (which the filler used to ask on a second socket of its own).
        # HERE because here the sentence is FINAL: past the hard interrupt, past echo suppression,
        # past the accumulator. Not later either — the readers are 2-4 s away and this takes ~800 ms,
        # which is the overlap that makes it free. Assembly, bounds and fail-soft: `turn_brief`.
        from nucleo.flash import turn_brief as _turn_brief
        _brief = canvas_h = _turn_brief.ask_for_turn(
            text, running_goals=_show_target._running_goals(),
            last_reply=getattr(brain, "_last_reply", "") or "",
            turn_id=f"{id(brain):x}-{getattr(brain, '_acc_gen', 0)}")

        # V2-013: el "corazón" (agente de memoria) clasifica en background lo que dijo el operador y, si es
        # perfil (nombre/ubicación/trato/hardware/coche) o deseo durable, lo lleva a `state`/`long` sin
        # bloquear el turno. Fire-and-forget: regex µs + escritura por la cola async → cero coste en TTFB.
        try:
            from nucleo import memory_agent as _mem_agent
            asyncio.create_task(_mem_agent.ingest_utterance(text, role="operator"))
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
                    _seed = _memory.recent_window(limit=int(os.getenv("ZAELAR_WINDOW_SEED", "6")))
                    if _seed:
                        brain._window[:0] = _seed
                        emit("brain", "🌱 ventana sembrada desde memoria", role="system",
                             extra={"turns": len(_seed)})
                except Exception:
                    pass

        # LATENCY GUARD + T135: acota lo que ve la capa rápida (turnos-parrafada) PRESERVANDO un comando
        # explícito — nunca truncar a ciegas los últimos N chars (así se perdía el "cierra los widgets").
        _max_in = int(os.getenv("ZAELAR_FAST_MAX_INPUT", "1600"))
        text, _clipped = attention.clamp_input(text, _max_in)
        if _clipped:
            emit("brain", "✂️ input recortado (comando preservado)", text=f"→{_max_in} chars")
        if first_turn:
            text = _say().kickoff_prompt   # V2-682 — it impersonates HIM, so it is in HIS language

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
            logger.warning(f"provider_chain(voice) no resolvió; sigo con la config: {_e_pc!r}")
        emit("brain", "⚡ Nucleo(flash): prompt", text=text, role="user",
             extra={"engine": spec.provider, "model": spec.model})

        self._phase = "montando el prompt"
        timings: dict = {}
        _t_prompt = time.time()
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
                recent_block = await asyncio.wait_for(
                    asyncio.to_thread(_prompt_mod.compose_recent_block), timeout=0.5)
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
        timings["prompt_ms"] = round((time.time() - _t_prompt) * 1000, 1)
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
        messages += _dialog.prune_window(brain._window)[-_WINDOW_MAX:]   # colapsa turnos gemelos (anti-degeneración)
        messages.append({"role": "user", "content": text})

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
        buf, spoken, first_ms = "", [], None
        _t_stream0 = time.monotonic()      # covers fired at/after this instant belong to THIS turn (V2-642)
        # `v` = la escalada PRINCIPAL del turno (la primera); `more` = las ADICIONALES cuando el operador encarga
        # varias tareas DISTINTAS de una sentada (V2-118, medido 2026-08-18). Antes solo existía `v` con un
        # `if is None`, así que de «hazme un informe, búscame un monitor y móntame un widget» arrancaba UNA tarea
        # y las otras dos se descartaban en silencio — mientras el turno DECÍA que las tres iban en marcha. El
        # arnés lo midió por el registro real (`/api/tasks`), no por el transcript: máximo simultáneo 1.
        # Sigue habiendo una principal a propósito: todo el resto del turno (guards de show, backstops, dedup,
        # ack «nunca mudo») razona sobre UNA decisión, y esos caminos no cambian. Las adicionales solo se suman
        # al final, cuando ya se sabe que el turno escaló de verdad.
        escalate_req: dict = {"v": None, "more": [], "surface": {}}   # V2-227: superficie declarada POR petición
        search_req = {"v": None}
        listing_req = {"v": None}        # V2-556: la pasada rápida de anuncios (nucleo/flash/listing_turn.py)
        recall_req = {"v": None}         # V2-056: el modelo pidió RECORDAR (tool recall) — se resuelve tras el stream
        read_req = {"v": None}           # V2-668: el modelo pidió LEER un widget (read_widget) — hermana de recall
        reopen_req = {"v": None}         # V2-728: el modelo pidió RECUPERAR el resultado de un encargo terminado
        reveal_req = {"v": None}         # V2-060: el operador pidió un SECRETO (reveal_secret) — valor OUT-OF-BAND
        music_req = {"v": None, "followup": None}  # V2-041: {'query','action'}; 'followup' = 2ª acción de CONTROL
        images_req = {"v": None}                   # V2-457: {'query','n'} de `show_images`, ejecutado tras el stream
                                          # (volumen/pausa) pedida EN EL MISMO turno que un play/queue (bug real
                                          # 2026-07-23: "pon música de Queen y súbele el volumen" decía las DOS
                                          # cosas pero solo ejecutaba la 1ª — la 2ª se tiraba en silencio)
        style_fired = {"v": False}       # V2-046 A1: se fijó/retiró una user rule → ack si el modelo no habló
        acted = {"widget": False}
        confirm_state = {"handled": False}
        clarify = {"msg": None}          # V2-026: pregunta a decir si una referencia a un item no se resolvió
        _closed_by_tool: set = set()      # the cards `close_widget` closed this turn — each one once
        _repeat_repair: dict = {"v": None}  # (card, repeated view, verdict action) — see `call_for_repeated_view`
        data_done = {"v": False}         # V2-026: se despachó una data-op FAST → ack hablado si el modelo no habló
        deduped = {"v": False}           # V2-634: el guarda anti context-bleed descartó un duplicado — el turno
                                         # fue ATENDIDO (dedupe deliberado), no un vacío que disculpar
        aside = {"v": False}             # V2-657: el modelo emitió [[aparte]] — el turno iba dirigido a OTRA
                                         # persona presente; silencio sancionado, y el refresco de ventana se
                                         # RETRACTA para que la conversación pueda morir durante charla de sala
        worker_acted = {"v": None}       # V2-038: 'inject'|'stop'|'answer' si se dirigió a un Brain Worker vivo
        cron_seen = {"v": False}         # V2-146: el turno YA pidió un cron → el backstop de aviso no duplica
        _shown_ids: set = set()          # ids ya mostrados ESTE turno → dedup de [[show]] duplicado
        # ¿había una confirmación de borrado en el aire al empezar el turno? Solo entonces interpretamos un
        # "sí/no" suelto como respuesta a ELLA (red determinista, por si el modelo no llama a la tool).
        try:
            had_pending_confirm = bool(_wconfirm.pending())
        except Exception:
            had_pending_confirm = False

        def send(txt: str):
            nonlocal first_ms
            if not txt:
                return
            if first_ms is None:
                first_ms = round((time.time() - t0) * 1000)
            spoken.append(txt)
            # ANTI-ECO (FASE 2): recuerda lo ÚLTIMO que zaelar dice + cuándo, para descartar el eco que el mic
            # recaptura como turno del operador. Se actualiza en CADA salida de voz (respuesta, filler, degradado).
            brain._last_spoken = "".join(spoken)
            brain._last_spoke_at = time.time()
            # `_last_reply` es el mismo texto pero SOLO pasa por aquí (nunca por el camino del filler, hoy
            # `voice/engine/speech/filler_audio.py`) — es el contexto que `evaluate_content()` necesita para juzgar si el
            # siguiente turno va dirigido. Un filler ("Pues…", "Mmm…") no lleva ningún tema: si se dejaba pisar
            # `_last_spoken` con él, el juez recibía "Se estaba haciendo: Pues…" justo tras una pregunta real y
            # clasificaba el siguiente turno del operador como ambiente (bug real, sesión 2026-08-17: 4 preguntas
            # de seguimiento — incluida la queja «te acabo de hacer preguntas ahora» — descartadas de seguido,
            # cada una justo tras un filler).
            brain._last_reply = "".join(spoken)
            # A real reply KEEPS THE CONVERSATION ALIVE (2026-09-01): the attention window opens on the
            # operator's handled turn, but a long narration can outlast `window_s()` — and then his answer to
            # what Zaelar just said lands on the cold-turn judge. Refreshed here, per chunk, because this path
            # only runs for real model output on a turn that already passed the gate; the kickoff (`first_turn`)
            # deliberately does NOT open the window (a session starting mid-meeting must not let ambient speech
            # in through an initial gap — the same rule written at the gate call site).
            if not first_turn:
                attention.note_directed()
            self._event_ch.send_nowait(
                ChatChunk(id=utils.shortuuid(), delta=ChoiceDelta(role="assistant", content=txt))
            )

        # CONFIRMACIÓN PENDIENTE — resuelta YA, antes de CUALQUIER trabajo lento (V2-090 addenda, 2026-08-15).
        # El backstop determinista de más abajo (RED DETERMINISTA V2-017, `classify_reply` + `_resolve_confirm`)
        # solo corre TRAS el streaming COMPLETO del modelo — cientos de líneas y varios segundos de por medio. Si
        # el operador sigue hablando, este turno se cancela por barge-in (como CUALQUIER turno) antes de llegar
        # allí, y el "sí" se pierde EN SILENCIO: la confirmación se queda pendiente para siempre y el widget nunca
        # se toca. Sesión real que lo demuestra: «Sí, vacía la entera.» se canceló por barge-in antes de resolver
        # nada; el operador vio "confirmar" y la agenda no cambió — no era un fallo de `apply_action` (que SÍ
        # marca los datos), era que la confirmación jamás llegó a ejecutarse. Un sí/no CLARO se resuelve AQUÍ,
        # determinista y ANTES de llamar al modelo — mismo principio que `attention.hard_interrupt`: lo
        # irreversible no puede depender de que el turno sobreviva entero. Ambiguo (`classify_reply` → None) cae
        # al backstop de siempre, que sigue con el modelo por si aporta más contexto.
        if not first_turn and had_pending_confirm:
            try:
                _verdict_early = _wconfirm.answers_pending(text)
            except Exception:
                _verdict_early = None
            if _verdict_early:
                if _resolve_pending_confirm(_verdict_early == "yes"):
                    # V2-743 — A YES IS ANSWERED WITH A START, NEVER WITH A COMPLETION. `data_ack` is
                    # «Hecho.», and this branch fires the instant the operator agrees: measured 2026-09-21
                    # (session bcd4aba1) it was spoken 0.86 s after the deletion was DISPATCHED and 7 s
                    # before any outcome existed — the op then outlived the widget pool's 8 s ceiling and
                    # finished anyway, so he heard «Hecho.», watched 47 rows sit there, and had to discover
                    # both the delay and the truth himself. The outcome now arrives from `op_receipt` when
                    # the work actually settles; this line only promises that it has begun.
                    _ack_early = (_say().work_started if _verdict_early == "yes" else _say().confirm_cancelled)
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

        _tool_fired: set = set()
        _data_ops_hechas: list = []      # V2-391: las data-ops YA ejecutadas de este turno, en orden
        _turn_op_tasks: list = []        # the dispatches of THIS turn's data-ops — a read of their card waits for them

        def take(final: bool) -> str:
            nonlocal buf
            out, buf = strip_tags(buf, _tag_emit, final)
            return out

        def _cover_work(kind: str, target: str = "") -> None:
            """Tell the filler node what this turn is about to GO AND DO, so it can cover the far side of the
            tool seam while the work and the second pass run (V2-669). Voice only: the text channel has no dead
            air to fill. Never breaks a turn."""
            try:
                from voice.engine.speech import filler_audio as _fa_w
                _fa_w.note_work(brain, kind, target)
            except Exception:                       # noqa: BLE001
                pass

        async def speak(sys2: str, user_text: str, max_tokens: int = 240, what: str = "2º pase") -> None:
            """ONE (system, user) SECOND PASS streamed straight into the mouth — the shape every light route
            (recall, read_widget) had written out in full. Owns this turn's tag accumulator (`buf`/`take`), so
            it cannot live outside this closure; the routes themselves live in their modules and inject it."""
            nonlocal buf
            buf = ""                        # discard any tag leftovers from the first pass
            # What this turn ALREADY said, so the second pass continues it instead of contradicting it (demo pass
            # 2026-09-28, C3: «which slot do you want, the 1:00 or the 4:00?» followed by a read answer saying «I
            # don't have any free-afternoon slot details») — and its first words are never glued to it
            # («…your day.Tomorrow, Tuesday»).
            _said = "".join(spoken).strip()
            if _said:
                user_text = (f"{user_text}\n\n(En este turno ya le has dicho: «{_said[:400]}». Continúa desde ahí, "
                             f"en SU idioma: no lo repitas ni lo contradigas. Si eso YA contesta lo que preguntó, "
                             f"responde exactamente SKIP y nada más. Anunciar que vas a mirar o que lo estás "
                             f"mirando NO es contestar: entonces da la respuesta.)")   # full53 R3: «let me look…» + SKIP
            _lead = [" " if _said else ""]
            # SKIP is held back until it can be told apart from an answer — a model asked for an EMPTY reply
            # says «you're all set» instead, so the silence is a word we recognise and never speak.
            _held = [""] if _said else None

            def _out(piece: str) -> None:
                if _held is not None:
                    if _held[0] is None:
                        return                                   # decided: SKIP — nothing of this pass is spoken
                    if _held[0] is not False:
                        _held[0] += piece or ""
                        head = _held[0].strip().upper()
                        if head.startswith("SKIP"):
                            _held[0] = None
                            # visible on the timeline (full53 R3 went silent after «let me look…» and nothing said why)
                            emit("brain", "🤐 segundo pase: SKIP — lo ya dicho contestaba", role="system",
                                 text=f"{what}: {_said[:120]}", extra={"cat": "flash"})
                            return
                        if len(head) < 4 and "SKIP".startswith(head):
                            return                               # still could be SKIP: keep holding
                        piece, _held[0] = _held[0], False
                if piece and _lead[0]:
                    piece, _lead[0] = _lead[0] + piece, ""
                send(piece)
            try:
                async for delta in FastClient().stream(
                        [{"role": "system", "content": sys2}, {"role": "user", "content": user_text}],
                        spec=spec, max_tokens=max_tokens):
                    buf += delta
                    _out(speech.inline(take(False)))
                _out(speech.sanitize(take(True), drop_metadata=False))
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.warning(f"{what} falló (voz sigue): {e}")

        # Security-config voice command + spoken-secret interception (V2-060), both DETERMINISTA before the model
        # ever sees the text — moved to vault_intercept.py (2026-08-17 modularization pass, extraction step 1 of
        # the plan from this session's architecture audit). `send`/`emit` passed through as-is: `emit` may have
        # been locally overridden to a no-op above, and `send` is this closure's own turn-state accumulator.
        from voice.engine.llm.providers.vault_intercept import try_vault_intercept
        _vault_done, text = await try_vault_intercept(text, first_turn, send, emit)
        if _vault_done:
            return

        # V2-778 F1-10 — the tool executor lives in `nucleo/flash/tool_executor.py`; built here, after the last
        # rebinding of anything it captures (the vault intercept above may redact `text`).
        _tx = _tool_executor.build(
            self=self,
            brain=brain,
            emit=emit,
            text=text,
            operator_text=operator_text,
            _brief=_brief,
            canvas_h=canvas_h,
            aside=aside,
            cron_seen=cron_seen,
            _shown_ids=_shown_ids,
            acted=acted,
            confirm_state=confirm_state,
            clarify=clarify,
            _closed_by_tool=_closed_by_tool,
            _repeat_repair=_repeat_repair,
            data_done=data_done,
            deduped=deduped,
            escalate_req=escalate_req,
            search_req=search_req,
            listing_req=listing_req,
            recall_req=recall_req,
            read_req=read_req,
            reopen_req=reopen_req,
            reveal_req=reveal_req,
            music_req=music_req,
            images_req=images_req,
            style_fired=style_fired,
            worker_acted=worker_acted,
            _frontend=_frontend,
            _router=_router,
            _tool_fired=_tool_fired,
            _data_ops_hechas=_data_ops_hechas,
            _turn_op_tasks=_turn_op_tasks,
            _spawn=_spawn,
            _say=_say,
            _resolve_pending_confirm=_resolve_pending_confirm,
            _confirm_decide=_confirm_decide,
            _close_target=_close_target,
            _identify=_identify,
            _identify_is_widget=_identify_is_widget,
            _is_meta_widget_question=_is_meta_widget_question,
            _norm_nfkd=_norm_nfkd,
            _show_guard_target=_show_guard_target,
            _show_target_instance=_show_target_instance,
            with_also_named=with_also_named,
        )
        _tag_emit, _apply_widget_data, _on_tool_call = _tx.tag_emit, _tx.apply_widget_data, _tx.on_tool_call
        _resolve_confirm, _start_web_auth = _tx.resolve_confirm, _tx.start_web_auth


        errored = False
        stalled = False          # se atascó UN turno (≠ el cerebro está caído) — cambia lo que se le cuenta al operador
        err_text = ""
        err_exc: BaseException | None = None   # V2-758 — the exception ITSELF: only it can say whose fault this is
        llm_metrics: dict = {}   # totalizadores de tamaño/tokens/latencia del modelo (observabilidad, FASE 0)
        # SET CONTEXTUAL DE TOOLS (V2-035): omite las situacionales que no aplican este turno (confirmar-borrado sin
        # borrado en el aire, login-hecho sin login en curso) → prompt más corto y menos ruido de decisión.
        try:
            from widgets.navegador import tasks as _nt
            _auth_pending = bool(_nt.login_waiting_id())
        except Exception:
            _auth_pending = False
        # V2-038: ofrece send/stop_worker solo si hay Brain Workers vivos, y answer_worker solo si alguno espera.
        try:
            from nucleo import dispatch as _dispatch, worker_api as _wapi
            _has_workers = _dispatch.has_active()
            _ask_pending = _wapi.has_pending_ask()
        except Exception:
            _has_workers = _ask_pending = False
        # V2-086: las tools de cluster YA NO dependen de tener un widget delante. El gate de V2-064
        # (`cluster-registro` abierto) hacía la capacidad INDESCUBRIBLE — para conectar un cluster NUEVO había que
        # saber de antemano que primero tocaba abrir un widget concreto (pez que se muerde la cola: comprobado en
        # el turno 766 del 2026-08-01, donde `connect_cluster` simplemente no estaba en el set ofrecido y el
        # modelo no pudo hacer nada). La protección real contra el disparo espurio no era ese gate sino la
        # CONFIRMACIÓN Sí/No determinista con el cluster_id a la vista, que sigue intacta.
        _cluster_open = True
        # `cluster_send` sí es situacional, pero por ESTADO REAL: sin cluster conectado no hay a quién escribir.
        try:
            from connectors import meshkore as _mk0
            _cluster_conn = any(c.get("connected") for c in _mk0.get_manager().clusters())
        except Exception:
            _cluster_conn = False
        # V2-085 — tres CAPACIDADES reales más (nunca palabras del turno: hechos del sistema). Todas fail-OPEN:
        # si el sondeo peta, la tool se ofrece igual y no le quitamos nada al operador.
        try:
            from connectors.whatsapp import service as _wa1
            _msg_on = _wa1.enabled()
        except Exception:
            _msg_on = False
        if not _msg_on:
            try:
                from connectors.telegram import service as _tg1
                _msg_on = _tg1.enabled()
            except Exception:
                _msg_on = True                  # no se pudo sondear ninguno → fail-open
        try:
            from memory import vault as _vault1
            _has_vault1 = _vault1.exists()
        except Exception:
            _has_vault1 = True
        try:
            from widgets import runtime as _rt_cap
            _has_video1 = _rt_cap.get("youtube") is not None
        except Exception:
            _has_video1 = True
        _tool_ctx = _router.tool_context(confirm_pending=had_pending_confirm, auth_pending=_auth_pending,
                                         has_workers=_has_workers, ask_pending=_ask_pending,
                                         cluster_widget_open=_cluster_open, messaging_on=_msg_on,
                                         has_vault=_has_vault1, has_video_widget=_has_video1,
                                         cluster_connected=_cluster_conn)
        _turn_tools = _router.tools(_tool_ctx)
        # KICKOFF = saludo PURO, sin tools (fix 2026-07-19): el texto del kickoff ("Salúdame en 1-2 frases, cálido y
        # breve…") lo interpretaba el modelo como `set_style_directive` → guardaba una regla y respondía "Hecho." en
        # vez de saludar. El saludo no necesita ninguna tool → no las ofrecemos y no hay nada que mis-rutear.
        if first_turn:
            _turn_tools = []
        # SELECCIÓN PROGRESIVA (V2-096 F2): el turno lleva la DIRECCIÓN hacia la que va, no el catálogo entero.
        # «Cuando alguien dice "hola, ¿qué tal?" no le vamos a mandar todos los widgets, todas las tools.»
        # Va DESPUÉS del gate por estado (que decide qué capacidades EXISTEN) porque son cosas distintas: el gate
        # niega, esto solo recupera candidatos — y por eso puede mirar las palabras del turno sin romper el
        # invariante de V2-085. Medido sobre los 14 casos del nodo 2.13: **−51,4% de chars de catálogo** y CERO
        # casos que se queden sin ninguna tool aceptable.
        _tool_report: dict = {}
        # V2-726 A5: no Jev verdict enters here any more. The force set is the caller's own
        # (`_force_families`, set by `need_capability`), and `select_for_turn` is off by default
        # since F0a — a full stable catalog caches its ~6.000 tokens from the second turn on.
        if not first_turn:
            try:
                from nucleo.flash import tool_selection as _tsel
                _force_fams = set(getattr(self, "_force_families", None) or ())
                _turn_tools, _tool_report = _tsel.select_for_turn(
                    _turn_tools, turn_text=text, window=getattr(brain, "_window", None),
                    recent_families=getattr(brain, "_recent_tool_families", None),
                    force=_force_fams or None)
                if _tool_report.get("omitted"):
                    emit("brain", "🎯 tools recortadas al rumbo del turno", role="system",
                         extra={"cat": "flash", **_tool_report})
            except Exception as e:  # noqa: BLE001
                emit("brain", "⚠️ selección de tools falló — catálogo completo", role="system",
                     extra={"cat": "flash", "err": repr(e)[:120]})
        # OBSERVABILIDAD del presupuesto de tools (V2-085): no solo cuántas — cuánto ocupan, qué familias entraron
        # y cuáles se podaron. Junto a los `sz_*`/`widgets_*` del prompt cierra el desglose completo del turno.
        try:
            llm_metrics.update(_router.tools_report(_turn_tools))
        except Exception:
            llm_metrics["n_tools_offered"] = len(_turn_tools)
        # NO en el kickoff: el saludo lo inicia zaelar (nadie espera) → un "Pues…" antes de saludar suena raro.
        # Último corte ANTES de pagar el modelo: si la frase ya creció, este fragmento no tiene nada que decir.
        if self._superseded():
            self._death_logged = True
            emit("brain", "🧩 fragmento descartado — la frase seguía", text=text[:200], role="system",
                 extra={"cat": "flash", "phase": self._phase, "spent_model": False})
            return

        # LEAD-IN FILLER (V2-529, 2026-08-31 — replaces the say-path `LeadInFiller`, V2-093/V2-114/V2-122):
        # the filler is now pre-synthesized AUDIO yielded as the first frames of the reply's OWN speech, by
        # the tts_node wrapper in `voice/engine/pipeline/agent.py`. Here we only ARM it: the wrapper fires
        # only when the model's first token is later than ZAELAR_FILLER_MS (default 1100 ms — a reply within
        # ~a second gets no filler, operator's rule), and a turn that never armed (kickoff, probe, a `say`)
        # can never sound one. The old timer/cancel lifecycle is gone: a barge-in interrupts the reply speech
        # and the filler dies with it, because it IS part of that speech.
        try:
            from voice.engine.speech import filler_audio as _filler_audio
            if _filler_audio.enabled() and not first_turn:
                _filler_audio.arm(brain, text, messages=messages, brief=_brief)  # V2-640 cover, V2-726 A2 verdict
        except Exception:
            pass
        self._phase = "generando la respuesta"
        try:
            # PLAZO DE SILENCIO — el FlashBrain NUNCA se queda parado (2026-08-10, regla dura del operador).
            # Sesión 14:08:26: 23 turnos seguidos sin respuesta durante 5 minutos. El operador llegó a preguntar
            # «¿me estás escuchando?», «¿estás operativo, sí o no?» y tampoco obtuvo nada. La medida del log:
            # turnos de 35,7 s · 31,8 s · 32,2 s y uno de 60,5 s, todos con `partial_chars=0` y `ttft=None`, o sea
            # el modelo NO emitió un solo token hablable. No era razonamiento ni contención de los workers: la
            # llamada se quedaba colgada y el único plazo que existía era el timeout de red de httpx —60 s—, una
            # eternidad en el camino de tiempo real. Mientras, cada frase nueva del operador cancelaba el turno en
            # vuelo, así que el siguiente empezaba de cero: inanición perfecta, el sistema no podía contestar nunca.
            # El plazo se mide sobre el SILENCIO, no sobre la duración total: cada trozo hablable lo reinicia, así
            # una respuesta larga y legítima se transmite entera y solo se corta lo que de verdad no avanza.
            # EL PLAZO MIDE QUE EL STREAM NO AVANZA, no que no salga voz (corregido 2026-08-12, con tres turnos
            # SANOS muertos en dos minutos). Un turno cuya respuesta es una ACCIÓN —«muéstrame los resultados»,
            # «cierra eso»— no emite NI UN carácter hablable: los chunks de la tool-call los consume `stream()` sin
            # yieldear nada, así que desde aquí un turno de acción y un modelo colgado se veían IGUAL. Medido en el
            # corte de las 13:49: `ttft=1.50s` —el modelo había contestado en segundo y medio— con `spoken_chars=0`;
            # el plazo lo mataba a los 9 s, el operador oía «se me ha ido un momento» y seguía sin ver sus
            # resultados. Ahora `fast_client` sella `last_chunk_ts` en CADA chunk y aquí se consulta antes de
            # declarar nada: un stream que avanza es un turno vivo, aunque calle.
            #
            # Y se recorre con una TAREA BOMBA en vez de un `wait_for` sobre `__anext__()`: cancelar un `__anext__`
            # a mitad y llamar luego a `aclose()` deja el generador en un estado indefinido —carrera conocida, y
            # candidata a los cuelgues del hilo de voz—. Cancelar la TAREA sí es limpio: es la única dueña del
            # `async for`, y el `finally` de `stream()` cierra y dispara sus tool-calls acumuladas igual que en
            # cualquier otro cierre.
            _quiet_ms = _turn_budget_ms()
            _chunks: asyncio.Queue = asyncio.Queue()
            _stream = FastClient().stream(messages, spec=spec, tools=_turn_tools,
                                          on_tool_call=_on_tool_call, metrics=llm_metrics)

            async def _pump() -> None:
                try:
                    async for _d in _stream:
                        await _chunks.put(("d", _d))
                except asyncio.CancelledError:
                    raise
                except BaseException as _e:  # noqa: BLE001
                    await _chunks.put(("err", _e))
                    return
                await _chunks.put(("end", None))

            _pump_task = asyncio.create_task(_pump(), name="flash-stream-pump")
            try:
                while True:
                    try:
                        _kind, _val = await asyncio.wait_for(_chunks.get(), timeout=_quiet_ms / 1000.0)
                    except asyncio.TimeoutError:
                        # ¿Llega algo por debajo (argumentos de una tool-call)? Entonces NO es un atasco.
                        if stream_advancing(llm_metrics, _quiet_ms):
                            continue
                        # Atasco de verdad: ni texto ni chunks. Se trata como fallo del cerebro (rama `errored`):
                        # frase corta y honesta + aviso — nunca un minuto de silencio que parece un cuelgue.
                        errored = True
                        stalled = True
                        err_exc = None
                        err_text = f"flash brain stalled: {_quiet_ms} ms sin un solo chunk"
                        emit("brain", "⏱️ turno ATASCADO — el modelo no emitía nada, lo corto", role="system",
                             extra={"cat": "flash", "quiet_ms": _quiet_ms, "spoken_chars": len("".join(spoken)),
                                    "chunks": int(llm_metrics.get("chunks") or 0), "phase": self._phase})
                        break
                    if _kind == "err":
                        raise _val
                    if _kind == "end":
                        break
                    delta = _val
                    buf += delta
                    if delta:
                        _quiet_ms = _turn_budget_ms()      # hay avance real → el plazo se renueva
                    send(speech.inline(take(False)))
            finally:
                if not _pump_task.done():
                    _pump_task.cancel()
            if not errored:
                send(speech.sanitize(take(True), drop_metadata=False))
        except asyncio.CancelledError:
            # BARGE-IN / turno superpuesto: el stream se cancela. NO reinyectamos la respuesta parcial a la ventana
            # (el `raise` salta el append de más abajo) → sin respuestas zombie. PERO lo que dijo el OPERADOR sí se
            # conserva (fix 2026-08-02): cancelar la RESPUESTA no borra la FRASE, y hasta hoy el `raise` se llevaba
            # por delante el turno de usuario → el siguiente turno llegaba al modelo sin el contexto que el operador
            # acababa de dar (ver dialog.push_user para el caso real de la piscina). Coalesce por prefijo, así los
            # trozos acumulativos del STT no duplican la frase.
            _dialog.push_user(brain._window, text)
            del brain._window[:-_WINDOW_MAX]
            if not "".join(spoken):
                _acc_mod.unanswered_by(brain, text)   # V2-776 D0 — cut before its first word
            # El relleno de ESTE turno se va con él: es audio DENTRO de la locución de la respuesta (V2-529),
            # así que el barge-in que cancela el turno lo corta también — sin lifecycle propio que cancelar.
            self._death_logged = True   # ya se relata aquí, con métricas; la envoltura de `_run` no duplica
            emit("brain", "✂️ turno cancelado (barge-in/overlap)", role="system",
                 extra={"cat": "flash", "partial_chars": len("".join(spoken)),
                        "ttft_ms": first_ms, "cut_after_ms": round((time.time() - t0) * 1000)})
            raise  # barge-in
        except Exception as e:
            errored = True
            err_text = str(e)
            err_exc = e          # V2-758: the EXCEPTION, not only its text — see `provider_failure.is_engine_fault`
            logger.warning(f"nucleo fast brain error (not spoken raw): {e}")
        if errored:
            # DEGRADED: sin Hermes al que caer — frase de reserva segura (nunca el error crudo, nunca mudo).
            # CLASIFICA el error (V2-043): SIN SALDO/cuota (credit) · credencial (auth) · caída (outage) — así el
            # diálogo de estado muestra la alerta REAL en vez de un genérico "no responde". Fail-open a "error".
            # UN TURNO ATASCADO NO ES «EL CEREBRO ESTÁ CAÍDO» (fix 2026-08-12). El plazo de silencio reutilizaba esta
            # rama entera, así que un corte aislado —del que la sesión se recupera al turno siguiente— pintaba el ◉ en
            # rojo con «no responde» y gritaba «Cerebro rápido caído». Visto en vivo: el modelo contestaba bien antes y
            # después, y el operador se queda mirando un LLM en rojo que funciona. Se distingue el HECHO (este turno no
            # salió, y eso hay que decirlo) del DIAGNÓSTICO (el proveedor está caído, que es otra cosa y más grave).
            # V2-252 — la DECISIÓN (¿atasco o fallo duro? ¿a qué escalón se releva? ¿queda alguno?) vive ahora en
            # `nucleo/flash/provider_failure.py`, compartida con el canal de TEXTO. Estaba escrita dos veces y esa
            # duplicación mordió tres veces: la última dejó al arnés ocho horas sin poder medir, con el texto
            # devolviendo un 402 en el mismo segundo en que el log decía «relevo a aimlapi-failover». Lo que NO se
            # comparte, a propósito, es lo que cada canal DICE: esta habla, el otro devuelve un objeto.
            # ── V2-758 · WHOSE FAULT IS THIS? ─────────────────────────────────────────────────────────────
            # Asked FIRST, because everything below assumes the provider failed. On 2026-09-23 nine turns were
            # reported to him as «Cerebro rápido caído» while DeepSeek answered perfectly: the real cause was an
            # `UnboundLocalError` of ours. Treating it as the provider's opened a cooldown on a healthy tier,
            # painted the model light, and promoted the stand-in to serve traffic the titular could have
            # served — and no failover can cure a bug of ours, because the same exception fires on the
            # stand-in too. So a fault of ours takes its own exit: no ladder, no light, and the timeline NAMES
            # the defect instead of blaming a provider that was up.
            _mine = ""
            try:
                from nucleo.flash import provider_failure as _pfail
                if _pfail.is_engine_fault(err_exc):
                    _mine = _pfail.engine_fault_line(err_exc)
            except Exception:  # noqa: BLE001
                _mine = ""
            if _mine:
                logger.error(f"FALLO INTERNO del turno rápido (el proveedor NO tiene la culpa): {err_text}")
                emit("alert", "Fallo del motor — este turno no salió. El modelo no tiene la culpa.",
                     text=_mine, extra={"cat": "flash", "engine_fault": type(err_exc).__name__})
                emit("error", "nucleo flash brain engine fault", text=_mine)
                try:
                    from voice import health_state as _hs_mine
                    _hs_mine.record("engine", "bug", _mine)
                except Exception:  # noqa: BLE001
                    pass
                send("Uf, se me ha ido un momento. ¿Me lo repites?")
                return

            _v = {}
            try:
                from nucleo.flash import provider_chain as _pchain1
                # `fast_client` may ALREADY have relayed inside this very turn and marked both tiers on the
                # way (V2-758). Marking again from here would punish the titular for a failure the stand-in
                # produced — the class of silent mis-attribution V2-307 paid for.
                if not (llm_metrics or {}).get("relayed_to"):
                    _v = _pfail.handle(err_text, role=_pchain1.ROLE_VOICE, stalled=bool(stalled), spec=spec)
                else:
                    _v = {"relay": None, "dry": _pchain1.pick(_pchain1.ROLE_VOICE) is None}
            except Exception:
                pass
            # RELAY on a HARD failure, not just a slow one (2026-08-15 addendum to V2-094): `note_slow` below
            # already relays a titular that's merely lagging, but a real provider error — no balance, bad
            # credential, an outage — used to just repeat against the same broken tier turn after turn, because
            # `note_failure` was hardcoded to the CLUSTER role. Cooldown is sticky (`pick()` is O(1)), so this
            # only needs to fire once per failure — the NEXT turn already starts on the relay.
            # V2-243/246: el cooldown, el relevo y el «¿queda alguien?» los acaba de resolver `provider_failure`
            # (un atasco REPETIDO cuenta —`note_stall`—; uno aislado es ruido). Aquí solo se lee el veredicto.
            _dry = bool(_v.get("dry")) and not stalled
            if stalled:
                emit("alert", "Un turno se atascó y lo corté — sigo operativo.", text="flash turn stalled")
            elif _dry:
                # V2-676 — the alert carries FACTS, not only prose: `blocking` tells the frontend to put a
                # full-screen notice in the operator's own language with a button into the settings. His
                # ruling: «la voz hay que pararla y bloquear a la gente… que salga en grande… y un botón que
                # abra la configuración». Composition and facts both live in `provider_chain`.
                from nucleo.flash import provider_chain as _pchain2   # ONE import, used twice in this branch
                emit("alert", "Sin proveedor de modelo — no es un tropiezo, no hay a quién preguntar.",
                     text=err_text[:200] or "provider chain exhausted", extra=_pchain2.dry_alert_extra())
            else:
                # V2-758 — the alert CARRIES the cause. It used to travel as the literal string «flash layer
                # error», so the timeline could not say why the brain fell and every diagnosis had to go
                # digging in `server.log`. His first question is always the same: «tengo que saber qué pasa…
                # identificarlo». `_relayed` says whether the stand-in was tried and failed too, which is a
                # different sentence from «the titular failed».
                _relayed_to = (llm_metrics or {}).get("relayed_to") or ""
                emit("alert", "Cerebro rápido caído — turno degradado.",
                     text=(err_text or "flash layer error")[:200],
                     extra={"cat": "flash", "relayed_to": _relayed_to,
                            "relayed_from": (llm_metrics or {}).get("relayed_from") or "",
                            "exc": type(err_exc).__name__ if err_exc is not None else ""})
            emit("error", "nucleo flash brain error")
            # V2-243 — «¿ME LO REPITES?» ES UNA MENTIRA CUANDO NO QUEDA NINGÚN PROVEEDOR. Esa frase es la
            # correcta ante un tropiezo: el siguiente intento puede ir bien. Con la cadena entera seca, el
            # siguiente intento falla igual, y el operador se queda repitiéndose a una máquina que no puede
            # contestarle — sin enterarse de lo único que lo arregla, que es suyo y no del motor.
            # Medido en producción el 2026-08-21: `Insufficient Balance` (DeepSeek, 402) dos veces, «SIN RELEVO
            # disponible», y el canario del arnés MUDO en todos los turnos hasta que él paró de medir.
            # V2-244: la composición (nombrar lo callado + su clave) vive en provider_chain.dry_chain_line.
            _line = "Uf, se me ha ido un momento. ¿Me lo repites?"
            if _dry:
                try:
                    _line = _pchain2.dry_chain_line(_pchain2.suppressed_relays())
                except Exception:
                    from i18n import langs as _lg_dry
                    _line = _lg_dry.current_language().no_model_provider
            send(_line)
            return

        # SEGUNDO VIAJE de la selección progresiva (V2-096 F2), y SOLO aquí: la recuperación se equivocó y el modelo
        # lo dijo llamando a `need_capability`. Es el precio explícito y MEDIBLE de recortar el catálogo.
        #
        # Va DESPUÉS del stream, no dentro: ese bucle tiene tarea bomba, cola y plazo de silencio, y meterle un
        # reintento a media máquina es cómo se estropea el camino caliente. Aquí el primer stream ya cerró y el modelo
        # NO le dijo nada al operador (gastó el turno en pedir la familia), así que no hay voz que deshacer: se
        # repite la misma petición con la familia cargada. UNA sola vez — si con la familia delante tampoco resuelve,
        # no es un problema de catálogo y otro viaje solo añade segundos.
        _need = getattr(self, "_need_family", "")
        if _need and not getattr(self, "_retried_tools", False) and not "".join(spoken).strip():
            self._retried_tools = True
            try:
                from nucleo.flash import tool_selection as _tsel3
                _wider, _rep2 = _tsel3.select(_router.tools(_tool_ctx), turn_text=text, force={_need})
                emit("brain", "🔁 segundo viaje con la familia que faltaba", text=_need, role="system",
                     extra={"cat": "flash", "family": _need, **_rep2})
                _again: list[str] = []
                async for _piece in FastClient().stream(messages, spec=spec, tools=_wider,
                                                        on_tool_call=_on_tool_call, metrics=llm_metrics):
                    _again.append(_piece)
                if _again:
                    # SAME buf/take seam as the primary stream — never send() raw model text. Measured live
                    # (acc5e85e, 2026-08-31): this retry sent the reply verbatim, the TTS *spoke*
                    # «[[show:mensajeria]]» aloud and no widget opened. take(True) executes+strips the tags.
                    buf = ""                       # discard any tag leftovers from the first pass
                    buf += "".join(_again)
                    _txt2 = take(True).strip()
                    if _txt2:
                        spoken.append(_txt2)
                        send(speech.sanitize(_txt2, drop_metadata=False))
            except Exception as e:  # noqa: BLE001
                emit("brain", "⚠️ el segundo viaje falló — sigo con lo que haya", role="system",
                     extra={"cat": "flash", "err": repr(e)[:120]})

        # V2-778 F1-10b — the post-stream chain lives in `nucleo/flash/post_stream.py`. The tag buffer stays
        # here (take/speak rebind it): the chain resets and feeds it through these two accessors.
        def _buf_reset() -> None:
            nonlocal buf
            buf = ""

        def _buf_add(d: str) -> None:
            nonlocal buf
            buf += d

        _ps = await _post_stream.run(
            FastClient=FastClient,
            _apply_widget_data=_apply_widget_data,
            _ask_waiting=_ask_waiting,
            _auth_pending=_auth_pending,
            _brief=_brief,
            _cover_work=_cover_work,
            _data_ops_hechas=_data_ops_hechas,
            _dialog=_dialog,
            _filler_audio=_filler_audio,
            _has_workers=_has_workers,
            _prev_pending=_prev_pending,
            _prompt_mod=_prompt_mod,
            _repeat_repair=_repeat_repair,
            _resolve_confirm=_resolve_confirm,
            _router=_router,
            _shown_ids=_shown_ids,
            _tag_emit=_tag_emit,
            _tool_fired=_tool_fired,
            _turn_op_tasks=_turn_op_tasks,
            acted=acted,
            aside=aside,
            attention=attention,
            brain=brain,
            canvas_h=canvas_h,
            clarify=clarify,
            confirm_state=confirm_state,
            cron_seen=cron_seen,
            data_done=data_done,
            emit=emit,
            escalate_req=escalate_req,
            had_pending_confirm=had_pending_confirm,
            images_req=images_req,
            listing_req=listing_req,
            llm_metrics=llm_metrics,
            music_req=music_req,
            operator_text=operator_text,
            read_req=read_req,
            recall_req=recall_req,
            reopen_req=reopen_req,
            reveal_req=reveal_req,
            search_req=search_req,
            send=send,
            speak=speak,
            spec=spec,
            speech=speech,
            spoken=spoken,
            style_fired=style_fired,
            take=take,
            text=text,
            worker_acted=worker_acted,
            _say=_say,
            _close_target=_close_target,
            _identify=_identify,
            _identify_system=_identify_system,
            _show_guard_target=_show_guard_target,
            _show_target_instance=_show_target_instance,
            with_also_named=with_also_named,
            _buf_reset=_buf_reset,
            _buf_add=_buf_add,
        )
        spoken_text, _op_text = _ps["spoken_text"], _ps["_op_text"]

        # BACKSTOP GENÉRICO — turno MUDO que no hizo NADA (qué cuenta como «hecho algo»: `turn_handled`).
        # V2-778 F1 — the end of the turn (dialog window, reply event, extra escalations, promise backstop) lives
        # in `voice/engine/llm/providers/turn_after.py`.
        _blk = await _turn_after.close_the_turn(
            send=send,
            _acc_ms=_acc_ms,
            _amap_ms=_amap_ms,
            _brief=_brief,
            _busy_at_start=locals().get('_busy_at_start'),
            _dialog=_dialog,
            _escalate_mod=_escalate_mod,
            _filler_audio=locals().get('_filler_audio'),
            _gate_ms=_gate_ms,
            _op_text=_op_text,
            _prev_pending=locals().get('_prev_pending'),
            _router=_router,
            _shown_ids=_shown_ids,
            _start_web_auth=_start_web_auth,
            _t_entry=_t_entry,
            _t_stream0=_t_stream0,
            _tool_fired=_tool_fired,
            _turn_tools=_turn_tools,
            acted=acted,
            aside=aside,
            attention=attention,
            brain=brain,
            clarify=clarify,
            confirm_state=confirm_state,
            data_done=data_done,
            deduped=deduped,
            emit=locals().get('emit'),
            escalate_req=escalate_req,
            first_ms=first_ms,
            first_turn=first_turn,
            images_req=images_req,
            listing_req=listing_req,
            llm_metrics=llm_metrics,
            music_req=music_req,
            operator_text=operator_text,
            read_req=read_req,
            recall_req=recall_req,
            reopen_req=reopen_req,
            reveal_req=reveal_req,
            search_req=search_req,
            spec=spec,
            speech=speech,
            spoken_text=spoken_text,
            style_fired=style_fired,
            system=system,
            t0=t0,
            text=text,
            timings=timings,
            worker_acted=worker_acted,
        )


# ── Los LECTORES DETERMINISTAS de intención de widget viven en `widget_intent.py` desde la pasada del
# trinquete (2026-09-02): son puros sobre el texto y no saben nada de un turno. Se reexportan porque los
# puntos de llamada de este fichero —y los tests que los alcanzan por aquí— los nombran sin prefijo.
from voice.engine.llm.providers.widget_intent import (  # noqa: E402
    _close_target, _identify, _identify_is_widget, _identify_system, _is_meta_widget_question,
    _norm_nfkd, _show_guard_target, _show_target_instance, _widget_fallback, with_also_named)

from voice.engine.llm.providers import turn_after as _turn_after  # noqa: E402 — V2-778 F1, imports this module back
