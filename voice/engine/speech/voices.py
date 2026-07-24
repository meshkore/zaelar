"""Voice catalog for the LiveKit engine (INI-012).

Ported from the old Pipecat ``voice/agent.py`` (``VOICES_BY_PROVIDER`` /
``voices_for`` / ``tts_provider``) when Pipecat was retired. Consumed by:
  * the ⚙ config panel (``config/settings.py``) to list/select voices,
  * the HTTP voice API (``server/voice_api.py``) for /api/voices, /config, status,
  * the TTS builders (``tts/cartesia.py``, ``tts/kokoro.py``) to honor the picked voice.

Provider-name reconciliation: the zaelar catalog historically keyed voices by
``cartesia`` / ``kokoro`` / ``deepgram`` / ``elevenlabs``; the LiveKit engine names
its TTS providers ``cartesia`` / ``kokoro_local``. We normalize ``kokoro_local`` ->
``kokoro`` so either spelling resolves to the same list. Only cartesia + kokoro are
buildable by the engine today; deepgram/elevenlabs entries are kept for reference
(no engine builder maps to them).

Selected voice: ``selected_voice(provider)`` returns the concrete voice id the
operator picked in the ⚙ (persisted as ``assistant_voice`` in config/settings.json,
or the ``ASSISTANT_VOICE`` env) **only if it belongs to that provider's catalog** —
this guards against cross-provider poisoning (a Cartesia UUID leaking into Kokoro,
etc.). If it doesn't match, we return '' and the TTS builder keeps its own default.
Because the engine reads ``SETTINGS`` (frozen at import), a voice change applies on
the next reconnect/restart.
"""
from __future__ import annotations

import json
import os

from ..core import langs
from ..core.config import SETTINGS
from ..core.env import ZAELAR_ROOT

# Voices GROUPED BY PROVIDER. The ⚙ picks the PROVIDER; the value below is the voice id
# handed to the TTS plugin. Cartesia Sonic voices are MULTILINGUAL (one voice speaks any
# catalog language — the language param aligns it), so they're a single global list.
# Kokoro voices are LANGUAGE-SPECIFIC and come from the language catalog (core/langs.py)
# per the ACTIVE language, so a voice can never be sent through the wrong-language pipeline.
# deepgram/elevenlabs kept for reference (not buildable by the engine).
VOICES_BY_PROVIDER = {
    "cartesia": [
        {"label": "Marcos", "voice": "13ff5deb-2591-42ad-a356-63a04e524411", "gender": "m"},
        {"label": "Nuria",  "voice": "9d8c6b2e-0a23-4a15-ae1b-121d5b5af417", "gender": "f"},
    ],
    # "kokoro" is dynamic per language — see kokoro_voices() / voices_for().
    "deepgram": [
        {"label": "Selena (es+en)", "voice": "aura-2-selena-es", "gender": "f"},
        {"label": "Javier (es+en)", "voice": "aura-2-javier-es", "gender": "m"},
        {"label": "Diana (es+en)",  "voice": "aura-2-diana-es",  "gender": "f"},
        {"label": "Carina (es+en)", "voice": "aura-2-carina-es", "gender": "f"},
        {"label": "Aquila (es+en)", "voice": "aura-2-aquila-es", "gender": "m"},
    ],
    "elevenlabs": [
        {"label": "Voz ElevenLabs", "voice": os.getenv("ELEVENLABS_VOICE_ID", ""), "gender": "f"},
    ],
}

# engine TTS provider name -> catalog key
_ALIAS = {"kokoro_local": "kokoro"}


def _catalog_key(provider: str) -> str:
    p = (provider or "").lower()
    return _ALIAS.get(p, p)


def tts_provider() -> str:
    """The ACTIVE TTS provider as a CATALOG key (engine ``kokoro_local`` -> ``kokoro``)."""
    return _catalog_key(SETTINGS.tts_provider) or "cartesia"


def kokoro_voices(lang: str | None = None) -> list:
    """Kokoro voices for a language (active language if None) — native, aligned voices only."""
    return langs.kokoro_voices(lang)


def kokoro_default_voice(lang: str | None = None) -> str:
    """The reliable default Kokoro voice for a language (active language if None)."""
    return langs.spec(lang).kokoro_default


def voices_for(provider: str | None = None, lang: str | None = None) -> list:
    """Voice list for the given provider (engine or catalog name), or the active one.
    For Kokoro (local) the list is the ACTIVE (or given) language's native voices, so the
    picker can never offer a wrong-language voice. Falls back to Cartesia for unknowns."""
    p = _catalog_key(provider) if provider else tts_provider()
    if p == "kokoro":
        return kokoro_voices(lang)
    return VOICES_BY_PROVIDER.get(p) or VOICES_BY_PROVIDER["cartesia"]


def _picked_voice() -> str:
    """The operator's chosen voice id: config/settings.json ``assistant_voice`` (written by
    the ⚙ panel), else the ``ASSISTANT_VOICE`` env. '' when nothing is set."""
    try:
        p = ZAELAR_ROOT / "config" / "settings.json"
        av = json.loads(p.read_text(encoding="utf-8")).get("assistant_voice")
        if av:
            return str(av).strip()
    except Exception:
        pass
    return os.getenv("ASSISTANT_VOICE", "").strip()


def selected_voice(provider: str | None = None) -> str:
    """The picked voice id IF it's valid for this provider AND (for Kokoro) the ACTIVE
    language — guards against cross-provider AND cross-language poisoning (e.g. a Spanish
    voice leaking into the English pipeline). Else '' → the TTS builder uses the language default."""
    p = _catalog_key(provider) if provider else tts_provider()
    av = _picked_voice()
    if not av:
        return ""
    valid = voices_for(p)  # for kokoro this is the active language's native voices
    if any(v["voice"] == av for v in valid):
        return av
    return ""


__all__ = ["VOICES_BY_PROVIDER", "voices_for", "kokoro_voices", "kokoro_default_voice",
           "tts_provider", "selected_voice"]
