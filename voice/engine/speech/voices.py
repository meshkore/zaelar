"""Voice catalog for the LiveKit engine (INI-012).

Ported from the old Pipecat ``voice/agent.py`` (``VOICES_BY_PROVIDER`` /
``voices_for`` / ``tts_provider``) when Pipecat was retired. Consumed by:
  * the ⚙ config panel (``config/settings.py``) to list/select voices,
  * the HTTP voice API (``server/voice_api.py``) for /api/voices, /config, status,
  * the TTS builders (``tts/cartesia.py``, ``tts/kokoro.py``) to honor the picked voice.

Provider-name reconciliation: the zaelar catalog historically keyed voices by
``cartesia`` / ``kokoro`` / ``deepgram`` / ``elevenlabs``; the LiveKit engine names
its TTS providers ``cartesia`` / ``kokoro_local``. We normalize ``kokoro_local`` ->
``kokoro`` so either spelling resolves to the same list. Cartesia, Kokoro and
ElevenLabs are buildable by the engine; the deepgram entry is kept for reference
(no engine builder maps to it).

Three shapes of catalog, and the difference is a property of the PROVIDER, not a
style: Cartesia's voices are multilingual (one global list — the language param
aligns them), Kokoro's are language-specific and come from ``core/langs.py``, and
ElevenLabs' are fetched per language from its API (``elevenlabs_voices.py``). A
picker must never be able to offer a wrong-language voice, so each list is built
from whatever its provider actually knows about language.

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
    # "elevenlabs" is dynamic per language too — see elevenlabs_voices.py. It used to be ONE entry read
    # from an env var, which is why every language got the same Castilian voice (V2-672).
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


def elevenlabs_voices(lang: str | None = None) -> list:
    """ElevenLabs voices for a language (active language if None) — native ones first, multilingual last."""
    from .elevenlabs_voices import for_language
    return for_language(lang or langs.current_code())


def elevenlabs_default_voice(lang: str | None = None) -> str:
    """The voice ElevenLabs should speak this language with when the operator has not picked one."""
    from .elevenlabs_voices import default_voice
    return default_voice(lang or langs.current_code())


def default_voice_for(provider: str | None = None, lang: str | None = None) -> str:
    """The right voice for (provider, language) when nothing has been chosen — the seam the language
    onboarding and the ⚙'s realignment both use, so neither has to know which providers are per-language."""
    p = _catalog_key(provider) if provider else tts_provider()
    if p == "kokoro":
        return kokoro_default_voice(lang)
    if p == "elevenlabs":
        return elevenlabs_default_voice(lang)
    return ""                    # Cartesia's voices are multilingual — one voice speaks any language


def voice_is_aligned(provider: str | None, voice: str, lang: str | None = None) -> bool:
    """Is `voice` a sound choice for `lang` under `provider`? The question a LANGUAGE CHANGE has to ask.

    "Is it in the list" is NOT the same question, and using it was a real defect (V2-672): the ElevenLabs
    list deliberately KEEPS multilingual voices as a fallback, so a Castilian voice is in the English list —
    and a language switch would have looked at it, found it present, and left English speaking Spanish,
    which is the very thing this work exists to fix. Kokoro's list contains natives only, so for it the two
    questions happen to coincide, which is how one of them passed for the other.

    A language with NO native voice (measured: Swahili returns zero from the Voice Library) has nothing
    better to offer, so whatever is set stays — realigning there would swap one fallback for another and
    throw away the operator's choice for nothing.
    """
    p = _catalog_key(provider) if provider else tts_provider()
    voice = (voice or "").strip()
    if not voice:
        return False
    if p == "kokoro":
        return any(v["voice"] == voice for v in kokoro_voices(lang))
    if p == "elevenlabs":
        natives = [v for v in elevenlabs_voices(lang) if v.get("native")]
        return True if not natives else any(v["voice"] == voice for v in natives)
    return True                  # Cartesia: one multilingual voice speaks every catalog language


def voices_for(provider: str | None = None, lang: str | None = None) -> list:
    """Voice list for the given provider (engine or catalog name), or the active one.
    For Kokoro (local) the list is the ACTIVE (or given) language's native voices, so the
    picker can never offer a wrong-language voice. Falls back to Cartesia for unknowns."""
    p = _catalog_key(provider) if provider else tts_provider()
    if p == "kokoro":
        return kokoro_voices(lang)
    if p == "elevenlabs":
        return elevenlabs_voices(lang)
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
           "elevenlabs_voices", "elevenlabs_default_voice", "default_voice_for", "voice_is_aligned",
           "tts_provider", "selected_voice"]
