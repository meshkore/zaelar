"""The worker process's PREWARM: heavy local models loaded once, before a job is assigned (V2-778 F1, 2026-10-01).

Moved out of `voice/engine/pipeline/agent.py` (925 lines, over the 900 a new file may reach). Unchanged; `agent`
imports it back and still hands it to the LiveKit server as `prewarm_fnc`. `logger` is the same object as
agent's (`logging.getLogger("zaelar.agent")` returns one logger per name).
"""
from __future__ import annotations

import logging

from livekit.agents import JobProcess

from ..core.config import SETTINGS
from ..core.logging import setup_console_logging
from ..speech import build_stt, build_tts, build_vad

logger = logging.getLogger("zaelar.agent")


def prewarm(proc: JobProcess) -> None:
    """Load heavy local models once per worker process, BEFORE a job is assigned.

    With ``num_idle_processes>=1`` the worker keeps a fully-warm executor waiting
    (this runs there), so a session connects and the agent joins fast instead of
    paying the ~6s cold start (VAD + Whisper model load + Ollama) on the first turn.

    CONFIRMED WORKING (2026-07-08, INI-013): this runs in the ``job_thread_runner``
    thread of THIS process (THREAD executor); the very session that connects reuses
    THIS proc's ``userdata`` (``entrypoint`` reports ``vad_hit/stt_hit/tts_hit=True``).
    An earlier note claimed "prewarm never fires" — that was a FALSE NEGATIVE: the
    confirmation was ``logger.info`` but, in the job thread, the root logger has no
    handler yet (``entrypoint`` sets it up later), so Python's WARNING-level lastResort
    handler swallowed it. We now call ``setup_console_logging()`` FIRST so the confirmation
    is visible in the zaelar log, and this misdiagnosis can't recur.
    """
    setup_console_logging()  # make this thread's INFO logs visible (see docstring)
    logger.info("prewarm() START — warming VAD/STT/TTS(+Ollama) in the idle executor")
    proc.userdata["vad"] = build_vad()
    # Pre-build the STT so the Whisper model loads here (idle executor), not on the
    # first turn of each session. Reused verbatim in entrypoint.
    try:
        proc.userdata["stt"] = build_stt(vad=proc.userdata["vad"])
    except Exception as e:  # noqa: BLE001
        logger.warning("STT prewarm skipped: %s", e)
    try:
        proc.userdata["tts"] = build_tts()  # warms the Metal Kokoro model in the idle executor
        # Remote TTS plugins (Cartesia) keep a websocket ConnectionPool that is only opened on the FIRST
        # synthesis — so the session's first utterance (the kickoff greeting) paid a fresh TLS+WS handshake
        # (2026-09-01 latency audit). Plugins that expose prewarm() get their pool opened here, in the idle
        # executor; local TTS (Kokoro) has no such method and is already warmed by build_tts() itself.
        _pw = getattr(proc.userdata["tts"], "prewarm", None)
        if callable(_pw):
            _pw()
    except Exception as e:  # noqa: BLE001
        logger.warning("TTS prewarm skipped: %s", e)

    # Pre-load any LOCAL Ollama model on the critical path so turn 1 isn't a ~3s cold start
    # (Ollama loads on first use + unloads when idle → keep_alive keeps it hot). Two cases:
    #   · llm_provider == "local"  → the main LLM is Ollama
    #   · llm_provider == "nucleo" with a LOCAL fast layer → the «Colmena» FlashBrain runs on Ollama
    _warm = []  # (ollama_v1_url, model)
    if SETTINGS.llm_provider == "local":
        _warm.append((SETTINGS.local_llm_url, SETTINGS.local_llm_model))
    if SETTINGS.llm_provider == "nucleo":
        try:
            from nucleo.flash.fast_client import spec_from_config
            spec = spec_from_config()
            if (spec.provider or "").lower() == "ollama" and spec.model:
                _warm.append((spec.resolved_base_url(), spec.model))
        except Exception as e:  # noqa: BLE001
            logger.warning("nucleo fast-layer prewarm probe skipped: %s", e)
    for url, model in _warm:
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                url.rsplit("/v1", 1)[0] + "/api/generate",
                data=json.dumps(
                    {"model": model, "prompt": "hola", "stream": False, "keep_alive": "30m"}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=60).read()
            logger.info("prewarmed local Ollama model %s", model)
        except Exception as e:  # noqa: BLE001
            logger.warning("local Ollama prewarm skipped (%s): %s", model, e)
    logger.info("prewarm() DONE — warm executor ready (userdata: %s)", sorted(proc.userdata.keys()))
