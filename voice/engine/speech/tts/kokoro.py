"""Local TTS — Kokoro, hardware-adaptive (on-machine ⇒ no per-token cost).

Two backends, picked at build like the STT (see core/accel):
  metal   → mlx-audio Kokoro in-process (Apple Silicon GPU) — ~0.3s to first audio
  fastapi → Kokoro-FastAPI over HTTP (CPU, Docker) — ~2s to first audio (fallback)

The CPU/Docker path was the latency regression (TTS first-audio ~1-2s → the "3-4s"
perceived); on Apple Silicon the Metal backend brings it back to ~0.3s. English
voices: af_heart / af_bella / am_michael. Talks to Kokoro's OpenAI-compatible
``/v1/audio/speech`` for raw PCM (24 kHz mono s16le) on the FastAPI path.

Ported from voice-lab-2 (INI-012 upgrade). zaelar keeps the operator's ⚙-picked
voice (``selected_voice``) in BOTH backends; lang code defaults to English.
"""
from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
import numpy as np
from livekit.agents import DEFAULT_API_CONNECT_OPTIONS, tts
from livekit.agents.tts import TTSCapabilities

from ...core import accel, langs
from ...core.config import SETTINGS
from ..voices import kokoro_default_voice, selected_voice
from . import registry

logger = logging.getLogger("zaelar.tts")

_SAMPLE_RATE = 24000  # Kokoro native
_NUM_CHANNELS = 1


def _voice() -> str:
    """The operator's ⚙-picked Kokoro voice IF valid for the active language; else the
    language's native default. Guarantees the voice is aligned with the language."""
    return selected_voice("kokoro") or kokoro_default_voice()


def _lang_code() -> str:
    """Kokoro lang code for the ACTIVE language (live), e.g. 'e'=Spanish, 'a'=US English."""
    return langs.current_language().kokoro_lang


class KokoroTTS(tts.TTS):
    def __init__(self) -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=False),
            sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS,
        )
        self._base = SETTINGS.kokoro_url.rstrip("/")
        self._voice = _voice()

    def synthesize(self, text: str, *, conn_options=DEFAULT_API_CONNECT_OPTIONS) -> "KokoroChunkedStream":
        return KokoroChunkedStream(tts=self, input_text=text, conn_options=conn_options)


class KokoroChunkedStream(tts.ChunkedStream):
    async def _run(self, output_emitter) -> None:
        impl: KokoroTTS = self._tts  # type: ignore[assignment]
        output_emitter.initialize(
            request_id="kokoro", sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS, mime_type="audio/pcm",
        )
        try:
            from voice.observer import emit
        except Exception:
            emit = lambda *a, **k: None
        t0 = time.time()
        await _fastapi_pcm(self._input_text, impl._voice, output_emitter)
        output_emitter.flush()
        emit("tts", "🔊 Kokoro (fastapi)", extra={"tts_ms": round((time.time() - t0) * 1000)})


class MlxKokoroTTS(tts.TTS):
    """Apple Silicon (Metal) via mlx-audio — in-process, ~0.3s to first audio."""

    def __init__(self) -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=False),
            sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS,
        )
        from mlx_audio.tts.utils import load_model

        self._model = load_model(SETTINGS.kokoro_mlx_model)
        self._voice = _voice()
        self._lang = _lang_code()   # aligned with the voice (both from the active language)
        # Warm the pipeline/model. If THIS phrase trips mlx-audio's vocoder shape
        # bug, keep the backend anyway — per-utterance FastAPI fallback covers the
        # occasional bad phrase; one bad warm must not disable Metal for the session.
        try:
            list(self._synth(langs.current_language().warm))
        except Exception as e:  # noqa: BLE001
            logger.warning("Metal TTS warm phrase tripped (%s) — backend stays (per-utterance fallback)", e)

    def _synth(self, text: str):
        for seg in self._model.generate(text=text, voice=self._voice, lang_code=self._lang, speed=1.0):
            a = np.asarray(seg.audio, dtype=np.float32)
            yield (np.clip(a, -1.0, 1.0) * 32767).astype("<i2").tobytes()

    def synthesize(self, text: str, *, conn_options=DEFAULT_API_CONNECT_OPTIONS) -> "MlxKokoroStream":
        return MlxKokoroStream(tts=self, input_text=text, conn_options=conn_options)


