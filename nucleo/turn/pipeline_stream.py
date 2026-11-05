"""The turn's MAIN STREAM — the one model call of the turn, walked by a pump under a silence deadline (V2-851 F5:
stage of `nucleo/turn/pipeline`).

Moved out of `voice/engine/llm/providers/nucleo.py::_run_inner` with no change of behaviour: the pump, the deadline
that measures the stream's heartbeat (never the voice), the Hold (a sure ANSWER verdict or an unreadable sentence holds
the first words), the barge-in that keeps his words, the error that names its exception. After it, nothing runs the
model again (V2-851 F5): an unreadable sentence is answered with one line (`say_unread`), and a tool the model called
is said by its own round.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

from nucleo.flash import follow_up_pass as _fup
from nucleo.input import stt as _acc_mod
from nucleo.turn import pipeline_failure as _turn_failure
from nucleo.turn import route_by_verdict as _route


def hold_deadline_s(filler_audio) -> float:
    """How long the Hold may wait for a brief in flight: the lead-in filler's own deadline — the time the engine already
    treats as «he is fine without words». 0 when the channel has no filler (nothing waits)."""
    try:
        return filler_audio.delay_ms() / 1000.0 if filler_audio else 0.0
    except Exception as e:  # noqa: BLE001 — an unreadable deadline waits for nothing
        logger.debug(f"turn_unclear: the filler deadline could not be read — {e!r}")
        return 0.0


def say_unread(*, hold, marked: bool, errored: bool, window, send, emit, spoken) -> bool:
    """One line from the table when the Hold dropped the reflex words under an unreadable verdict (`hold.unread`) or the
    model called `not_understood` (`marked`) and said nothing. A turn that errored has its own line. True when said.
    No model runs: the deliberate second look went with every re-run after the main stream (V2-833 F7/F8, V2-851 F5)."""
    unread = getattr(hold, "unread", "")
    if not (unread or marked) or errored:
        return False
    if marked and not unread and "".join(spoken or ()).strip():
        return False                                   # the model's own words already ask him
    from nucleo.flash import unclear_turn as _unclear
    said = _unclear.line(window, "".join(spoken or ()))
    if said:
        send(said)
    emit("brain", "🤔 unreadable turn: one line asks him, no second look", role="system", text=said[:200],
         extra={"cat": "flash", "readable": unread or "marked"})
    return bool(said)


async def stream_the_reply(self, motor, *, FastClient, messages, spec, _turn_tools, _on_tool_call, llm_metrics, _brief,
                           send, take, _buf_add, speech, emit, brain, text, spoken, first_ms, t0, _dialog, data_done,
                           _turn_op_tasks, _filler_audio) -> dict:
    """The main stream of ONE turn. Returns `{errored, stalled, err_text, err_exc, _hold}`; a barge-in raises."""
    errored = False
    stalled = False          # se atascó UN turno (≠ el cerebro está caído) — cambia lo que se le cuenta al operador
    err_text = ""
    err_exc: BaseException | None = None   # V2-758 — the exception ITSELF: only it can say whose fault this is
    _hold = None
    try:
        # SILENCE DEADLINE (2026-08-10/12): it measures that the STREAM does not advance, not that no voice comes out
        # — an action turn yields no speakable character, so `fast_client` stamps `last_chunk_ts` on every chunk. The
        # stream is walked by a PUMP TASK (never `wait_for` on `__anext__()`): cancelling it is clean, and `stream()`'s
        # `finally` still fires its accumulated tool calls.
        _quiet_ms = motor._turn_budget_ms()
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
        # R16: under a sure ANSWER verdict the first words wait for the call; V2-833 F8: under an unreadable one too,
        # waiting for a brief in flight at most the lead-in filler's deadline (`turn_unclear.hold_deadline_s`)
        _hold = _fup.Hold(_brief, send, wait_s=hold_deadline_s(_filler_audio), route_wait_s=_route.wait_s())
        try:
            while True:
                try:
                    _kind, _val = await asyncio.wait_for(_chunks.get(), timeout=_quiet_ms / 1000.0)
                except asyncio.TimeoutError:
                    # ¿Llega algo por debajo (argumentos de una tool-call)? Entonces NO es un atasco.
                    if motor.stream_advancing(llm_metrics, _quiet_ms):
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
                _buf_add(delta)
                if delta:
                    _quiet_ms = motor._turn_budget_ms()      # hay avance real → el plazo se renueva
                _hold.say(speech.inline(take(False)))
        finally:
            if not _pump_task.done():
                _pump_task.cancel()
        if not errored:
            _hold.say(speech.sanitize(take(True), drop_metadata=False))
        await _hold.release(getattr(brain, "_turn_calls", None), data_done.get("ops"), emit, _turn_op_tasks)
    except asyncio.CancelledError:
        # BARGE-IN / turno superpuesto: el stream se cancela. NO reinyectamos la respuesta parcial a la ventana
        # (el `raise` salta el append de más abajo) → sin respuestas zombie. PERO lo que dijo el OPERADOR sí se
        # conserva (fix 2026-08-02): cancelar la RESPUESTA no borra la FRASE, y hasta hoy el `raise` se llevaba
        # por delante el turno de usuario → el siguiente turno llegaba al modelo sin el contexto que el operador
        # acababa de dar (ver dialog.push_user para el caso real de la piscina). Coalesce por prefijo, así los
        # trozos acumulativos del STT no duplican la frase.
        _dialog.push_user(brain._window, text)
        del brain._window[:-motor._WINDOW_MAX]
        if not "".join(spoken):
            _acc_mod.unanswered_by(brain, text)   # V2-776 D0 — cut before its first word
        # El relleno de ESTE turno se va con él: es audio DENTRO de la locución de la respuesta (V2-529),
        # así que el barge-in que cancela el turno lo corta también — sin lifecycle propio que cancelar.
        self._death_logged = True   # ya se relata aquí, con métricas; la envoltura de `_run` no duplica
        emit("brain", "✂️ turno cancelado (barge-in/overlap)", role="system",
             extra={"cat": "flash", "partial_chars": len("".join(spoken)),
                    "ttft_ms": first_ms(), "cut_after_ms": round((time.time() - t0) * 1000)})
        raise  # barge-in
    except Exception as e:
        errored = True
        err_text = str(e)
        err_exc = e          # V2-758: the EXCEPTION, not only its text — see `provider_failure.is_engine_fault`
        _turn_failure.log_named("nucleo fast brain error (not spoken raw)", e)
    return {"errored": errored, "stalled": stalled, "err_text": err_text, "err_exc": err_exc, "_hold": _hold}
