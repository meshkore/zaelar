"""The TTS that is speaking RIGHT NOW — so a language change can re-point it without a reconnect (V2-733).

THE FAILURE THIS EXISTS FOR. The operator, arriving in Spanish on a fresh install (2026-09-20): *«acabo de
probar arrancar en español y me sale la voz del señor inglés intentando hablar español, con lo cual lo hace
muy mal»*. Everything upstream was already right — V2-672 gave every language its own native voice and
`config/settings.update()` realigns `assistant_voice` the moment the language is locked, and it did. What
nobody had is the LAST metre: the TTS service is constructed when the pipeline is built, reads the voice
once, and keeps it for the life of the session. So the realigned voice sat correctly in `settings.json`
waiting for a reconnect nobody was going to ask for, while the live session went on speaking Spanish with
an English voice — including `onboarding.confirmSpoken`, which is by design *the very first thing the
operator ever hears*.

WHY NOT A RECONNECT. That is what the ⚙ does (`session.reconnect()`), and it is right there because the ⚙
also changes the STT and the provider, which really are built-once. Doing it here would race the
confirmation: the server speaks it the instant `lock()` returns, so the utterance would land in the
session being torn down, or in no session at all. Re-pointing the live TTS has no such window — the next
thing synthesised uses the new voice, and the first thing the operator hears is correct.

WHAT THIS IS NOT. It does not persist anything and it is not a source of truth: `assistant_voice` in
`config/settings.json` remains the record, and a session built later reads it through
`voices.selected_voice()` exactly as before. This only stops the CURRENT session from being the one that
never got the message. If the live plugin cannot take the change, `apply_voice` says so by returning False
and the caller degrades to what used to happen anyway — the voice is right on the next connect.
"""
from __future__ import annotations

import inspect

from loguru import logger

# The session running in THIS process. One at a time: the engine runs one AgentSession per worker job, and
# a stale handle is worse than none (it would re-point a TTS nobody can hear), so `detach` clears it and
# `attach` replaces it outright.
_live: dict = {"tts": None, "provider": ""}

# Which keyword each plugin calls the voice. Measured against the installed plugins (2026-09-20):
# elevenlabs `update_options(voice_id=…, language=…)`, cartesia `update_options(voice=…, language=…)`.
# A provider that is not here can still be re-pointed if it names the voice one of these — the lookup
# below asks the SIGNATURE, so a rename in the plugin shows up as «could not re-point», never as a silent
# no-op on a call that looked fine.
_VOICE_KW = ("voice_id", "voice")


def attach(tts: object, provider: str) -> None:
    """Remember the TTS of the session being built. Called from the pipeline, once, per session."""
    _live["tts"] = tts
    _live["provider"] = (provider or "").strip().lower()


def detach(tts: object | None = None) -> None:
    """Forget it. With `tts`, only if it is still the one attached — a session closing late must not
    unregister the session that has already replaced it."""
    if tts is not None and _live["tts"] is not tts:
        return
    _live["tts"] = None
    _live["provider"] = ""


def live_provider() -> str:
    """The provider of the session currently speaking, '' if none."""
    return _live["provider"] if _live["tts"] is not None else ""


def apply_voice(voice_id: str, lang: str | None = None) -> bool:
    """Re-point the LIVE voice to `voice_id` (and, where the plugin accepts it, lock the language).

    Returns True only if the live plugin actually took it. False means there is no session, or its TTS
    cannot be re-pointed — both of which are the pre-V2-733 behaviour: the persisted setting applies on the
    next connect. Never raises: a voice that could not be swapped must not take down the settings save that
    was otherwise fine.
    """
    tts = _live["tts"]
    voice_id = (voice_id or "").strip()
    if tts is None or not voice_id:
        return False
    fn = getattr(tts, "update_options", None)
    if not callable(fn):
        logger.info("live_tts: {} cannot be re-pointed (no update_options) — the voice applies on reconnect",
                    _live["provider"] or "the live TTS")
        return False
    try:
        params = inspect.signature(fn).parameters
    except Exception:  # noqa: BLE001 — a builtin/bound method we cannot introspect
        params = {}
    kw = {}
    for name in _VOICE_KW:
        if name in params:
            kw[name] = voice_id
            break
    if not kw:
        logger.warning("live_tts: {} names its voice something we do not know — the voice applies on reconnect",
                       _live["provider"] or "the live TTS")
        return False
    # The language lock matters as much as the voice on a multilingual model: ElevenLabs' flash/turbo v2.5
    # drift in accent on short text when it is not told which language it is speaking (V2-035).
    if lang and "language" in params:
        kw["language"] = lang
    try:
        fn(**kw)
    except Exception as e:  # noqa: BLE001
        logger.warning("live_tts: could not re-point the live voice ({}) — it applies on reconnect", e)
        return False
    logger.info("live_tts: live voice → {} (lang={}) on {}", voice_id, lang or "—", _live["provider"] or "?")
    return True


__all__ = ["attach", "detach", "apply_voice", "live_provider"]
