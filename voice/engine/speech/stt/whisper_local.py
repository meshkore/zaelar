"""Local STT — Whisper, hardware-adaptive & cross-platform (no per-token cost).

At build time we pick the fastest backend the machine actually has (see
``core.accel``) and fall back down the chain if init fails:

    metal → mlx-whisper (Apple Silicon, GPU/ANE)      ~0.15s / utterance on M4
    cuda  → faster-whisper on CUDA (NVIDIA, float16)
    cpu   → faster-whisper on CPU (int8)   ← universal fallback, works everywhere

Both backends are non-streaming recognizers, wrapped in ``StreamAdapter(vad=…)``
so Silero segments speech and each segment is transcribed. To add a backend
(e.g. AMD/ROCm via whisper.cpp-Vulkan) implement one ``stt.STT`` class + a branch
in ``_make_backend`` — a welcome PR, nothing else changes.

Ported from voice-lab-2 (INI-012 upgrade); zaelar is English, so the decode
``initial_prompt`` and logger name are the only substantive local changes.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import re
import logging
import time

import numpy as np
from livekit import rtc
from livekit.agents import stt as stt_module
from livekit.agents.stt import SpeechData, SpeechEvent, SpeechEventType, STTCapabilities

from ...core import accel, langs
from ...core.config import SETTINGS
from . import registry

logger = logging.getLogger("zaelar.stt")

# Set at build() so the rest of the app can report the backend actually in use.
RESOLVED_DEVICE: str | None = None

# MLX (Apple Metal) binds its GPU stream to the OS thread that first touches it. The
# warm-up call in MlxWhisperSTT.__init__ used to run on whatever thread constructed the
# backend, while every live call went through asyncio's default executor (shared with
# every other run_in_executor(None, …)/asyncio.to_thread(...) in the app) — a pool that
# spins up new worker threads under load. A transcribe landing on a thread that never
# touched MLX's Metal stream crashes with "There is no Stream(gpu, N) in current thread."
# Pinning every call (warm-up included) to one dedicated thread keeps the stream valid.
_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="zaelar-stt")

# Anti-hallucination decode settings. Whisper invents common fillers ("Thank you.",
# "Bye.") on short/quiet segments and loops when conditioned on prior text.
# These are the standard levers to suppress that without a bigger model:
#   temperature=0 + condition_on_previous_text=False  → no runaway/repeat loops
#   no_speech_threshold + logprob/compression thresholds → drop non-speech segments
# ``initial_prompt`` is added per call from the ACTIVE language (core/langs) so
# recognition + accents track a language switch.
_DECODE = dict(
    temperature=0.0,
    condition_on_previous_text=False,
    no_speech_threshold=0.6,
    compression_ratio_threshold=2.4,
)

# Frases-alucinación conocidas de Whisper (aparecen en silencios/ruido pese al gate de energía; el modelo las
# "aprendió" de subtítulos de YouTube). Si la transcripción ES SOLO una de estas, es ruido → se descarta. Evita
# que zaelar responda a turnos fantasma ("Gracias por ver el video") y deraile la conversación. Vale para uso real.
_HALLUCINATIONS = {
    "gracias.", "¡gracias!", "gracias", "gracias por ver el video.", "gracias por ver el vídeo.",
    "gracias por ver el video", "gracias por ver el vídeo", "gracias por su atención.",
    "subtítulos realizados por la comunidad de amara.org", "subtítulos por la comunidad de amara.org",
    "¡suscríbete!", "suscríbete al canal.", "más información en www.alimmenta.com",
    "thank you.", "thanks for watching!", "thank you for watching.", "you", "bye.", ".", "so",
}


# Non-speech vocalizations: Whisper annotates a cough/sneeze/sigh/laugh either as a bracketed tag ("[cough]",
# "(sneezes)", "[música]") or as a bare onomatopoeia word. zaelar must NOT treat these as a turn (the operator
# coughs → zaelar should stay quiet, not answer "Cough."). Kept NARROW on purpose: real short replies (sí, no,
# vale, ya, ok, hola…) are NEVER here, so a genuine one-word answer is never dropped.
_NONSPEECH_WORDS = {
    "cough", "coughs", "coughing", "coughs.", "cough.", "sneeze", "sneezes", "sneezing", "sneeze.",
    "sigh", "sighs", "sighing", "sigh.", "ahem", "ahem.", "sniff", "sniffs", "sniffles", "gasp", "gasps",
    "laughs", "laughing", "laughter", "chuckles", "clears throat", "throat clearing", "grunt", "grunts",
    "tos", "estornudo", "estornuda", "suspiro", "suspira", "carraspeo", "risa", "risas", "toser", "gemido",
}
# whole transcript = only bracketed/parenthesized annotations, e.g. "[cough]", "( sneezes )", "[music] [laughter]"
_BRACKET_ONLY = re.compile(r"^[\s.\-]*(?:[\[(][^\])]*[\])][\s.\-]*)+$")


def _is_hallucination(text: str) -> bool:
    t = (text or "").strip().lower()
    if t in _HALLUCINATIONS:
        return True
    if _BRACKET_ONLY.match(t):                       # "[cough]", "(sighs)" … non-speech annotation only
        return True
    return t.strip(" .!¡?¿-") in _NONSPEECH_WORDS    # bare "Cough." / "Estornudo" etc.


def _frames_to_16k(buffer) -> np.ndarray:
    """AgentSession audio buffer → mono float32 @ 16 kHz (what Whisper expects)."""
    frame = rtc.combine_audio_frames(buffer)
    pcm = np.frombuffer(frame.data, dtype=np.int16)
    if frame.num_channels > 1:
        pcm = pcm.reshape(-1, frame.num_channels).mean(axis=1).astype(np.int16)
    samples = pcm.astype(np.float32) / 32768.0
    if frame.sample_rate != 16000:
        n = int(round(len(samples) * 16000 / frame.sample_rate))
        if n > 0:
            samples = np.interp(
                np.linspace(0, len(samples), n, endpoint=False), np.arange(len(samples)), samples
            ).astype(np.float32)
    return samples


class _WhisperSTT(stt_module.STT):
    """Common shell; subclasses implement ``_transcribe(samples, language) -> str``."""

    def __init__(self) -> None:
        super().__init__(capabilities=STTCapabilities(streaming=False, interim_results=False))

    def _transcribe(self, samples: np.ndarray, language: str, prompt: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def _recognize_impl(self, buffer, *, language=None, conn_options=None) -> SpeechEvent:
        samples = _frames_to_16k(buffer)
        # LIVE active language (a ⚙/voice switch applies on the next session); honor an
        # explicit non-empty override if the caller passes one.
        # FIRST-RUN (V2-089 P3): if no language has been chosen yet, transcribe in AUTO mode (language=None →
        # Whisper detects it) so a non-Latin operator (Arabic/Chinese/…) is transcribed CORRECTLY — that clean
        # text is what i18n.init.detect classifies to lock the language. No biasing initial_prompt in auto mode.
        auto = False
        if isinstance(language, str) and language:
            lang = language
        else:
            auto = langs.first_run_auto()      # misma respuesta que dan deepgram/voxtral (una sola fuente)
            lang = None if auto else langs.current_code()
        prompt = "" if auto else langs.spec(lang or langs.current_code()).whisper_prompt

        # Energy/duration gate: drop non-speech blips before Whisper so it can't
        # hallucinate a confident filler ("Thank you.") on silence/noise.
        dur = len(samples) / 16000.0
        rms = float(np.sqrt(np.mean(np.square(samples)))) if len(samples) else 0.0
        if rms < SETTINGS.stt_rms_gate or dur < SETTINGS.stt_min_sec:
            text = ""
        else:
            t0 = time.time()
            text = await asyncio.get_event_loop().run_in_executor(
                _EXECUTOR, self._transcribe, samples, lang, prompt
            )
            try:
                from voice.observer import emit
                emit("stt", f"👂 Whisper ({RESOLVED_DEVICE})", extra={"stt_ms": round((time.time() - t0) * 1000)})
            except Exception:
                pass
            if _is_hallucination(text):   # frase-alucinación conocida ("Gracias por ver el video") → ruido
                logger.info("descartada alucinación de Whisper: %r", text)
                text = ""
        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[SpeechData(language=lang or "auto", text=text)],
        )


class MlxWhisperSTT(_WhisperSTT):
    """Apple Silicon (Metal/ANE) via mlx-whisper."""

    def __init__(self) -> None:
        super().__init__()
        import mlx_whisper  # noqa: F401  (import here so non-Mac never needs it)

        self._repo = SETTINGS.whisper_mlx_model
        _spec = langs.current_language()
        # Warm on the SAME dedicated thread every live call will use (see _EXECUTOR above) —
        # otherwise warm-up binds the Metal stream to a thread no later call ever runs on.
        _EXECUTOR.submit(
            self._transcribe, np.zeros(16000, dtype=np.float32), _spec.code, _spec.whisper_prompt
        ).result()

    def _transcribe(self, samples: np.ndarray, language: str, prompt: str) -> str:
        import mlx_whisper

        r = mlx_whisper.transcribe(
            samples, path_or_hf_repo=self._repo, language=language,
            logprob_threshold=-1.0, initial_prompt=prompt, **_DECODE,
        )
        return (r.get("text") or "").strip()


class FasterWhisperSTT(_WhisperSTT):
    """NVIDIA CUDA or CPU via faster-whisper (CTranslate2)."""

    def __init__(self, device: str) -> None:
        super().__init__()
        from faster_whisper import WhisperModel

        compute = SETTINGS.whisper_compute if device == "cpu" else "float16"
        self._model = WhisperModel(SETTINGS.whisper_model, device=device, compute_type=compute)

    def _transcribe(self, samples: np.ndarray, language: str, prompt: str) -> str:
        segments, _info = self._model.transcribe(
            samples, language=language, beam_size=5, vad_filter=False,
            log_prob_threshold=-1.0, initial_prompt=prompt, **_DECODE,
        )
        return "".join(s.text for s in segments).strip()


def _make_backend(device: str) -> _WhisperSTT:
    if device == "metal":
        return MlxWhisperSTT()
    return FasterWhisperSTT(device=device)  # "cuda" or "cpu"


def build(vad=None):
    global RESOLVED_DEVICE
    if vad is None:
        raise ValueError("whisper_local needs a VAD (StreamAdapter)")

    device = accel.pick_device(SETTINGS.whisper_device)
    try:
        backend = _make_backend(device)
    except Exception as e:  # auto-adapt: any backend init failure → CPU (universal)
        logger.warning("STT device %r failed to init (%s) — falling back to CPU", device, e)
        device, backend = "cpu", FasterWhisperSTT(device="cpu")

    RESOLVED_DEVICE = device
    logger.info("local STT backend: %s (%s)", device,
                SETTINGS.whisper_mlx_model if device == "metal" else SETTINGS.whisper_model)
    return stt_module.StreamAdapter(stt=backend, vad=vad)


registry.register("whisper_local")(build)
