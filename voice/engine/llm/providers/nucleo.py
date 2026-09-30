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
        from nucleo.flash import tool_executor as _tool_executor
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

        spoken_text = "".join(spoken).strip()

        # GUARD DETERMINISTA de SHOW puro (V2-023, ampliado 2026-07-14). "muéstrame el de mensajería" / "abre la
        # agenda" / "muéstrame el widget de fútbol": si el modelo rápido ESCALÓ (→ widget basura) o disparó
        # web_search (las palabras-tema «fútbol/resultados» ceban la búsqueda, hallazgo del test post-P1/P2) una
        # petición que en realidad es MOSTRAR un widget que YA EXISTE, lo resolvemos aquí: `_show_guard_target`
        # exige verbo de show + NO-crear + que `runtime.identify` (fuzzy por keywords, GENÉRICO) case un widget
        # real → override determinista de la tool espuria. Solo si no hubo ya una data-op efectiva.
        # Solo si el modelo emitió una tool ESPURIA (escalate/search) para lo que en realidad es MOSTRAR un widget
        # existente. (Se probó ampliarlo a CHARLA en el mar de testing 2026-07-19, pero los verbos 'pon/ver' del
        # guard colisionan con 'pon música'/'va a poner el tiempo'/'a ver si…' → hijack de web/deep/música. La cola
        # de show-promesa-en-charla la captura el Susurro, no un guard sobre-amplio.)
        if (escalate_req["v"] is not None or search_req["v"] is not None) and not acted["widget"]:
            _guard_wid = _show_guard_target(text, brain._window, brain._last_action)
            _guard_src = "grammar" if _guard_wid else "none"
            if not _guard_wid:
                # Jev show license (T-jev-show-close, shared reader `show_target.show_from_verb`):
                # a confident "show" + a real identify hit rescues a grammar miss (e.g. English
                # "show me X", whose verb the Spanish-stem grammar never sees). Anything else —
                # vetoed, unsure, unresolvable, Jev off — keeps the path below untouched.
                try:
                    _guard_wid, _guard_src = _show_target.show_from_verb(text, canvas_h)
                except Exception:
                    _guard_wid, _guard_src = None, "none"
            if _guard_wid:
                _was_search = search_req["v"] is not None
                escalate_req["v"] = None
                search_req["v"] = None
                acted["widget"] = True
                # V2-773 — a show the door SUPPRESSES (already open) is not the act: the turn's order was inside
                # the card («Open the most important one»), and `card_commission.after_show` asks for the call.
                acted["show_suppressed"] = not _cvis.present(_guard_wid, reason="turn-order", src="flash", emit=emit)
                acted["widget_id"] = acted.get("widget_id") or _guard_wid
                emit("brain", "🪟 show por guard determinista (tool espuria evitada)",
                     text=f"{_guard_wid} ({'search' if _was_search else 'escalate'}→show"
                          f"{', licencia Jev' if _guard_src == 'jev' else ''})", role="system")
                if not spoken_text:
                    try:
                        # V2-209 (impl PARALELA — cablear en AMBOS): abrir una tarjeta no es entregar un
                        # resultado. La decisión vive en `router_guards` para que los dos canales no puedan
                        # divergir.
                        from voice.engine.core import langs as _langs
                        from nucleo.flash import router_guards as _rg_show
                        spoken_text = _rg_show.show_ack(_langs.current_language(), _guard_wid)
                    except Exception:
                        spoken_text = "Aquí lo tienes."
                    send(speech.sanitize(spoken_text, drop_metadata=False))

        # Demo pass 69, B1 — his words NAME the (empty) picture viewer: the turn is the picture search, whatever tool
        # the model reached for (a listing search this time; a worker, a promise and a commission before).
        from nucleo.flash import card_commission as _cardc_pic
        _pic_named = (None if images_req["v"] is not None
                      or any(str(_w).split("::")[0] == "imagenes" for _w, _a in (data_done.get("ops") or []))
                      else _cardc_pic.picture_named_by(operator_text))
        if _pic_named:
            images_req["v"], listing_req["v"] = _pic_named, None
            escalate_req["v"], escalate_req["more"] = None, []
            emit("brain", "🎯 sus palabras nombran el visor de imágenes — la búsqueda de fotos, nada más",
                 text=_pic_named["query"][:120], role="system", extra={"cat": "flash", "tool": "show_images"})

        # GHOST-WORKER guard, plus the «Sí» that has no directive either — in `escalation_guard`.
        _eguard.drop_if_fragment(escalate_req, operator_text=operator_text, brief=_brief,
                                 last_reply=brain._last_reply or "", emit=emit)

        # V2-741 · THE THIRD RUNG — a declared action BEFORE anything may cost minutes: a catalogue of
        # videos became a worker that took 195 s to reach the `youtube:search` the brief had named.
        if escalate_req["v"] is not None and not acted["widget"] and not data_done["v"]:
            if _direct_action.take_rung(escalate_req, brief=_brief, operator_text=operator_text,
                                        emit=emit, present=_cvis.present,
                                        apply_widget_data=_apply_widget_data):
                acted["widget"] = True
            # V2-770 — the rung fills ONE key; a data-op of two («a partir de noviembre ya no hay piano» →
            # cancel_meeting {title, from}) gets one pass with the named card's fields before a worker.
            elif (_esc_owner := _direct_action.from_brief(_brief)[0]):
                from nucleo import danger as _danger_esc
                from nucleo.flash import act_repair as _act_repair_esc
                _ar = (None if _danger_esc.is_dangerous(operator_text) else   # full44 E3: + the verdict's call
                       await _act_repair_esc.call_for_promise_or_order(operator_text, str(escalate_req.get("v") or ""),
                                                                       _esc_owner, _direct_action.from_brief(_brief)[1],
                                                                       spec=spec, window=list(brain._window)))
                if _ar:
                    _cvis.present(_ar["widget_id"], reason="turn-order", src="flash", emit=emit)
                    _apply_widget_data(_ar["widget_id"], _ar["action"], _ar["payload"])
                    escalate_req["v"], escalate_req["more"] = None, []
                    acted["widget"] = True
                    emit("brain", "🎯 acción declarada en vez de un worker (segunda pasada con sus campos)",
                         text=f"{_ar['widget_id']}:{_ar['action']}", role="system",
                         extra={"cat": "flash", "widget": _ar["widget_id"], "action": _ar["action"]})
            # V2-773 — the card is CLOSED and the verdict names it from the catalogue: a commission whose answer
            # lives in one of our cards is a READ (or a declared call), never a five-minute worker. The decision
            # and its two outcomes live in `card_commission`; None keeps the worker.
            else:
                from nucleo.flash import card_commission as _cardc
                if await _cardc.before_worker(escalate_req, read_req, brief=_brief, operator_text=operator_text,
                                              spec=spec, emit=emit, present=_cvis.present,
                                              apply_widget_data=_apply_widget_data,
                                              window=list(brain._window), images_req=images_req) == "call":
                    acted["widget"] = True

        # JEV ESCALATE GATE (T-jev-escalate): a commission that SURVIVED the grammar guards gets a
        # cheap second opinion before it spends money. A confident `handle_inline` annuls it in the
        # same shape as the ghost-worker guard above; anything else keeps `v`. Only ever CLEARS —
        # every backstop below already handles `None`, so their precedence is intact.
        #
        # V2-726 A3 — AND IT NEEDS EVIDENCE NOW. We are past the model and usually past the start of
        # speech: the reply the operator just heard normally PROMISED this errand. `handle_inline`
        # says «no worker needed», not «already done», and clearing `v` on it alone produced a
        # promise with nothing behind it. The rule and the three promise detectors it reuses live in
        # `escalation_guard.annulment_verdict`; every commission ends with a DISPOSITION, emitted,
        # because one that simply disappears is the failure this whole gate was meant to prevent.
        if escalate_req["v"] is not None:
            _eguard.settle_commission(
                escalate_req, brief=_brief, operator_text=operator_text, reply="".join(spoken),
                acted=bool(acted["widget"] or data_done["v"] or listing_req["v"]
                           or music_req["v"] or search_req["v"]),
                anything_running=bool(_has_workers), emit=emit)

        # BACKSTOP PROMESA-SIN-ACCIÓN UNIFICADO 2026-07-19 (mar de testing): ante fraseo CORTÉS/subjuntivo
        # («¿podrías…?», «deberías…», «sería genial que hicieras…», «me haría falta…») el modelo CHARLA una promesa
        # («me pongo con ello», «te lo abro», «voy a poner…») SIN llamar a la tool → causa nº1 de "dice que lo hace y
        # no lo hace". Gated por la promesa en la RESPUESTA (zaelar se comprometió) → re-derivamos la intención con
        # los clasificadores DETERMINISTAS. GENERALIZA sobre todas las conjugaciones (no se parchea verbo a verbo).
        # V2-556: elegir la pasada rápida de anuncios YA es actuar (ver `listing_turn.voice_turn`).
        # The two guards themselves, and WHY they read the operator's words, live in `escalation_guard`.
        if (escalate_req["v"] is None and listing_req["v"] is None and not acted["widget"]
                and not data_done["v"] and not music_req["v"]):
            _guard_text = _eguard.escalation_text(operator_text, text)
            if _guard_text:
                search_req["v"] = None
                escalate_req["v"] = _guard_text
                emit("brain", "🧭 escalada por guard (marketplace→navegar / modificar-widget→generador)",
                     text=_guard_text[:80], role="system")

        # BACKSTOP DE AVISO PROMETIDO (V2-146, impl PARALELA con el probe — cablear en AMBOS): el modelo prometió
        # el recordatorio en PROSA y no emitió la tag, así que `scheduled_jobs.created` salió vacío mientras el
        # turno decía «te avisaré el miércoles». El ejecutor de tags funciona y el prompt lo pide con todas las
        # letras: faltaba hacerlo cuando el modelo no lo hace. Solo con un momento RESOLUBLE — la función
        # devuelve "" ante cualquier expresión que no sea inequívoca, porque un aviso mal fechado no se nota
        # hasta el día que no suena.
        if spoken_text and not cron_seen["v"]:
            try:
                # V2-153: misma función que el probe. Ver su docstring — el duplicado nació justamente de que
                # cada canal decidía por su cuenta.
                _cron = _router.dated_reminder_backstop(spoken_text, operator_text, window=brain._window)
                if _cron:
                    from nucleo import scheduler as _sched_bk
                    _r = _sched_bk.create(_cron["prompt"], _cron["schedule"], name=_cron["name"])
                    emit("cron", "⏰ aviso programado por backstop (lo prometió sin emitir la tag)"
                         if _r.get("ok") else "⚠️ schedule no reconocido",
                         text=_r.get("display") or _r.get("error") or "", role="system",
                         extra={"ok": bool(_r.get("ok")), "op": "cron.create", "backstop": True})
            except Exception:
                pass

        # BACKSTOP DEL APUNTE CON FECHA (V2-159, espejo del probe — cablear en AMBOS). La OTRA mitad del mismo
        # encargo: el caso pide las dos cosas —el compromiso registrado y el aviso— y la corrida salió con el
        # cron puesto y ninguna cita. Solo si el turno no hizo ya una data-op.
        if spoken_text and not data_done["v"]:
            try:
                _note = _router.dated_note_backstop(spoken_text, operator_text, window=brain._window)
                if _note:
                    import widgets as _w_note
                    await _w_note.dispatch_tag("widget.data", {"id": "agenda", "data": {
                        "action": "add_meeting", "payload": _note}})
                    emit("widget", "🗓️ cita apuntada por backstop (lo prometió sin emitir la data-op)",
                         text=f"{_note['date']} · {_note['title']}", role="system",
                         extra={"id": "agenda", "act": "add_meeting", "backstop": True})
            except Exception:
                pass

        # EVERY tool the model can answer with counts — demo pass 2026-09-28, I1: «show me a red ferari f40» called
        # show_images, the pictures came up, and the verdict «completed» the «empty» turn with a YouTube search too.
        _no_tool = (not acted["widget"] and not data_done["v"] and not music_req["v"] and not worker_acted["v"]
                    and escalate_req["v"] is None and search_req["v"] is None
                    and all(r["v"] is None for r in (images_req, listing_req, recall_req, read_req, reopen_req,
                                                     reveal_req)))
        _op_text = _router.operator_words(operator_text, text)   # a note is CONTEXT, never the errand
        # V2-754 — sin tool del modelo y con una ORDEN sobre una tarjeta abierta en el brief («Sí, el catálogo» →
        # `show_tab` 0,88 y «te dejo el catálogo» sobre nada): el veredicto completa el turno por la misma puerta.
        if _no_tool and not clarify["msg"] and (
                _direct_action.complete_canvas(_brief, tag_emit=_tag_emit, emit=emit, operator_text=_op_text)
                or _direct_action.complete(_brief, operator_text=_op_text, emit=emit, present=_cvis.present,
                                           apply_widget_data=_apply_widget_data)):
            acted["widget"] = True
            _no_tool = False
        # …and a data-op INSIDE a card he also told to close by its name («stop the video and close youtube»): the
        # card closes after the op (`closes_the_named_card`).
        if data_done["v"] and not clarify["msg"] and "close_widget" not in _tool_fired:
            _cn = _direct_action.closes_the_named_card(_brief, _op_text, data_done.get("ops"))
            if _cn:
                _tag_emit("close", {"id": _cn, "named": True})
                emit("brain", "🎯 el veredicto completa al modelo — close", text=_cn, role="system",
                     extra={"cat": "flash", "widget": _cn, "action": "close", "said": (_op_text or "")[:120]})
        # V2-764 — it PROMISED to act on a card the verdict names and called nothing: one pass for the call
        # (`act_repair`), before any backstop decides it was a web errand and spends a worker on it.
        # full44 M1: «Checking… Apple's up about 1.4% today, roughly $258 — pulling the chart up now.», nothing called,
        # the verdict unsure — and `promises_action` is a table of SPANISH promise forms, so an English promise never
        # opened this door. Whether the words promised or claimed an act is the repair pass's own question (its
        # prompt); the door only needs a card the turn names (`named_or_catalogue` below, "" = no pass).
        _named_by_verdict = ""     # the card the verdict (brief or late catalogue) names for this order, if any
        if (_no_tool and spoken_text and not clarify["msg"]
                and not _router.asks_for_missing_detail(spoken_text)):
            from nucleo.flash import act_repair as _act_repair, build_decision as _bd_ar
            from nucleo.flash import card_commission as _cardc_ar
            _ar_wid = _cardc_ar.named_or_catalogue(_brief, _op_text)   # V2-773: a closed card while others are open
            _named_by_verdict = _ar_wid
            if _ar_wid and _direct_action.sure_canvas(_brief) == "close":
                # the promise was to CLOSE it: the card's own close, never a data action (S4 emptied the sheet)
                _tag_emit("close", {"id": _show_target.close_target(_ar_wid)})
                acted["widget"] = True
                _no_tool = False
                emit("brain", "🔁 prometió cerrar sin tool — cierra la tarjeta", text=_ar_wid, role="system",
                     extra={"cat": "flash", "widget": _ar_wid, "action": "close"})
                _ar_wid = ""
            _ar_vo, _ar_va = _direct_action.from_brief(_brief)    # full41 E3: a refusal of the verdict's declared act
            _ar = (await _act_repair.call_for_promise_or_order(_op_text, spoken_text, _ar_wid, _ar_va if _ar_vo == _ar_wid
                                                               else "", spec=spec, window=list(brain._window)) if _ar_wid else None)
            # Demo pass 67, B1: a promise to find a wallpaper, the catalogue naming the EMPTY picture viewer, and no
            # call from the pass — the promise backstop then spent a worker. That order is the picture search.
            _pic = None if (_ar or not _ar_wid) else _cardc_ar.picture_search_for(_ar_wid, _op_text)
            if _pic and images_req["v"] is None:
                images_req["v"] = _pic
                acted["widget"] = True
                _no_tool = False
                emit("brain", "🎯 la herramienta del turno en vez de un worker (promesa sobre el visor vacío)",
                     text=f"{_ar_wid} ← show_images «{_pic['query'][:100]}»", role="system",
                     extra={"cat": "flash", "widget": _ar_wid, "tool": "show_images"})
            if _ar:
                _cvis.present(_ar["widget_id"], reason="turn-order", src="flash", emit=emit)
                _apply_widget_data(_ar["widget_id"], _ar["action"], _ar["payload"])
                acted["widget"] = True
                _no_tool = False
                emit("brain", "🔁 prometió actuar sin tool — la llamada, en una segunda pasada",
                     text=f"{_ar['widget_id']}:{_ar['action']}", role="system",
                     extra={"cat": "flash", "widget": _ar["widget_id"], "action": _ar["action"]})
                # the words did not promise it (they may have REFUSED it): what was done is said after them
                _ar_tail = _act_repair.after_the_repair(spoken_text, _router.promises_action(spoken_text),
                                                        _ar["widget_id"], _ar["action"])
                if _ar_tail:
                    send(speech.sanitize(_ar_tail, drop_metadata=False))
                    spoken_text = spoken_text + _ar_tail
        # An order on ONE card while the turn only touched OTHERS (full23 C5: «send rowan a telegram with the new
        # time» re-wrote the meeting on the agenda and the reply said «he's getting the update now» — nothing was
        # sent). The order is carried out on its card, with what the touched card holds.
        _ops_cards = {str(w).split("::")[0] for w, _a in (data_done.get("ops") or [])}
        if _ops_cards and not clarify["msg"] and "close_widget" not in _tool_fired:
            _missed = _direct_action.order_card_after_read(_brief, _op_text, next(iter(_ops_cards)))
            if _missed and _missed not in _ops_cards:
                from nucleo.flash import act_repair as _act_repair_oc
                _oc = await _act_repair_oc.call_after_read(_op_text, next(iter(_ops_cards)), _missed, spec=spec,
                                                           window=list(brain._window))
                if _oc:
                    _cvis.present(_oc["widget_id"], reason="turn-order", src="flash", emit=emit)
                    _apply_widget_data(_oc["widget_id"], _oc["action"], _oc["payload"])
                    emit("brain", "🔁 la orden era sobre otra tarjeta — la llamada, en una segunda pasada",
                         role="system", text=f"{sorted(_ops_cards)} → {_oc['widget_id']}:{_oc['action']}",
                         extra={"cat": "flash", "widget": _oc["widget_id"], "action": _oc["action"]})
        if _repeat_repair["v"] and not clarify["msg"]:
            from nucleo.flash import act_repair as _act_repair_rv
            _rv_card, _rv_seen, _rv_act = _repeat_repair["v"]
            _rv = await _act_repair_rv.call_for_repeated_view(_op_text, _rv_card, _rv_seen, _rv_act, spec=spec,
                                                               window=list(brain._window))
            if _rv:
                _apply_widget_data(_rv["widget_id"], _rv["action"], _rv["payload"])
                acted["widget"] = True
                emit("brain", "🔁 solo repitió la vista — la llamada del veredicto, en una segunda pasada",
                     text=f"{_rv['widget_id']}:{_rv['action']}", role="system",
                     extra={"cat": "flash", "widget": _rv["widget_id"], "action": _rv["action"]})
        # V2-773 — the turn SHOWED a card and promised more on it, or its show was suppressed over the open card
        # with the verdict naming an action: the show is not the act (`card_commission.after_show`).
        if acted.get("widget_id") and not data_done["v"] and not clarify["msg"]:   # a SILENT show too (M1)
            from nucleo.flash import card_commission as _cardc2
            if await _cardc2.after_show(acted, brief=_brief, operator_text=_op_text, spoken_text=spoken_text, spec=spec,
                                        emit=emit, present=_cvis.present, apply_widget_data=_apply_widget_data,
                                        window=list(brain._window)):
                data_done["v"] = True
        # An order that owes WORDS whose data-op RETURNED data (search_archive, peek…): the answer is that data
        # (`data_ops.answer_of`) — composed with it as the only source, after the op lands (bounded wait).
        _op_answer = None
        if read_req["v"] is None and escalate_req["v"] is None and _turn_op_tasks:
            from nucleo.flash import turn_brief as _tbw
            _wk, _wi = _tbw.read(_brief, _tbw.WORDS_KEY, "")
            _rk, _ri = _tbw.read(_brief, _tbw.REQUEST_KEY, "")
            from widgets import effects as _fx_ans
            _answers = any(_fx_ans.carries(_w, _a, _fx_ans.OUTPUT_ANSWER) for _w, _a in (data_done.get("ops") or []))
            if _answers or (_wi is not None and str(_wk) == "tell") or (_ri is not None and str(_rk) == "question"):
                _pend = [t for _w, t in _turn_op_tasks if not t.done()]
                if _pend:
                    await asyncio.wait(_pend, timeout=6.0)
                _got = []
                for _w, _t in _turn_op_tasks:
                    try:
                        _got.append((_w, _data_ops.answer_of(_t.result()) if _t.done() and not _t.cancelled() else {}))
                    except Exception:  # noqa: BLE001
                        pass
                _op_answer = _data_ops.answer_to_speak(_got, data_done.get("ops"))
            # The card of THIS turn already brought the answer, so a web search next to it is the second-best
            # source (full15 M1: the Apple chart was up with its price, and «the search results only gave me quote
            # pages, so I can't tell you» was what he heard). The card answers; the search does not run.
            if _op_answer is not None and search_req["v"] is not None:
                emit("brain", "🔎 la tarjeta ya trae la respuesta — la búsqueda web sobra", role="system",
                     text=f"{_op_answer[0]} ← {search_req['v'][:100]}", extra={"cat": "flash"})
                search_req["v"] = None
        # A QUESTION answered by a lens alone gets its answer read from that card (C1/Z1, `question_left_to_a_lens`).
        if _op_answer is not None:
            import json as _json_oa
            from nucleo.flash import widget_read as _wread_oa
            emit("brain", "📖 la data-op DEVOLVIÓ datos y el turno debe palabras — contesto con ellos",
                 text=f"{_op_answer[0]} ← {_op_text[:100]}", role="system", extra={"cat": "flash", "widget": _op_answer[0]})
            await speak(_wread_oa.compose_system(_prompt_mod._lang_lock(), _op_text, _op_answer[0], _op_text,
                                                 _json_oa.dumps(_op_answer[1], ensure_ascii=False, default=str)[:3500],
                                                 answered=True, on_screen=_direct_action.on_screen_now(_op_answer[0])),
                        _op_text, 220, "op answer compose")
            spoken_text = "".join(spoken).strip()
        elif read_req["v"] is None and escalate_req["v"] is None and search_req["v"] is None and not clarify["msg"]:
            from nucleo.flash import card_commission as _cardc3
            _qlens = _cardc3.question_left_to_a_lens(_brief, ops=list(_data_ops_hechas), acted=acted,
                                                     operator_text=_op_text)
            if _qlens:
                read_req["v"] = {"widget_id": _qlens, "question": _op_text}
                emit("brain", "📖 una pregunta contestada solo con una vista — leo la tarjeta y contesto",
                     text=f"{_qlens} ← {_op_text[:100]}", role="system", extra={"cat": "flash", "widget": _qlens})
        # U2 (demo passes 34-51, 2026-09-29): «Sure — putting on Like a Prayer now» and no call — an ENGLISH promise
        # of playback, read here with the same gate the branch below applies (music card open, or a music word).
        _playback = _router.promises_playback(spoken_text, _op_text, music_open=_direct_action.on_screen_now("musica"))
        if (_no_tool and spoken_text
                and (_router.promises_action(spoken_text) or _playback
                     or _direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))
                     or _direct_action.verdict_shows(_brief))
                and not _router.asks_for_missing_detail(spoken_text)):
            _win_goal = ""
            if not (_router.looks_like_create_widget(_op_text) or _router.looks_like_escalate_task(_op_text)):
                # V2-132 — la petición puede ser de HACE UNOS TURNOS: zaelar pidió el dato que faltaba (correcto),
                # el operador se lo dio, y la promesa cayó en un turno cuyo texto por sí solo no describe tarea
                # ninguna («vale, avísame»). El backstop miraba solo ESTE turno, así que no podía dispararse — y
                # la corrida se fue en ocho turnos narrando una búsqueda que nunca arrancó. Solo con NADA vivo:
                # con una tarea en marcha, «sigo con ello» es honesto y re-escalar haría el trabajo dos veces.
                #
                # V2-176: «nada vivo» era la pregunta equivocada — la que decide es «nada vivo PARA ESTO».
                # Medido en `book-hotel-night-known__es`: el encargo del hotel no escaló porque seguía vivo un
                # worker del encargo ANTERIOR, y zaelar pasó cuatro turnos diciendo «la reserva sigue en marcha»
                # sobre una tarea de Ticketmaster ya cancelada. Espejo exacto del canal de texto; el predicado es
                # compartido (`router_guards.nothing_running_for`) y es CONSERVADOR: ante la duda, se comporta
                # como antes.
                try:
                    from nucleo import dispatch as _disp_wg
                    _cand = _router.escalate_goal_from_window(brain._window, _op_text)
                    if _cand:
                        _live = [str(r.get("request") or "") for r in _disp_wg.pending_summaries()]
                        if not _disp_wg.has_active() or _router.nothing_running_for(_cand, _live):
                            _win_goal = _cand
                except Exception:
                    _win_goal = ""
            # V2-773 — …or the brief's own verdict said this order needs a worker (kickoff A1: «On it — I'll show
            # you the options» over nothing; the verb tables know «búscame», not every way of asking).
            # V2-773 (demo S1) — a «show me X» that NAMES a card we have (open, or a finished errand's closed sheet)
            # is a show, before any worker: the escalate verdict fired first and a second worker searched the
            # monitors again over their own closed sheet.
            # C1 (demo pass 52, 2026-09-29): «show me what i've got tomorrow» — the catalogue named `agenda`, `identify`
            # answered by CONTEXT with the minimized monitor sheet, and the sheet came up over the day he asked for.
            # The card the verdict names wins over a contextual guess.
            _pw = ((_named_by_verdict or _identify(_op_text))
                   if (_router.looks_like_show_strict(_op_text) or _direct_action.verdict_shows(_brief)) else "")
            if _pw:
                # V2-776 — the CARD, not the piece: a bare `results` is resolved like the tool path resolves it
                # (open instance, or the closed sheet the phrase names), or «Show me the monitors» opened the base.
                try:
                    _r_pw = _show_target_instance(_pw, _op_text, brain._last_spoken or "")
                    if not _r_pw.get("ask"):
                        _pw = _r_pw.get("id") or _pw
                except Exception:  # noqa: BLE001
                    pass
                acted["widget"] = True
                _shown_ids.add(_pw)          # V2-660: a shown card is an end state the harness verifies
                _cvis.present(_pw, reason="turn-order", src="flash", emit=emit)
                emit("brain", "🪟 show por backstop de promesa (prometió mostrar sin tool)", text=_pw, role="system")
            elif _playback:
                # BEFORE any worker or show: the song is on the player, not on the web. The query is the title the
                # words carry, never his sentence whole («no, put like a prayer» is not a song).
                music_req["v"] = {"query": _router.music_query(spoken_text, _op_text), "action": "play"}
                emit("brain", "🎵 música por backstop (prometió ponerla sin tool, en inglés)",
                     text=music_req["v"]["query"][:80], role="system")
            elif (_router.looks_like_create_widget(_op_text) or _router.looks_like_escalate_task(_op_text) or _win_goal
                    or _direct_action.verdict_escalates(_brief, answered=not _router.promises_action(spoken_text))
                    or _direct_action.order_over_a_card_left_undone(_brief)):
                # crear widget (o sinónimo: panel/gadget) = código → escala; marketplace/informe = navegador → escala
                escalate_req["v"] = _win_goal or _op_text
                emit("brain", "🧭 escalada por backstop (prometió crear/gestionar sin escalar)",
                     text=(_win_goal or _op_text)[:80], role="system")
            elif _router.looks_like_show_strict(_op_text):    # it named no card: a TAB of the wall, or nothing
                _wtab = _wall_tab_for(_identify_system(_op_text), _op_text)
                if _wtab:
                    # V2-761 — it named a TAB of the wall («te abro el panel de apps», nothing called).
                    acted["widget"] = True
                    emit("panel", "open", extra={"tab": _wtab, "src": "flash"})
                    emit("brain", "🗂️ panel por backstop de promesa (prometió abrirlo sin tool)", text=_wtab,
                         role="system")
            elif _router.promises_music(spoken_text):     # 'voy a poner algo de rock' sin tool → reproduce
                music_req["v"] = {"query": _op_text, "action": "play"}
                emit("brain", "🎵 música por backstop (prometió poner música sin tool)", text=_op_text[:80], role="system")

        # BACKSTOP DE TRABAJO DEVUELTO (V2-142). Distinto del de promesa: aquí el modelo no promete nada, MANDA
        # AL OPERADOR a buscar en Google/Maps lo que él acaba de pedir. Medido en `reorder-prescription`: «¿puedes
        # buscar tú el teléfono?, para eso te pido ayuda» → «la forma más fiable es que tú busques "farmacia" en
        # Google Maps y me pases el teléfono». Una regla de prompt no basta: lo que hace falta es HACER la
        # búsqueda. Solo si NADA corre (con una tarea viva la frase puede ser una sugerencia mientras se trabaja,
        # y re-escalar duplicaría el trabajo, V2-123).
        if (_no_tool and spoken_text and escalate_req["v"] is None
                and _router.hands_public_lookup_back(spoken_text)):
            try:
                from nucleo import dispatch as _disp_hb
                _busy = _disp_hb.has_active()
            except Exception:
                _busy = False
            if not _busy:
                escalate_req["v"] = _router.escalate_goal_from_window(brain._window, _op_text) or _op_text
                emit("brain", "🧭 escalada por backstop (devolvió la búsqueda al operador)", text=_op_text[:80], role="system")

        # BACKSTOP DETERMINISTA de CIERRE corto (sesión 22:40 2026-07-16): «Vale, ciérralo» → el modelo respondió
        # "Listo, cerrado" SIN emitir [[close]] ni tool alguna — la tarjeta quedó abierta y el operador tuvo que
        # repetirlo (T10 muteó, luego "no se está cerrando nada"). Orden CORTA que es claramente CERRAR (verbo de
        # cerrar, sin verbo de borrar, ≤5 palabras — `looks_like_close`, mismo guard que cerrar≠borrar) y el turno
        # NO cerró nada → cerramos AQUÍ: el widget que nombre el texto, o el ÚNICO abierto. Con varios abiertos y
        # sin nombre no adivinamos ("cierra todo" ya lo cubre `hard_interrupt`). Post-stream (la voz ya salió):
        # la lectura µs de `state.open_widgets` no toca la latencia del turno.
        # AMPLIADO (sesión absurda 2026-07-19): «Cierra el widget de música. Has puesto un videoclip…» (>5 palabras,
        # con queja) NO cazó el guard corto → el modelo ESCALÓ, y una escalada de "cerrar" cayó en el worker de
        # MODIFICAR código («modificando el widget musica…»), que giró 3 min leyendo fuentes mientras zaelar repetía
        # "sigo procesando el cierre" e ignoraba "ya está cerrado". Cerrar un widget NUNCA es tarea de código
        # (V2-017). Por eso: si hay verbo de CERRAR (sin borrar/crear) Y se NOMBRA un widget ABIERTO concreto,
        # cerramos AQUÍ aunque el turno sea largo, y CANCELAMOS cualquier escalada que el modelo haya pedido.
        # guardas contra verbos AMPLIOS ('apaga/quita'): si el turno ya disparó MÚSICA ('apaga la música'=stop
        # audio) o una data-op ('quita la tarea X'), NO cerramos el widget además (evita doble-acción).
        # BUG real 2026-07-23: "quita la pantalla completa" (verbo amplio 'quita' + turno corto + 1 solo widget
        # abierto) disparaba ESTE backstop y CERRABA el widget entero — el operador solo quería salir de
        # fullscreen. `fullscreen_widget` YA resolvió la intención real este turno; no lo pisa un cierre espurio
        # (mismo criterio que música/data-op de arriba: una acción real explícita gana sobre el backstop genérico).
        # V2-600 (2026-09-05): the fullscreen guard used to depend on the MODEL having called fullscreen_widget
        # this turn (`_tool_fired`). Measured live (session 3050e623): the operator's complaint «te he dicho que
        # cerraras la pantalla completa, no que cerraras el widget del vídeo» — a turn where the model called
        # nothing — matched the close verb + named widget and this backstop closed `youtube` AGAIN, twice, while
        # he was describing the first wrongful close. A turn that MENTIONS fullscreen is about a screen state
        # (leaving it, or narrating it), never a whole-widget close order for a backstop to guess at; if the
        # operator really wants it closed the model can still emit [[close]] itself.
        # V2-759 — «Y sal de pantalla completa.» → «Ya está, fuera de pantalla completa.» with NOTHING called,
        # for the second time (V2-609 was the first). Completed here only when a card IS covering the screen
        # and the existing licence reads the turn as leaving — see `show_target.fullscreen_exit_backstop` for
        # why that is safe. It runs BEFORE the close backstop and marks the tool as fired, so a turn that is
        # about leaving full screen can never be read below as an order to close the whole widget.
        try:
            if _show_target.fullscreen_exit_backstop(
                    _bnotes.operator_half(text), fired="fullscreen_widget" in _tool_fired,
                    tag_emit=_tag_emit, emit=emit):
                _tool_fired.add("fullscreen_widget")
        except Exception:  # noqa: BLE001 — a backstop never adds an exception to a turn
            pass
        if (not acted.get("closed")) and _canvas_lic.close_license(text, brief=_brief) \
                and not _router.looks_like_create_widget(text) \
                and not music_req["v"] and not data_done["v"] \
                and "fullscreen_widget" not in _tool_fired \
                and not attention.mentions_fullscreen(text):
            try:
                from memory import api as _memapi
                _openw = list((_memapi.state() or {}).get("open_widgets") or [])
            except Exception:
                _openw = []
            _cw = None
            # THE VERDICT NAMES THE CARD before any word match does (demo pass 2026-09-28, V7: «ok stop the video
            # and close it» — the video was already closed, «video» then tied navegador↔youtube, «the open one
            # wins» picked the worker's browser card, and the backstop closed THAT). Already closed → nothing to do.
            _vc = _direct_action.verdict_card(_brief) if _direct_action.sure_canvas(_brief) == "close" else ""
            try:
                from widgets import runtime as _rt_close
                # los ABIERTOS desempatan ("cierra el vídeo": vídeo empata navegador↔youtube; gana el abierto)
                _idc = ({"match": _vc if _vc in _openw else ""} if _vc
                        else (_rt_close.identify(text, open_ids=_openw) or {}))
                # NOMBRE resuelto y NO ambiguo = cerramos aunque el turno sea largo (señal fuerte: cerrar + widget
                # nombrado). No exigimos que esté en open_widgets: el frontend puede no haberlo reportado y cerrar
                # uno ya cerrado es no-op inofensivo; el valor real es CANCELAR la escalada espuria.
                if not _idc.get("ambiguous"):
                    _cw = _idc.get("match")
            except Exception:
                _cw = None
            # sin nombre resuelto: solo el caso corto genérico ("ciérralo") con un único widget abierto.
            if not _cw and not _vc and _closeg.is_short_order(text) and len(_openw) == 1:
                _cw = _openw[0]
            if _cw:
                _t = _close_target(_cw, text)
                if _t["ask"]:                           # V2-259 F3
                    clarify["msg"] = _t["ask"]
                    emit("brain", "❓ cerrar: varias tarjetas abiertas", text=_cw, role="system",
                         extra={"options": _t["options"]})
                    if escalate_req["v"] is not None:
                        escalate_req["v"] = None
                    _cw = None
            if _cw:
                acted["widget"] = True
                acted["closed"] = True
                for _cid in with_also_named(_t.get("ids") or [_t["id"] or _cw], text):
                    emit("widget", "close", extra={"id": _cid, "src": "flash"})
                    _canvas_lic.note_operator_close(_cid)                     # V2-650b
                emit("brain", "🙈 close por backstop (cerrar widget nombrado sin [[close]])",
                     text=_cw, role="system")
                # cerrar un widget NO es tarea de worker → cancela la escalada espuria (evita el bucle de 3 min)
                if escalate_req["v"] is not None:
                    escalate_req["v"] = None
                    emit("brain", "🚫 escalada de cierre cancelada (cerrar ≠ tarea de código)", role="system")

        # REVELAR UN SECRETO (V2-060): el operador pidió un secreto guardado (reveal_secret). El valor se descifra
        # FUERA del event loop y se entrega OUT-OF-BAND: NUNCA entra en un prompt del modelo NI en el observer/logs.
        # En F1b zaelar IDENTIFICA el secreto y confirma/pide passphrase por voz (SIN el valor); el valor lo sirve la
        # API `/api/vault/reveal` (loopback) al frontend/tester. (Lectura del valor POR VOZ con redacción = F2.)
        if reveal_req["v"] is not None and escalate_req["v"] is None:
            _lblq = reveal_req["v"]
            emit("brain", "🔐 reveal_secret", text=_lblq, role="system")
            from nucleo.turn import vault_gate as _vgate
            _rv = await _vgate.reveal(_lblq)
            for _k, _lb, _ex in _rv.events:
                emit(_k, _lb, role="system", extra=_ex)
            buf = ""   # descarta restos de tags del 1er pase
            send(speech.sanitize(_vgate.voice_line(_rv), drop_metadata=False))
            spoken_text = "".join(spoken).strip()

        # RECALL DE MEMORIA por tool (V2-056): ruta LIGERA hermana de web_search — memory.query FUERA del event
        # loop (to_thread, V2-011) + 2º pase con los recuerdos (el modelo que el turno ya paga). Solo si el turno
        # no escaló (el worker recibe su propio dossier) ni buscó (una sola respuesta compuesta por turno).
        # LECTURA DE UN WIDGET por tool (V2-668): la ruta LIGERA hermana de recall — lo que el widget GUARDA, leído
        # por las costuras que ya publica para el prompt (`widget_read.read`) + 2º pase con ese contenido como
        # ÚNICA fuente. Sesión 53de97d4: la hora de la cita con Hacienda estaba en la agenda y el modelo no tenía
        # ninguna puerta para leerla con la tarjeta cerrada. Solo si el turno no escaló ni buscó ni reveló.
        if read_req["v"] is not None and escalate_req["v"] is None and search_req["v"] is None \
                and reveal_req["v"] is None:
            from nucleo.flash import widget_read as _wread
            # V2-773 — «Show me that time in my calendar»: a read answers in words, and the card he asked to SEE
            # stayed closed. When the verdict says the canvas should SHOW, the card comes up (`card_commission`).
            from nucleo.flash import card_commission as _cardc
            _cardc.present_if_show(read_req, brief=_brief, operator_text=operator_text, is_open=_cvis.is_open,
                                   present=_cvis.present, emit=emit)
            _cover_work("widget", _wread.cover_target(read_req["v"] or {}, operator_text))
            # A card this turn just changed is read AFTER the change lands (demo pass 2026-09-28, full11 M3: the chart
            # was switched to the Nasdaq and the read, a few ms later, answered «the only thing on the chart is Apple»).
            _rw = str((read_req["v"] or {}).get("widget_id") or "").split("::")[0]
            _pending = [t for w, t in _turn_op_tasks if str(w).split("::")[0] == _rw and not t.done()]
            if _pending:
                await asyncio.wait(_pending, timeout=6.0)
            # A read that serves an ORDER on another card (full20 C5: «send rowan a telegram with the new time» read
            # the agenda for the time) — the order is carried out with what was read, instead of a words-only pass
            # that has no tools and says it cannot.
            _after = None
            _order_card = _direct_action.order_card_after_read(_brief, _op_text, _rw)
            if _order_card:
                from nucleo.flash import act_repair as _act_repair_rd
                _after = await _act_repair_rd.call_after_read(_op_text, _rw, _order_card, spec=spec,
                                                              window=list(brain._window))
            if _after:
                _cvis.present(_after["widget_id"], reason="turn-order", src="flash", emit=emit)
                _apply_widget_data(_after["widget_id"], _after["action"], _after["payload"])
                acted["widget"] = True
                data_done["v"] = True
                emit("brain", "🔁 leyó para una orden — la llamada, con lo leído", role="system",
                     text=f"{_rw} → {_after['widget_id']}:{_after['action']}",
                     extra={"cat": "flash", "widget": _after["widget_id"], "action": _after["action"]})
            else:
                await speak(await _wread.prepare(read_req["v"] or {}, operator_text, _prompt_mod._lang_lock(), emit),
                            operator_text, 220, "read_widget compose")
                spoken_text = "".join(spoken).strip()

        # V2-728 — RECUPERAR UN ENCARGO TERMINADO. La decisión ENTERA (índice léxico → Jev → preguntar si hay
        # varios) y su descripción viven en `task_recall.voice_turn`; aquí solo lo propio del canal.
        if reopen_req["v"] is not None and escalate_req["v"] is None:
            _re = await asyncio.to_thread(_trecall.voice_turn, reopen_req["v"])
            acted["widget"] = True          # lo ATENDIMOS (abriendo o preguntando) — no cae a escalate
            if _re["show"]:
                _tag_emit("show", {"id": _re["show"]})
            elif _re["ask"]:
                clarify["msg"] = _say().ask_which_item.format(cands=_re["ask"])
            emit("brain", _re["label"], role="system", text=_re["text"], extra=_re["extra"])

        if recall_req["v"] is not None and escalate_req["v"] is None and search_req["v"] is None \
                and reveal_req["v"] is None and read_req["v"] is None:
            from nucleo.flash import second_pass as _second_v
            _cover_work("recall")
            _recall_empty_thread = await _second_v.recall_spoken(text, recall_req["v"], spec, emit, speak)
            spoken_text = "".join(spoken).strip()
            if _recall_empty_thread == "empty_thread" and not acted["widget"] and not data_done["v"]:
                # fix02: the pills came back empty on a LIVE-thread question — the compose would have narrated
                # the void as no-access. The deterministic which-message question replaces it at the clarify
                # gate below (V2-026: a hard "I don't know what you mean" never loses to invented prose).
                clarify["msg"] = _say().ask_which_item_bare

        # BÚSQUEDA WEB FACTUAL (V2-022): ruta LIGERA — se resuelve EN ESTE turno (NO es el navegador pesado del
        # SlowBrain). La búsqueda es I/O de red → FUERA del event loop (to_thread). La EXTRACCIÓN reusa el MISMO
        # modelo rápido que el turno ya paga (coste marginal ≈0): 2º pase con los snippets como contexto →
        # respuesta hablada. Proveedor por capas (calidad primero): respuesta-IA (Perplexity/Tavily) → snippets
        # (Brave) → gratis (DDG). Compartido con el SlowBrain. Ver nucleo/websearch.py.
        # V2-210 — AQUÍ NO. El backstop de «un dato del mundo no se improvisa» vive en el canal de texto
        # (`probe.py`) y este canal se queda FUERA a propósito, que es lo contrario de lo que pide la regla de
        # implementación paralela y por eso se escribe.
        #
        # La razón es una asimetría real entre los dos canales: la voz EMITE los deltas del modelo según llegan,
        # así que cuando el turno llega hasta aquí la frase inventada YA SE HA DICHO. Sustituirla es imposible y
        # añadir la versión con fuente detrás significa hablar dos veces en toda pregunta de horarios o precios
        # — una regresión en el canal del operador, cambiada por un defecto que en este canal nadie ha medido.
        #
        # El arreglo BUENO para la voz es el mismo disparo pero ANTES de generar (si la pregunta es de un dato
        # del mundo, se busca primero y el modelo compone con los resultados), que es además lo que el modelo
        # hace cuando acierta. Eso toca `_run_inner` antes del stream y quiere su propia medición de latencia.
        if search_req["v"] is not None and reveal_req["v"] is None:
            query = search_req["v"]
            emit("brain", "🔎 búsqueda web", text=query, role="system")
            _cover_work("search")     # the slowest light route measured (7.2 s end to end) — V2-669
            _t_s = time.time()
            try:
                from nucleo import websearch as _ws
                res = await asyncio.to_thread(_ws.search, query)
                ctx = _ws.format_results(res)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"web_search falló (voz sigue): {e}")
                res, ctx = {"source": "none", "results": []}, ""
            # EVIDENCIA (2026-08-10): además del proveedor y el número, se guarda QUÉ VOLVIÓ — título, URL y un
            # trozo del snippet de cada resultado, más la respuesta sintetizada si el proveedor la dio. Sin esto
            # se podía auditar que el sistema BUSCÓ, nunca si respondió con lo que traía: la fila decía «7
            # resultados» y el contenido que el modelo leyó se perdía para siempre. Presupuestada en
            # `observability.evidence` (se recorta, no se resume) y best-effort: si falla, el evento sale igual.
            _ev = {"source": res.get("source"), "ai": bool(res.get("ai")), "ms": round((time.time() - _t_s) * 1000),
                   "n": len(res.get("results", [])), **({"failure": res["failure"]} if res.get("failure") else {})}
            try:
                from observability import evidence as _evd
                _ev["evidence"] = _evd.web_results(res.get("results"))
                _ans = _evd.body(res.get("answer"))
                if _ans:
                    _ev["evidence"]["answer"] = _ans
            except Exception:
                pass
            emit("search", "🔎 resultados web", text=query, role="system", extra=_ev)
            # V2-676 — the prompt (and the REASON an empty search was empty) now lives in ONE home shared with
            # the probe channel: `flash/search_turn`. It was a parallel implementation these two files had been
            # apologising for since V2-135, and the half that was missing in BOTH is what cost the operator his
            # «don't you have access to the Internet?» turn.
            from nucleo.flash import search_turn as _st
            from nucleo import canvas_focus as _cf_s
            sys2 = _st.compose_system(operator_text, query, res, ctx,
                                      today=time.strftime("%A %d %b %Y (%Y-%m-%d)"), on_screen=_cf_s.this_turn_cards())
            await speak(sys2, operator_text or query, _st.MAX_TOKENS, "web_search compose")
            spoken_text = "".join(spoken).strip()
            # THE BACKSTOP. The prompt above forbids the sentence; this catches it when the model says it
            # anyway. Only reaches the room if it fires, and then what was already spoken is corrected — see
            # `denial_repair` for why a false claim cannot be left standing as merely "a bad answer".
            _fixed = _st.denial_repair(spoken_text, res)
            if _fixed != spoken_text:
                emit("alert", "🌐 retirada una frase que negaba tener internet",
                     text=spoken_text[:200], role="system",
                     extra={"cat": "flash", "guard": "denies_the_world", "failure": res.get("failure")})
                send(_fixed)
                spoken_text = _fixed
            brain._last_action = "search"

        # BÚSQUEDA DE ANUNCIOS (V2-556): ruta LIGERA hermana de web_search. La pasada rápida corre FUERA del
        # event loop y el MÓDULO decide solo (listing_turn.run): o hay filas reales en la hoja y este 2º pase
        # las cuenta, o él mismo ya escaló a un worker que HEREDA la hoja y este 2º pase dice honestamente que
        # la búsqueda a fondo está en marcha. Se salta si el turno además escaló (escalate_req): dos workers
        # corriendo la misma caza es exactamente el defecto del fontanero (c480413b), no una redundancia sana.
        if listing_req["v"] is not None and reveal_req["v"] is None and escalate_req["v"] is None:
            emit("brain", "🛒 búsqueda de anuncios", text=listing_req["v"]["query"], role="system")
            buf = ""   # descarta cualquier resto de tags del 1º pase antes de componer la respuesta
            _said_before = "".join(spoken).strip()
            _lsep = [bool(_said_before)]      # a second pass after spoken words starts with a space, once

            def _listing_delta(_d: str) -> None:
                nonlocal buf
                if _lsep[0] and _d.strip():
                    _d, _lsep[0] = " " + _d.lstrip(), False
                buf += _d
                send(speech.inline(take(False)))

            await _lt.voice_turn(listing_req["v"], operator_text or text, spec=spec, on_delta=_listing_delta,
                                 already_said=_said_before)
            send(speech.sanitize(take(True), drop_metadata=False))
            spoken_text = "".join(spoken).strip()
            brain._last_action = "listings"

        # MÚSICA (V2-041/V2-042): ruta LIGERA como web_search, ahora con la CADENA resolver→validar→actuar
        # (`nucleo/flash/music_flow`): intento directo → si no_track, websearch (Chromium CALIENTE del prewarm) +
        # 2º pase del modelo que el turno ya paga (extractor 'Artista - Título') → reintento. El estado del intento
        # vive en las ACTIVIDADES (buscando / sonando / sin_resolver AISLADA con intentos → el turno siguiente la
        # continúa con más datos) y cada reproducción se vuelca a memoria (source="music" → gustos/historial).
        # Todo el I/O va FUERA del event loop (to_thread, V2-011). Se dice el mensaje si (a) falló, (b) el modelo
        # no habló (nunca mudo), o (c) la cadena RESOLVIÓ otra cosa que lo dicho (validación por anuncio).
        if images_req["v"] is not None:
            # V2-457 — aquí y no en la rama de la tool: buscar es red y en el stream bloquearía el turno (V2-011).
            _parte_img, _say_img = await _image_turn.voice_turn(images_req["v"], silent=not spoken_text)
            emit("brain", "🖼️ fotos ↩", text=str(_parte_img)[:200], role="system")
            if _say_img:
                send(speech.sanitize(_say_img, drop_metadata=False))
                spoken_text = "".join(spoken).strip()

        if music_req["v"] is not None:
            mq = music_req["v"]
            emit("brain", "🎵 música", text=f"{mq.get('action')} {mq.get('query')}".strip(), role="system")
            _t_m = time.time()

            async def _extract(sys2: str, user2: str) -> str:
                """2º pase INTERNO (no se habla): mismo modelo del turno, respuesta corta y estricta."""
                out: list[str] = []
                async for d in FastClient().stream([{"role": "system", "content": sys2},
                                                    {"role": "user", "content": user2}],
                                                   spec=spec, max_tokens=40):
                    out.append(d)
                return "".join(out)

            try:
                from nucleo.flash import music_flow as _mflow
                res = await _mflow.run(mq.get("action") or "play", mq.get("query") or "", extract=_extract)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"play_music falló (voz sigue): {e}")
                res = None
            # Ejecuta el FOLLOWUP de control (volumen/pausa) tras un play/queue OK — en SECUENCIA, nunca antes
            # (bug real 2026-07-23, ver comentario en el collapse de arriba). Fail-open: si falla, el play ya
            # dicho/hecho no se deshace; solo no se aplica el ajuste.
            if music_req.get("followup") and bool(getattr(res, "ok", False)):
                try:
                    await _mflow.run(music_req["followup"]["action"], "", extract=None)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"play_music followup falló: {e}")
            ok = bool(getattr(res, "ok", False))
            msg = (getattr(res, "message", "") or "").strip()
            _extra = getattr(res, "extra", {}) or {}
            _resolved = bool(_extra.get("resolved_from"))
            emit("music", "🎵 acción de música", text=mq.get("query") or mq.get("action"), role="system",
                 extra={"provider": getattr(res, "provider", ""), "action": mq.get("action"),
                        "ok": ok, "reason": getattr(res, "reason", ""), "surface": _extra.get("surface", ""),
                        "resolved_from": _extra.get("resolved_from", ""),
                        "ms": round((time.time() - _t_m) * 1000)})
            # V2-721/V2-723 — `surface` says WHERE the audio is, never what must be on SCREEN. The door
            # checks the claim against the widget's own declaration and refuses to raise an open card.
            if ok and str(_extra.get("surface") or "") == "widget":
                _cvis.present(str(_extra.get("widget") or ""), reason="producer-mount",
                              action=mq.get("action") or "", src="flash", emit=emit)
            # No re-anunciar un no-op (F5): si la reproducción fue "ya suena eso", el modelo ya habló; no encajes
            # el "ya está sonando" salvo que el modelo callara.
            _is_noop = bool(_extra.get("noop"))
            if msg and (not ok or not spoken_text or _resolved) and not (_is_noop and spoken_text):
                _clean = speech.sanitize(msg, drop_metadata=False)
                # HIGIENE (V2-047 F11, sesión 23:15 «…sin pausa.Con esta fuente gratis…»): el msg del conector se
                # concatenaba al texto del modelo SIN separador → dos frases pegadas. Si ya hay locución y no cierra
                # con espacio/puntuación, antepón un separador.
                if spoken_text and _clean and spoken_text[-1:] not in " \n.,;:!?¡¿—-":
                    _clean = " " + _clean
                elif spoken_text and _clean and not _clean[:1].isspace():
                    _clean = " " + _clean
                send(_clean)
                spoken_text = "".join(spoken).strip()

        # RED DETERMINISTA de confirmación (V2-017): si había un borrado pendiente y el modelo NO lo resolvió por
        # tool, pero el operador dijo claramente sí/no → resuélvelo igual (no depende del LLM, como hard_interrupt).
        if had_pending_confirm and not confirm_state["handled"]:
            try:
                verdict = _wconfirm.answers_pending(text)
                if verdict:
                    _resolve_confirm(verdict == "yes")
            except Exception:
                pass

        # …y lo mismo para una TAREA irreversible parada por el confirm-gate (V2-126). MISMO clasificador
        # determinista, distinto registro: aquel resuelve una acción de widget, este re-lanza la tarea. Va
        # DESPUÉS y solo si no había confirmación de widget, para que un único «sí» no resuelva dos cosas.
        # Sin esto el gate era un callejón sin salida: nadie ponía nunca `context["confirmed"]`, así que el sí
        # del operador no tenía a qué volver y la acción quedaba parada para siempre sin decirlo.
        # …y la TERCERA puerta con la misma llave (V2-202): el navegador parado en un clic irreversible. Aquélla
        # re-lanza una tarea; ésta desbloquea un clic que está esperando AHORA MISMO dentro del navegador.
        #
        # LAS DOS SE DECIDEN JUNTAS, y ahí estaba el defecto (medido 2026-08-24). Eran dos bloques con el MISMO
        # guarda —`not had_pending_confirm and not worker_acted["v"]`, que mira la puerta de WIDGET—, así que
        # nada registraba que la de tarea acabase de resolverse: con las dos abiertas, un solo «sí» hablado
        # autorizaba LAS DOS. El comentario que había aquí decía «solo si el «sí» no ha resuelto ya otra cosa» y
        # el código no lo hacía; el `probe` sí, o sea que el espejo derivó y la prosa lo tapó. Ahora la
        # precedencia la decide `nucleo/turn/confirm_gates.py`, una vez y para los dos canales.
        if not had_pending_confirm and not worker_acted["v"]:
            from nucleo.turn import confirm_gates as _gates
            _ans = _gates.resolve_all(text)
            if _ans:
                escalate_req["v"] = None      # contesta a lo PARADO; ni abre tarea nueva ni pide nada más
                escalate_req["more"] = []
                _r = _ans.result if isinstance(_ans.result, dict) else {}
                if _ans.gate == "task":
                    emit("brain", "✅ confirmación de tarea resuelta" if _ans.yes
                         else "🚫 tarea irreversible descartada por el operador",
                         text=str(_r.get("request", ""))[:120], role="system", extra={"cat": "flash"})
                else:
                    emit("brain", "✅ clic confirmado por el operador" if _ans.yes
                         else "🚫 clic descartado por el operador",
                         text=str(_r.get("task_id", "")), role="system", extra={"cat": "flash"})

        # RED DETERMINISTA V2-038 (§v3·M): precedencia confirm > ask-activo > stop-worker. Si un worker ESPERABA
        # respuesta y el modelo NO llamó answer_worker → enruta el turno como la respuesta (el estado ya lo marcaba).
        # SOLO una "respuesta libre CORTA" (§v3·M): si el turno YA disparó otra acción (widget/búsqueda/escalada/
        # data-op), es largo, o hay un login pendiente (rango superior en la precedencia), NO se lo tragamos como
        # respuesta al worker — el modelo siempre puede enrutar explícito con answer_worker.
        # PRECEDENCIA (2026-07-17, ronda 3): si un worker ESPERA respuesta, un turno corto ES esa respuesta —
        # AUNQUE el modelo haya mis-ruteado a escalate (gpt-4o-mini escaló "sí, el jueves para dos" en vez de
        # answer_worker). Coincide con la doctrina del propio prompt (_flash_layer: "lo que diga el operador es esa
        # respuesta"). Se responde al worker Y se CANCELA la escalada espuria (no abrir una tarea nueva). No aplica
        # si el turno disparó otra acción clara (widget/data/confirm/auth) o es largo (posible tarea nueva genuina).
        if _ask_waiting and worker_acted["v"] != "answer" and not had_pending_confirm \
                and search_req["v"] is None and not acted["widget"] \
                and not data_done["v"] and not _auth_pending and len(text) <= 140:
            try:
                from nucleo import worker_api as _wapi2
                if _wapi2.answer_active_soon(text):
                    worker_acted["v"] = "answer"
                    escalate_req["v"] = None        # respondía al worker, no pedía tarea nueva → no escalar
                    if not spoken_text:
                        spoken_text = "Vale, se lo digo."
                        send(speech.sanitize(spoken_text, drop_metadata=False))
            except Exception:
                pass
        # Backstop de PARADA: hay workers vivos, el operador pidió parar trabajo y el modelo NO llamó stop_worker.
        if worker_acted["v"] not in ("stop",) and escalate_req["v"] is None:
            try:
                from nucleo import dispatch as _disp2
                # V2-773 — «Stop it and close the video widget» is about the CARD the verdict names, never the
                # errands running behind it (two were cancelled on the demo's kickoff).
                if _disp2.has_active() and _router.looks_like_stop_work(text) and not _direct_action.aims_at_a_card(_brief):
                    tids = _disp2.cancel_soon(text)
                    if tids:
                        worker_acted["v"] = "stop"
                        emit("brain", "🛑 stop worker (backstop determinista)", text=str(tids), role="system")
                        # Un kill SIEMPRE se anuncia por voz (demo 2026-07-14: se mató el worker del widget en
                        # silencio mientras la voz decía "no te he entendido" — incoherente). Si el modelo ya
                        # habló otra cosa, se AÑADE la frase; nunca un kill mudo.
                        _ack = "Vale, lo paro." if not spoken_text else " He parado esa tarea."
                        send(speech.sanitize(_ack, drop_metadata=False))
                        spoken_text = (spoken_text + _ack) if spoken_text else _ack.strip()
            except Exception:
                pass

        # Confirmación abierta este turno → la pregunta la decimos NOSOTROS, gane lo que gane el modelo.
        # Cubre borrado y data-op irreversible (V2-025).
        #
        # ⚠️ Esto exigía `not spoken_text` hasta V2-693, con el razonamiento de «si el modelo ya dijo algo,
        # ya formuló él la pregunta». Medido el 2026-09-14 en su propia sesión: pidió «limpia todo los items
        # de esta semana, menos lo de mañana a las 15h y el inicio de instituto»; el modelo llamó a
        # `agenda:clear_all`, el gate abrió la confirmación REAL («¿Vacío la agenda entera? Es permanente.»)
        # — y como el modelo había hablado, esa pregunta se calló. Lo único que él leyó fue «Clearing this
        # week from your calendar — keeping tomorrow at 15:00…»: una acción NARRADA como hecha que ni
        # siquiera se había despachado, y cuyo alcance real era el calendario entero, no la semana.
        # Su reacción es la medida del coste: «no ha funcionado la orden… necesitamos un sistema estable».
        #
        # Es exactamente la lección que el bloque de `clarify` de abajo ya aprendió el 2026-07-22 y que
        # este no heredó: una señal DETERMINISTA («esto no se ha hecho y necesito tu sí») no puede perder
        # contra una frase que el modelo se inventó. Y sustituye, no acompaña: la frase del modelo habla de
        # algo que no ha pasado, así que dejarla delante es dejar la mentira delante.
        if confirm_state.get("opened") and escalate_req["v"] is None and search_req["v"] is None:
            spoken_text = confirm_state["opened"]
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Referencia a item sin resolver (V2-026) → preguntamos SIEMPRE, aunque el modelo ya haya dicho algo.
        # Bug real (maratón de testing 2026-07-22): la condición exigía `not spoken_text` — si el turno NO
        # resolvió a qué item se refería (agenda:done:"comprar pan" cuando esa tarea nunca se creó) pero el
        # modelo YA había soltado una frase confiada ("Entendido, marca la tarea como hecha"), esa frase
        # FALSA ganaba y la pregunta real ("¿cuál? no lo tengo claro") nunca llegaba a hablarse — la señal
        # determinista de "no sé a qué te refieres" quedaba silenciada por la propia alucinación del modelo,
        # justo el "nunca mudo" que el comentario original quería garantizar. `clarify["msg"]` solo se fija
        # cuando la referencia genuinamente NO resolvió — es un hecho duro, nunca debe perder frente a lo que
        # el modelo diga por su cuenta.
        if clarify["msg"] and escalate_req["v"] is None and search_req["v"] is None:
            spoken_text = clarify["msg"]
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Data-op despachada por tool sin frase hablada (el modelo fue directo a la tool) → ack corto (no mudo).
        # V2-038 (test post-P1/P2): dos data-ops seguidas con el MISMO "Hecho." disparaban el loop-detector — se
        # elige una variante que NO repita el último ack hablado (funcional consecutivo = se dice distinto).
        # V2-633: under silent-orders (genesis default, or the operator's own rule) the SUCCESS ack stays
        # unspoken — the visible effect is the answer. Failures still speak: dispatch_and_report (V2-607)
        # and clarify/confirm above are questions and reports, not confirmations, and are not gated.
        try:
            from nucleo import style_policy as _style_ack
            _ack_allowed = _style_ack.confirm_short_actions()
        except Exception:
            _ack_allowed = True
        if data_done["v"] and not spoken_text and _ack_allowed \
                and escalate_req["v"] is None and search_req["v"] is None:
            try:
                from voice.engine.core import langs as _langs
                _lg = _langs.current_language()
                _acks = list(getattr(_lg, "data_acks", None) or (_lg.data_ack,))
                _last = _dialog.sanitize_reply(brain._last_spoken or "").strip().lower()
                spoken_text = next((a for a in _acks if a.strip().lower() != _last), _acks[0])
            except Exception:
                spoken_text = "Hecho."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # Regla de usuario fijada/retirada SIN frase hablada → ack corto (V2-046 A1, visto en el probe: la
        # RETIRADA dejaba el turno MUDO). Nunca mudo al aceptar/quitar una regla.
        if style_fired["v"] and not spoken_text and escalate_req["v"] is None and search_req["v"] is None:
            try:
                from voice.engine.core import langs as _langs
                spoken_text = _langs.current_language().data_ack
            except Exception:
                spoken_text = "Vale, lo tengo."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # SHOW/CLOSE de canvas por tag SIN frase hablada → ack corto (bug 2026-07-13: el modelo emitía [[show:agenda]]
        # sin decir nada → turno MUDO; el operador no oía NI veía nada y creía que estaba roto). Nunca mudo al abrir/
        # cerrar un widget.
        if acted["widget"] and not spoken_text and _ack_allowed \
                and escalate_req["v"] is None and search_req["v"] is None \
                and not confirm_state.get("opened") and not clarify["msg"]:
            try:
                from voice.engine.core import langs as _langs
                from nucleo.flash import router_guards as _rg_show2
                _lg_ack = _langs.current_language()
                spoken_text = (_rg_show2.show_ack(_lg_ack, str(acted.get("widget_id") or ""),
                                                  chose=str(acted.get("show_chose") or ""))
                               if acted.get("widget_id") else _lg_ack.data_ack)   # a close is not an open (S4)
            except Exception:
                spoken_text = "Aquí lo tienes."
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # V2-660/V2-658 — lo que el turno DEBE, en la costura compartida (`flash/harness_turn.py`, misma
        # llamada que el probe): una afirmación de entrega sobre una hoja VACÍA o una widget_data cortada por
        # el tope escalan con superficie documento, y la voz añade el seguimiento honesto (forma V2-572).
        try:
            _ht.note_shown(_shown_ids, _router.operator_words(operator_text, text), trace=_ht.current_trace())
            _owed = await _ht.rescue(
                spoken_text, data_done=bool(data_done["v"]), turn_text=text,
                metrics=(None if (acted["widget"] or data_done["v"] or search_req["v"] is not None
                                  or music_req["v"] is not None) else llm_metrics),
                may_escalate=(escalate_req["v"] is None and not aside["v"]))
            if _owed:
                escalate_req["v"] = _owed["request"]
                escalate_req["surface"][_owed["request"]] = _owed["surface"]
                if _owed["reason"] == _ht.OVERSIZED:
                    emit("brain", "🧾 widget_data cortada por el tope → escalada con superficie documento",
                         text=_owed["head"][:120], role="system")
                else:
                    _fix = _rg.follow_up_line()
                    send(speech.sanitize(_fix, drop_metadata=False))
                    spoken_text = (spoken_text + " " + _fix).strip()
        except Exception as _e_h:  # noqa: BLE001
            logger.warning(f"turn repairs skipped: {_e_h}")

        # Escalada sin texto hablado → frase de espera neutral (V2-029/V2-189): varía turno a turno y esquiva
        # la apertura si un filler ya sonó — en `harness_turn.holding_line`, con su historia.
        if escalate_req["v"] is not None and not spoken_text:
            spoken_text = _rg.holding_line_now(brain._window, _prev_pending,
                                               after_filler=_filler_audio.played_recently())
            send(speech.sanitize(spoken_text, drop_metadata=False))

        # BACKSTOP GENÉRICO — turno MUDO que no hizo NADA (qué cuenta como «hecho algo»: `turn_handled`).
        _typed_turn = False
        try:
            _typed_turn = attention.was_typed()
        except Exception:
            _typed_turn = False
        _tool_handled = _ht.turn_handled(
            typed=_typed_turn, widget=acted["widget"], data=data_done["v"], worker=worker_acted["v"],
            style=style_fired["v"], deduped=deduped["v"], aside=aside["v"],
            escalated=escalate_req["v"] is not None, searched=search_req["v"] is not None,
            music=music_req["v"] is not None, video=("play_video" in _tool_fired),
            images=images_req["v"] is not None,
            confirm=bool(confirm_state.get("opened") or confirm_state.get("handled")))
        if not spoken_text and not _tool_handled:
            try:
                from voice.engine.core import langs                      # V2-603: the shared decision
                spoken_text = _rg.mute_backstop(brain._window, langs.current_language(), _prev_pending,
                                                  operator_text=_op_text)
            except Exception:
                spoken_text = _say().still_on_it if _prev_pending else _say().say_again
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
        elif _ht.turn_handled(typed=_typed_turn, widget=acted["widget"], data=data_done["v"],
                              worker=worker_acted["v"], style=style_fired["v"], deduped=False, aside=False,
                              escalated=escalate_req["v"] is not None, searched=search_req["v"] is not None,
                              music=music_req["v"] is not None, video=("play_video" in _tool_fired),
                              images=images_req["v"] is not None,
                              confirm=bool(confirm_state.get("opened") or confirm_state.get("handled"))):
            # The ack closes an order that was CARRIED OUT. `_tool_handled` above is a wider question («may
            # this turn stay mute?») and says yes to a turn whose only act was a re-emitted op the anti-drag
            # guard threw away, or an aside — writing «Done.» after those records a thing that never happened,
            # and the next turn believes it (V2-773 audit: «Make it fullscreen» + a dropped replay = «Done.»).
            _dialog.record_silent_action(brain._window, _say().data_ack)
        del brain._window[:-_WINDOW_MAX]
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
            if _widget_fallback(_bnotes.operator_half(text), emit, ask=lambda m: clarify.__setitem__("msg", m), last_spoken=brain._last_spoken or ""):
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
                logger.warning(f"login fallback skipped: {e}")

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
        _fast_ms = round((time.time() - t0) * 1000)
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
            _ht.note_aside(text, attention=attention, emit=emit)
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
            emit_turn(system=system, window=_dialog.prune_window(brain._window)[-_WINDOW_MAX:], tools=_turn_tools,
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
            if _similar_pending(req, _prev_pending):
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
                    req, context={"src": "voice", "surface": _surfaces_mod.pick(escalate_req["surface"].get(req, ""),
                                                                               _surfaces_mod.from_brief(_brief)),
                                  "done_when": (escalate_req.get("done_when") or {}).get(req),   # V2-776 L1
                                  "asked": spoken_text})   # V2-655: si el turno pidió permiso, se APARCA
                emit("brain", "🧭 Flash → Brain Worker (escalada registrada)", text=req, role="system")

            # …y las tareas ADICIONALES del mismo turno (V2-118). Van DESPUÉS de la principal y solo si esta
            # sobrevivió: los guards de arriba anulan `v` cuando el turno resulta no ser una tarea (era un show,
            # un cierre, la respuesta a un worker), y en ese caso las demás tampoco lo eran. Cada una pasa por el
            # MISMO dedup que la principal — dos peticiones parecidas se inyectan en la que ya corre en vez de
            # abrir una segunda sesión de lo mismo.
            # BACKSTOP CREATE-WIDGET (V2-118 ronda 2, medido): el operador pidió TRES cosas y una era «móntame
            # un widget de un juego». El modelo llamó a la tool UNA vez, por el informe, y las otras dos se
            # quedaron sin lanzar — el registro de tareas de la corrida no tiene NI UNA de kind `code` en los 14
            # turnos, mientras el turno decía «te cargo un juego de plataformas». La capacidad de abanicar ya
            # existe (arriba); lo que falla es que el modelo pequeño no la usa de forma fiable.
            # El guard de crear-widget YA existía pero solo cuando el turno no había disparado NADA
            # (`_no_tool`): en cuanto escalaba otra cosa, la petición de widget se caía en silencio. Aquí se
            # cubre justo ese hueco, con el MISMO clasificador determinista y solo si ninguna de las peticiones
            # que van a salir es ya una de crear widget.
            # V2-155 (espejo del probe — cablear en AMBOS): se añade la CLÁUSULA que pide el widget, no el turno
            # entero. Un turno que encarga tres cosas lleva las otras dos dentro, y con «informe» dentro el
            # dedup le asigna el mismo widget destino que la tarea del informe y se la come por su señal más
            # fuerte. Ver `router_guards.create_widget_request` para la medición.
            _w_req = (_router.create_widget_request(_op_text)
                      if not any(_router.looks_like_create_widget(r)
                                 for r in [req, *escalate_req["more"]]) else "")
            if _w_req:
                escalate_req["more"].append(_w_req)
                emit("brain", "🏗️ crear-widget del mismo turno, sin lanzar → escalada añadida (backstop)",
                     text=_w_req[:120], role="system", extra={"cat": "flash"})

            _launched = list(_prev_pending) + [{"request": req}]
            for _extra_req in escalate_req["more"]:
                try:
                    if _similar_pending(_extra_req, _launched):
                        from nucleo import dispatch as _disp4
                        _disp4.inject_soon(_extra_req, _extra_req)
                        emit("brain", "↪️ tarea adicional → inyección a worker vivo", text=_extra_req, role="system")
                    else:
                        _escalate_mod.escalate_to_slowbrain(
                            _extra_req,
                            context={"src": "voice", "surface": escalate_req["surface"].get(_extra_req, ""),
                                     "asked": spoken_text})
                        emit("brain", "🧭 Flash → Brain Worker (tarea adicional del mismo turno)",
                             text=_extra_req, role="system")
                    _launched.append({"request": _extra_req})
                except Exception as _e_more:  # noqa: BLE001
                    logger.warning(f"escalada adicional falló (las demás siguen): {_e_more}")

        # Promise-without-action, and the forced escalation behind it (V2-049 + V2-534). The DECISION moved to
        # `promise_backstop.py` (architecture ratchet, same pattern as `vault_intercept.py`); `_did_act` is
        # computed ONCE above the answer guards (V2-587) — it reads nine dicts of THIS turn's closure.
        from voice.engine.llm.providers import promise_backstop as _promise_backstop
        _promise_backstop.run(spoken_text, did_act=_did_act, op_text=_op_text, prev_pending=_prev_pending,
                              emit=emit, escalate=_escalate_mod.escalate_to_slowbrain,
                              similar_pending=_similar_pending, brief=_brief)


# ── Los LECTORES DETERMINISTAS de intención de widget viven en `widget_intent.py` desde la pasada del
# trinquete (2026-09-02): son puros sobre el texto y no saben nada de un turno. Se reexportan porque los
# puntos de llamada de este fichero —y los tests que los alcanzan por aquí— los nombran sin prefijo.
from voice.engine.llm.providers.widget_intent import (  # noqa: E402
    _close_target, _identify, _identify_is_widget, _identify_system, _is_meta_widget_question,
    _norm_nfkd, _show_guard_target, _show_target_instance, _widget_fallback, with_also_named)
