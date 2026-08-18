"""voice/engine/llm/providers/lead_in_filler.py — the FlashBrain's wait-filler (V2-093, extracted as its own
module V2-114, 2026-08-17), split out of `nucleo.py::_run_inner` per the operator's request to keep this concern
isolated and modular rather than inline inside the turn manager.

WHAT this is: the model's TTFT (~1.1s measured) leaves a silence that doesn't read as conversation. If the real
reply hasn't started by `delay_ms` (default 600ms, `ZAELAR_FILLER_MS`), `LeadInFiller` speaks ONE neutral,
varied "thinking" sound ("a ver…", "mmm…") in parallel — only turns that genuinely take a while get one; fast
replies stay clean.

WHY it's a separate object, not a bare coroutine: the turn manager (`nucleo.py`) needs to touch its state from
THREE different points in the turn's lifecycle — mark the real reply's first token (cuts the timer before it
fires late), cancel outright on barge-in (a turn the operator just interrupted doesn't get to keep talking over
them), and stop it once the stream ends for any reason (ok/tool-only/error, so a filler never fires after the
turn is already resolved). A `LeadInFiller` instance is created once per turn and exposes exactly those three
verbs plus `start()`.

Voice-only: `event_ch`/`emit` are turn-scoped LiveKit plumbing the probe (headless text channel) doesn't have,
so the caller only constructs this when a live session exists (kill-switch `ZAELAR_FILLER_MS=0` — `delay_ms<=0`
also short-circuits `start()`).

VISIBILITY (2026-08-18): a filler IS something the agent said out loud, so it belongs in the chat wall like
anything else — the operator's own words, "son frases que acaba de decir el agente". Its AUDIO stays out of
LiveKit's own conversation history (`proactive.ephemeral_speaker()`, `add_to_chat_ctx=False`) — that mechanism
is what caused the original bug (a filler landing AFTER an already-resolved reply, LiveKit's own item-add
ordering, not ours). The CHAT/observability visibility is instead pushed EXPLICITLY, by us, with a dedicated
`kind="filler"` so the frontend marks it distinctly from a real LLM-generated reply — see `_run()`'s final emit.
"""
from __future__ import annotations

import asyncio
import time


