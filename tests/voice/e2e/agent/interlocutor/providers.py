"""The interlocutor's own voice (TTS) and ears (STT) — LiveKit plugins built DIRECTLY, with ZERO imports of
zaelar's core code. The tester is a black-box external client; it must never depend on the code under test.
Defaults to reliable cloud (keys already in .env). A local/free tester voice/STT would be added HERE as a
self-contained adapter — never borrowed from zaelar's voice/engine (independence rule)."""
from __future__ import annotations

from livekit.agents import stt as _stt, tts as _tts

from .. import config


def build_tts() -> _tts.TTS:
    p = config.TESTER_TTS.lower()
    if p == "cartesia":
        from livekit.plugins import cartesia
        kw = {"api_key": config.CARTESIA_API_KEY or None}
        if config.TESTER_TTS_VOICE:
            kw["voice"] = config.TESTER_TTS_VOICE
        return cartesia.TTS(**kw)
    if p == "deepgram":
        from livekit.plugins import deepgram
        # Deepgram Aura model = voice+language. Spanish voice for a Spanish-speaking zaelar (Cartesia ran out of credit → 402).
        model = config.TESTER_TTS_VOICE or ("aura-2-selena-es" if config.TESTER_LANG == "es" else "aura-2-thalia-en")
        return deepgram.TTS(model=model, api_key=config.DEEPGRAM_API_KEY or None)
    raise ValueError(f"unsupported TESTER_TTS={p!r} (independent options: cartesia, deepgram)")


def build_stt() -> _stt.STT:
    p = config.TESTER_STT.lower()
    if p == "deepgram":
        from livekit.plugins import deepgram
        return deepgram.STT(model="nova-3", language=config.TESTER_LANG, api_key=config.DEEPGRAM_API_KEY or None)
    raise ValueError(f"unsupported TESTER_STT={p!r} (independent option: deepgram)")