# In-process kokoro-onnx fallback: CPU, NO server, NO mlx vocoder bug → ALWAYS available. This is what makes local
# TTS never go mute when Metal (mlx-audio) trips its shape bug, without needing a Kokoro-FastAPI server running.
_ONNX = None
_ONNX_LANG = {"es": "es", "en": "en-us", "en-us": "en-us"}


def _onnx_model():
    global _ONNX
    if _ONNX is None:
        import os as _os
        from kokoro_onnx import Kokoro
        base = _os.path.expanduser(_os.getenv("ZAELAR_KOKORO_ONNX_DIR", "~/.cache/pipecat/kokoro-onnx"))
        _ONNX = Kokoro(_os.path.join(base, "kokoro-v1.0.onnx"), _os.path.join(base, "voices-v1.0.bin"))
    return _ONNX


def _onnx_bytes(text: str, voice: str, lang: str) -> bytes:
    samples, _sr = _onnx_model().create(text, voice=voice, speed=1.0, lang=lang)
    a = np.asarray(samples, dtype=np.float32)
    return (np.clip(a, -1.0, 1.0) * 32767).astype("<i2").tobytes()


async def _fastapi_pcm(text: str, voice: str, emitter) -> None:
    """Fetch raw PCM from Kokoro-FastAPI (CPU) and push it — the reliable fallback."""
    payload = {"model": "kokoro", "input": text, "voice": voice, "response_format": "pcm"}
    base = SETTINGS.kokoro_url.rstrip("/")
    async with aiohttp.ClientSession() as sess:
        async with sess.post(f"{base}/audio/speech", json=payload) as resp:
            resp.raise_for_status()
            async for chunk in resp.content.iter_chunked(4096):
                if chunk:
                    emitter.push(chunk)


class MlxKokoroStream(tts.ChunkedStream):
    async def _run(self, output_emitter) -> None:
        impl: MlxKokoroTTS = self._tts  # type: ignore[assignment]
        output_emitter.initialize(
            request_id="kokoro", sample_rate=_SAMPLE_RATE,
            num_channels=_NUM_CHANNELS, mime_type="audio/pcm",
        )
        try:
            from voice.observer import emit
        except Exception:
            emit = lambda *a, **k: None
        t0 = time.time()
        backend = "metal"
        # Metal is faster-than-realtime; generate fully in a thread, then push. If
        # mlx-audio's vocoder trips on a phrase (a known shape bug, ~1/6), fall back
        # to Kokoro-FastAPI for THIS utterance so audio never drops.
        try:
            chunks = await asyncio.get_event_loop().run_in_executor(
                None, lambda: list(impl._synth(self._input_text))
            )
            for c in chunks:
                output_emitter.push(c)
        except Exception as e:  # noqa: BLE001
            # Metal tripped the mlx shape bug on THIS phrase. Fall back to in-process kokoro-onnx (CPU, no server,
            # no mlx bug) so local TTS NEVER goes mute — "el software local no puede fallar". FastAPI only if onnx also fails.
            lang = _ONNX_LANG.get(langs.current_language().code, "es")
            try:
                pcm = await asyncio.get_event_loop().run_in_executor(
                    None, _onnx_bytes, self._input_text, impl._voice, lang)
                output_emitter.push(pcm)
                backend = "onnx-fallback"
                logger.info("Kokoro Metal tripped (%s) — served by in-process kokoro-onnx fallback", str(e)[:60])
            except Exception as e2:  # noqa: BLE001
                backend = "fastapi-fallback"
                logger.warning("Kokoro Metal + onnx both failed (%s / %s) — Kokoro-FastAPI fallback", e, e2)
                await _fastapi_pcm(self._input_text, impl._voice, output_emitter)
        output_emitter.flush()
        emit("tts", f"🔊 Kokoro ({backend})", extra={"tts_ms": round((time.time() - t0) * 1000)})


@registry.register("kokoro_local")
def build():
    """Metal (mlx-audio) on Apple Silicon, else Kokoro-FastAPI over HTTP."""
    pref = SETTINGS.tts_device
    want_metal = pref == "metal" or (pref == "auto" and accel.has_metal())
    if want_metal:
        try:
            t = MlxKokoroTTS()
            logger.info("local TTS backend: metal (mlx-audio %s)", SETTINGS.kokoro_mlx_model)
            return t
        except Exception as e:  # noqa: BLE001
            logger.warning("Kokoro Metal init failed (%s) — Kokoro-FastAPI fallback", e)
    logger.info("local TTS backend: fastapi (%s)", SETTINGS.kokoro_url)
    return KokoroTTS()
