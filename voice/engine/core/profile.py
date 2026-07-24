"""Profiles — map a profile to per-component provider defaults.

Two profiles today: ``remote`` (everything external, the v1.0 baseline) and
``local`` (STT/LLM/TTS on-machine — no per-token cost, no network hop). Adding a
profile = one entry in ``_DEFAULTS``. The profile only sets DEFAULTS; an explicit
env override for any component always wins, which is what makes hybrids possible
(e.g. local STT+TTS + remote LLM on a weak machine).

zaelar note (INI-012): the ``llm`` default here is only a fallback. In practice
``config._llm_provider_default`` lets the ``BRAIN`` env (hermes|duo|direct)
override it, so these values apply when BRAIN is unset.
"""
from __future__ import annotations

from .env import env

PROFILE = env("ZAELAR_PROFILE", "remote")

_DEFAULTS: dict[str, dict[str, str]] = {
    "remote": {"stt": "voxtral", "tts": "cartesia", "llm": "aimlapi"},
    "local": {"stt": "whisper_local", "tts": "kokoro_local", "llm": "local"},
}


def pick(env_name: str, component: str) -> str:
    """Explicit env var, else the current profile's default for that component."""
    defaults = _DEFAULTS.get(PROFILE, _DEFAULTS["remote"])
    return env(env_name, defaults[component])
