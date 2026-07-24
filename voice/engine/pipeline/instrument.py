"""Voice-session side-channels that are NOT the event log.

**Único sistema de registro = `voice.observer.emit()`** (anillo en memoria + fichero por sesión +
`timeline-latest.jsonl` + fan-out SSE por el bus). TODO evento discreto de voz (transcript, state, vad,
barge-in, métricas, errores…) se registra por ahí y de ahí lo consume la lista de /debug, el /events SSE
y el tester. Este módulo NO registra eventos: guarda solo las dos cosas que no son "logging discreto":

  * ``BootChannel`` — publica el HANDSHAKE de arranque ({type:"boot",phase} + {type:"ready"}) al canal de
    datos de la sala (topic "vl2"). Es un transporte de UI, no un log: el frontend abre el SSE SOLO tras
    ``room.connect()`` (session-lk.js), así que el boot llegaría tarde por SSE (carrera). Por eso viaja por
    el data-channel de la sala, atado a la conexión de ESTE navegador.
  * grabación ``mic_raw.wav`` — grabadora de audio OPCIONAL para depurar (gate ``ZAELAR_RECORD_MIC``), que
    tapea el stream del VAD de la sesión. Son bytes de audio, no eventos; por defecto OFF (privacidad+disco).

Antes esto era ``DebugBus``, un 2º sistema de logging paralelo al observador (su propio ``events.jsonl`` +
topic ``vl2`` con niveles/parciales que el frontend ya no consume, y doble-emisión de transcript/state). Se
unificó: el log es uno solo (observer); aquí solo queda el handshake de boot + la grabadora opcional.
"""
from __future__ import annotations

import asyncio
import json
import os
import wave

import numpy as np
from livekit.agents import vad as vadmod

from ..core.config import SETTINGS

_TOPIC = "vl2"


def _record_enabled() -> bool:
    return (os.getenv("ZAELAR_RECORD_MIC") or "").strip().lower() in ("1", "true", "yes", "on")


class BootChannel:
    """Handshake de arranque a la sala + grabación opcional de mic. NO es el log de eventos."""

    def __init__(self, room, session_id: str) -> None:
        self._room = room
        self.dir = SETTINGS.log_dir / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.recording = _record_enabled()
        self._wav = None  # abierto perezosamente al primer frame (para casar su sample rate)
        self._closed = False

    # --- boot handshake (topic vl2, canal de datos de la sala) --------------
    def boot(self, phase: str) -> None:
        """Hito de arranque ordenado; el splash «Colmena» enciende un clúster por fase."""
        self._publish({"type": "boot", "phase": phase})

    def ready(self) -> None:
        """BARRERA de init: voz viva + memoria compuesta + warm → el splash implota en el orbe."""
        self._publish({"type": "ready"})

    def _publish(self, msg: dict) -> None:
        try:
            payload = json.dumps(msg, ensure_ascii=False, default=str)
            task = asyncio.get_running_loop().create_task(
                self._room.local_participant.publish_data(payload, reliable=True, topic=_TOPIC)
            )
            # Consumir errores (p. ej. un publish tardío tras cerrar el motor) para que no salten como
            # "Task exception was never retrieved".
            task.add_done_callback(lambda t: t.cancelled() or t.exception())
        except Exception:
            pass

    # --- grabación de mic (opcional, ZAELAR_RECORD_MIC) ---------------------
    def write_audio(self, frames) -> None:
        if not self.recording:
            return
        try:
            for f in frames:
                if self._wav is None:
                    self._wav = wave.open(str(self.dir / "mic_raw.wav"), "wb")
                    self._wav.setnchannels(f.num_channels)
                    self._wav.setsampwidth(2)
                    self._wav.setframerate(f.sample_rate)
                self._wav.writeframes(bytes(f.data))
        except Exception:
            pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self._wav:
                self._wav.close()
        except Exception:
            pass


def _rms(frames) -> float:
    tot, n = 0.0, 0
    for f in frames:
        a = np.frombuffer(f.data, dtype=np.int16).astype(np.float32) / 32768.0
        tot += float(np.sum(a * a))
        n += a.size
    return (tot / n) ** 0.5 if n else 0.0


def tapped_vad(inner: vadmod.VAD, boot: BootChannel) -> vadmod.VAD:
    """VAD que delega en ``inner`` pero tapea su stream para grabar el mic (solo si ZAELAR_RECORD_MIC).

    Solo se envuelve el VAD de la sesión (el STT mantiene el suyo), así que no añade un 2º consumidor de
    audio ni altera la detección de turno. Si la grabación está OFF, agent.py usa el VAD pelado directamente
    y este wrapper ni se instancia.
    """

    class _TappedStream:
        def __init__(self, s):
            self._s = s

        def push_frame(self, frame):
            return self._s.push_frame(frame)

        def end_input(self):
            return self._s.end_input()

        def flush(self):
            return self._s.flush()

        async def aclose(self):
            return await self._s.aclose()

        def __aiter__(self):
            return self

        async def __anext__(self):
            ev = await self._s.__anext__()
            try:
                if ev.type == vadmod.VADEventType.INFERENCE_DONE:
                    boot.write_audio(ev.frames)
            except Exception:
                pass
            return ev

    class _TappedVAD(vadmod.VAD):
        def __init__(self):
            super().__init__(capabilities=inner.capabilities)

        def stream(self):
            return _TappedStream(inner.stream())

    return _TappedVAD()