class LeadInFiller:
    def __init__(self, *, delay_ms: int, brain, superseded, event_ch, emit) -> None:
        self.delay_ms = delay_ms
        self.real_started = False
        self.spoken = False
        self._brain = brain
        self._superseded = superseded     # callable() -> bool: has a longer fragment of THIS utterance arrived?
        self._event_ch = event_ch         # this turn's LLMStream event channel (ChatChunk fallback path)
        self._emit = emit                 # voice.observer.emit, bound by the caller
        self._say_task: "asyncio.Task | None" = None      # the task that SPEAKS (separate from the timer below)
        self._timer_task: "asyncio.Task | None" = None

    def start(self) -> None:
        if self.delay_ms <= 0:
            return
        self._timer_task = asyncio.create_task(self._run())

    def mark_real_started(self) -> None:
        """Call on the turn's first real token. Idempotent — safe to call on every chunk."""
        if self.real_started:
            return
        self.real_started = True
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

    def cancel_for_barge_in(self) -> None:
        """A barge-in/overlap just cancelled this turn — the filler goes with it. Cancels the TASK that speaks,
        not just the timer: fire-and-forget means cancelling the timer alone doesn't stop an already-launched
        `say()`, and a turn cancelled turn's filler kept sounding AFTER the operator had already said something
        else (real incident, session 319252e7, 2026-08-15)."""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        if self._say_task is not None and not self._say_task.done():
            self._say_task.cancel()

    def stop(self) -> None:
        """The stream ended (ok/tool-only/error) — cut the timer so it can't fire a late filler for a turn that
        already resolved."""
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self.delay_ms / 1000.0)
            if self.real_started:
                return
            # ── NO SE LE HABLA ENCIMA AL OPERADOR (2026-08-15, sesión 319252e7) ─────────────────────────────
            # El relleno solo miraba si había empezado la respuesta. Medido en esa sesión: **2 de 10 rellenos
            # sonaron con el operador HABLANDO** (`user_in_flight: true` en el propio evento `say`) — y esos
            # dos son los que produjeron el síntoma que reportó: «el audio se corta, se cortan las frases antes
            # de terminarse… se está interrumpiendo la voz por procesos internos». No era el TTS cortándose:
            # era el agente arrancando a hablar encima, y el barge-in resultante cancelando el turno vivo.
            try:
                from voice import proactive as _pro
                if _pro.user_speaking():
                    self._emit("brain", "🤫 relleno omitido — el operador está hablando", role="system",
                               extra={"cat": "flash"})
                    return
            except Exception:
                pass
            if self._superseded():
                return
            from voice.engine.core import langs as _lgm
            _ph = _lgm.pick_filler(getattr(self._brain, "_last_filler", ""))
            if not _ph or self.real_started:
                return
            self._brain._last_filler = _ph
            self.spoken = True
            # actualiza el anti-eco (el mic no lo recaptura) — nunca el campo que alimenta el juez de contenido
            # dirigido (V2-105/V2-109 — reservado a la respuesta REAL, ver `nucleo.py::send()`): un filler no
            # lleva tema, y mezclarlo ahí clasificaría mal el siguiente turno del operador.
            self._brain._last_spoken = _ph
            self._brain._last_spoke_at = time.time()
            # ── FUERA DE BANDA, no por el stream del modelo (V2-093, 2026-08-14) ────────────────────────────
            # Esto empujaba un ChatChunk al stream de la respuesta, y por ahí el filler NO PODÍA SONAR NUNCA:
            # LiveKit agrega el texto del LLM con su tokenizador de frases, que solo suelta un segmento cuando
            # ve `.!?。！？` **y** el buffer pasa de 20 caracteres. Los rellenos acaban en «…» (no es fin de
            # frase para ese regex) y ninguno llega a 20 chars → cero segmentos; se quedaban retenidos hasta que
            # la respuesta real cerraba el stream y entonces se hablaban PEGADOS a ella.
            # ── AUDIO efímero, no el hablador normal (V2-114, 2026-08-17) ────────────────────────────────────
            # El OTRO registro de este mismo canal marca `add_to_chat_ctx=True` (el default de LiveKit) — un
            # filler dicho por ahí entra al historial de conversación de LIVEKIT, que dispara
            # `conversation_item_added` en un orden que LiveKit decide, no nosotros: reportado en vivo,
            # «¡Hola!…» seguido de «Déjame que mire…», el relleno colgando DESPUÉS de una respuesta que ya
            # había resuelto. `ephemeral_speaker()` (`add_to_chat_ctx=False`) saca el AUDIO de ese mecanismo por
            # completo — la visibilidad en chat/observabilidad la controlamos NOSOTROS, abajo, explícitamente.
            _spk = None
            try:
                from voice import proactive as _proactive
                _spk = _proactive.ephemeral_speaker()
            except Exception:
                _spk = None
            if _spk is not None:
                # Sin esperar hueco y sin await bloqueante: el relleno vale por sonar YA, y este task no puede
                # quedarse enganchado a la reproducción mientras el turno sigue generándose. Se guarda el
                # handle — ver `cancel_for_barge_in`.
                self._say_task = asyncio.create_task(_spk(_ph))
            else:
                from livekit.agents import utils
                from livekit.agents.llm import ChatChunk, ChoiceDelta
                self._event_ch.send_nowait(
                    ChatChunk(id=utils.shortuuid(), delta=ChoiceDelta(role="assistant", content=_ph + " ")))
            self._emit("brain", "💬 relleno de espera (lead-in)", text=_ph, role="system",
                       extra={"cat": "flash", "after_ms": self.delay_ms,
                              "path": "say" if _spk is not None else "stream"})
            # ── MURO DE CHAT, explícito y marcado (2026-08-18, pedido del operador) ───────────────────────────
            # Es una frase que el agente ACABA de decir en voz alta — pertenece al historial, igual que
            # cualquier otra. La diferencia con el camino viejo (arriba) es que este `emit` lo disparamos
            # NOSOTROS, síncronamente, en el mismo instante en que se decide el relleno — SIEMPRE antes de que
            # exista texto real de respuesta (`mark_real_started()` cancela este mismo `_run()` en cuanto llega
            # el primer token real, así que si esto se ejecuta es porque la respuesta real AÚN no existe). Eso
            # garantiza el orden correcto sin depender de LiveKit — el propio bug que esto reemplaza. `kind`
            # dedicado (`filler`, no `transcript`) para que el frontend lo marque como relleno, nunca como una
            # respuesta generada por el modelo (`frontend/app/services/sse.js`).
            self._emit("filler", "relleno", text=_ph, role="assistant", extra={"cat": "flash"})
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
