"""Voice-session side-channels that are NOT the event log.

**Single logging system = `voice.observer.emit()`** (in-memory ring + per-session file +
`timeline-latest.jsonl` + SSE fan-out through the bus). EVERY discrete voice event (transcript, state, vad,
barge-in, metrics, errors…) is logged there and consumed from there by the /debug list, the /events SSE
and the tester. This module does NOT log events: it stores only the two things that are not "discrete logging":

  * ``BootChannel`` — publishes the startup HANDSHAKE ({type:"boot",phase} + {type:"ready"}) to the room's
    data channel (topic "vl2"). It is UI transport, not a log: the frontend opens the SSE ONLY after
    ``room.connect()`` (session-lk.js), so the boot would arrive too late via SSE (race condition). That is
    why it travels through the room's data channel, tied to the connection of THIS browser.
  * ``mic_raw.wav`` recording — OPTIONAL audio recorder for debugging (``ZAELAR_RECORD_MIC`` gate), which
    taps the session's VAD stream. They are audio bytes, not events; OFF by default (privacy+disk).

Previously this was ``DebugBus``, a 2nd logging system parallel to the observer (its own ``events.jsonl`` +
topic ``vl2`` with levels/partials that the frontend no longer consumes, and double emission of transcript/state).
It was unified: there is only one log (observer); only the boot handshake + optional recorder remain here.
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
    """Startup handshake to the room + optional mic recording. NOT the event log."""

    def __init__(self, room, session_id: str) -> None:
        self._room = room
        self.dir = SETTINGS.log_dir / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.recording = _record_enabled()
        self._wav = None  # opened lazily on the first frame (to match its sample rate)
        self._closed = False

    # --- boot handshake (topic vl2, room data channel) ----------------------
    def boot(self, phase: str) -> None:
        """Ordered startup milestone; the «Colmena» splash lights up a cluster per phase."""
        self._publish({"type": "boot", "phase": phase})

    def ready(self) -> None:
        """Init BARRIER: live voice + composed memory + warm → the splash implodes into the orb."""
        self._publish({"type": "ready"})

    def _publish(self, msg: dict) -> None:
        try:
            payload = json.dumps(msg, ensure_ascii=False, default=str)
            task = asyncio.get_running_loop().create_task(
                self._room.local_participant.publish_data(payload, reliable=True, topic=_TOPIC)
            )
            # Consume errors (e.g. a late publish after closing the engine) so they do not appear as
            # "Task exception was never retrieved".
            task.add_done_callback(lambda t: t.cancelled() or t.exception())
        except Exception:
            pass

    # --- mic recording (optional, ZAELAR_RECORD_MIC) ------------------------
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
    """VAD that delegates to ``inner`` but taps its stream to record the mic (only if ZAELAR_RECORD_MIC).

    Only the session's VAD is wrapped (STT keeps its own), so this adds no 2nd audio consumer
    and does not alter turn detection. If recording is OFF, agent.py uses the bare VAD directly
    and this wrapper is not instantiated.
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
