#
# NUCLEO brain (zaelar v2 «Colmena») as a LiveKit LLM provider (EPIC-v2-colmena, V2-004).
#
# FlashBrain (the OWN implementation, `nucleo/flash/`) is plugged into the voice engine through the SAME seam as
# `duo`: LLMStream reads the latest turn from ChatContext, runs FlashBrain, and emits ALREADY CLEANED ChatChunks
# (they pass through strip_tags→side-effects→speech). The engine-agnostic contract is preserved.
#
# Difference from `duo`: there is NO Hermes. Startup memory and context come from the application's own central
# memory (`memory/`, injected into the prompt by `nucleo/flash/prompt.py`). Escalation goes to
# `nucleo/acts/errand.py` (STUB in V2-004: records + publishes on the bus; the real SlowBrain arrives in
# V2-006/V2-007). Degradation does NOT fall back to Hermes—it speaks a fallback phrase.
#
# Enabled with BRAIN=nucleo (opt-in, alongside duo/hermes; zero regression until the V2-009 cutover).
#
from __future__ import annotations

import asyncio
import os
import sys
import time

from loguru import logger
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, llm, utils
from livekit.agents.llm import ChatChunk, ChoiceDelta

from .. import registry
from nucleo.turn.prompt.catalogs import wall_tab_for as _wall_tab_for
from nucleo.flash import (build_decision as _build_decision, canvas_license as _canvas_lic,  # V2-750 grammar only proposes / V2-650 a replay can be an order
                          canvas_visibility as _cvis,                          # V2-723: ONE door to present
                          close_guards as _closeg,                             # V2-635: close needs the words
                          data_ops as _data_ops, escalation_guard as _eguard,  # V2-391 / V2-677
                          direct_action as _direct_action,                     # V2-741: the third rung
                          image_turn as _image_turn,                           # V2-402
                          show_target as _show_target,                         # V2-609: one target decision
                          video_turn as _video_turn)                           # V2-556 / V2-457: no cycles
from nucleo.turn import mouth as _mouth                                       # V2-851 F5: the in-turn mouth's door entry
from nucleo.turn import task_recall as _trecall                               # V2-728: «lo del piso que te dije»
# V2-515 (ratchet): ONE import replaces eight lazy `from widgets import confirm` — confirm.py never imports voice.
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
from nucleo.input import stt as _acc_mod   # V2-776 D0: a turn that died unanswered is un-consumed
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


# V2-669: the body moved to `flash/surface_ack.saved_state_is_empty` — the SAME decision was written there too
# (`nothing_to_show`'s docstring cited this copy by name), and the ratchet asks for a module, never a taller
# ceiling. The name stays here because callers and tests reach for it through this module.
from nucleo.flash.surface_ack import saved_state_is_empty as _surface_is_empty  # noqa: E402
# V2-778 F1-10 — the turn's tool executor and post-stream chain live in their own modules.
from nucleo.flash import follow_up_pass as _fup, post_stream as _post_stream, tool_executor as _tool_executor  # noqa: E402


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
        self._turn_count = 0                # turnos conversacionales completados esta sesión (per-session turn limit)
        self._last_action = ""              # route/surface del turno anterior para referencias deícticas
        self._session_started_at = time.time()  # arranque de la sesión (per-session TTL)

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
        __import__("nucleo.acts.surface_owner", fromlist=["x"]).turn_discarded()   # V2-844 F0: what it still does
        emit("brain", "✂️ turno descartado — sin respuesta", text=text[:200], role="system",
             extra={"cat": "flash", "reason": reason, "phase": getattr(self, "_phase", "?"),
                    "text_kept": kept})

    async def _run_inner(self) -> None:
        """ONE turn — `nucleo/turn/pipeline.run`, the same pipeline the typed channel runs (V2-851 F5). This provider is
        its adapter: the stream it reads (`_chat_ctx`), the chunk it emits (`_out`), and this module handed in as the
        `motor` whose seams the pipeline reads (a patch here still governs them)."""
        await _pipeline.run(self, sys.modules[__name__])

    def _out(self, txt: str) -> None:
        """The turn's words onto the channel's stream — the in-turn mouth's last hop."""
        self._event_ch.send_nowait(ChatChunk(id=utils.shortuuid(), delta=ChoiceDelta(role="assistant", content=txt)))


def _fast_lane_mod():
    """The fast lane (action map, presence, wall tab, small talk, task list) — the motor's, read by the pipeline."""
    from voice.engine.llm.providers import fast_lane
    return fast_lane


def _filler_audio_mod():
    """The lead-in filler (pre-synthesised audio inside the reply's own speech) — the motor's, read by the pipeline."""
    from voice.engine.speech import filler_audio
    return filler_audio


# ── Los LECTORES DETERMINISTAS de intención de widget viven en `widget_intent.py` desde la pasada del
# trinquete (2026-09-02): son puros sobre el texto y no saben nada de un turno. Se reexportan porque los
# puntos de llamada de este fichero —y los tests que los alcanzan por aquí— los nombran sin prefijo.
from voice.engine.llm.providers.widget_intent import (  # noqa: E402
    _close_target, _identify, _identify_is_widget, _identify_system, _is_meta_widget_question,
    _norm_nfkd, _show_guard_target, _show_target_instance, _widget_fallback, with_also_named)

from voice.engine.llm.providers import turn_prompt as _turn_prompt  # noqa: E402 — V2-778 F1, imports this module back
from voice.engine.llm.providers import turn_tools as _turn_tools_mod  # noqa: E402 — V2-778 F1, imports this module back
from voice.engine.llm.providers import turn_fragment as _turn_fragment  # noqa: E402
from voice.engine.llm.providers import turn_errands as _turn_errands  # noqa: E402 — read by nucleo/turn/pipeline_errands
from nucleo.turn import pipeline as _pipeline  # noqa: E402 — V2-851 F5: the ONE turn, this provider is its adapter
from voice.engine.llm.providers.vault_intercept import vault_first as _vault_first  # noqa: E402 — V2-778 F1, imports this module back


# V2-778 F1 — moved to `pending_confirm.py`, imported back under their names (that module reads this one).
from .pending_confirm import (  # noqa: E402,F401
    _resolve_pending_confirm, _resolve_and_end_the_turn)
