"""Profiles — map a profile to per-component provider defaults.

Two profiles today: ``remote`` (everything external, the v1.0 baseline) and
``local`` (STT/LLM/TTS on-machine — no per-token cost, no network hop). Adding a
profile = one entry in ``_DEFAULTS``. The profile only sets DEFAULTS; an explicit
env override for any component always wins, which is what makes hybrids possible
(e.g. local STT+TTS + remote LLM on a weak machine).

zaelar note (INI-012): the ``llm`` default here is only a fallback. In practice
``config._llm_provider_default`` lets the ``BRAIN`` env (hermes|duo|direct)
override it, so these values apply when BRAIN is unset.

⚠️ The ``llm`` default is ``nucleo`` — the PRODUCT's own brain — and this is a boot-integrity rule, not a
taste (2026-09-10). It used to be the raw broker plugin, so a bare ``python -m server`` (no ``BRAIN`` env)
silently booted a DIFFERENT product: a bare cloud model with no FlashBrain, no memory, no tools, no widgets
and no provider relay — while ``/api/brain`` kept answering «nucleo» from its own separate knob. Measured
live: the operator's engine ran a whole evening on the wrong brain, every turn died on the raw plugin's
provider error, and LiveKit closed the session with the mic still open. The baselines are still one env var
away (``BRAIN=direct`` / ``BRAIN=local``); what may never again depend on remembering an env var is booting
the real product.
"""
from __future__ import annotations

from .env import env

PROFILE = env("ZAELAR_PROFILE", "remote")

# ⚠️ The `remote` row is NOT free to choose: it must name the SAME providers as the canonical model table
# (`config/models.default.json` §stt / §tts, V2-500). This file is what a bare boot with no `settings.json`
# gets — i.e. every fresh install and every factory reset — so a value that drifts from the table silently
# ships a DIFFERENT voice stack than the one the table says we run, and nothing compares the two at runtime.
# It had drifted: voxtral + cartesia here against deepgram + elevenlabs in the table (V2-671, measured on the
# operator's install after a factory reset). `tests/infrastructure/unit/config/test_the_deployment_picks_the_profile.py`
# is the ratchet — change the table and this row goes red until it follows.
_DEFAULTS: dict[str, dict[str, str]] = {
    "remote": {"stt": "deepgram", "tts": "elevenlabs", "llm": "nucleo"},
    "local": {"stt": "whisper_local", "tts": "kokoro_local", "llm": "nucleo"},
}


def pick(env_name: str, component: str) -> str:
    """Explicit env var, else the current profile's default for that component."""
    defaults = _DEFAULTS.get(PROFILE, _DEFAULTS["remote"])
    return env(env_name, defaults[component])
