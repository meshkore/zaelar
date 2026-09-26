"""Inworld TTS — remote streaming over WebSocket (V2-774). The default cloud TTS; ElevenLabs is the second.

Why it is the default, MEASURED 2026-09-26 through the same LiveKit plugins the engine runs (streaming path,
full sentence pushed, first audio frame, p50 of 9 per language, from Spain):

  model                     es TTFB   en TTFB   $/1M chars (on-demand)
  inworld-tts-2-flash        136 ms    134 ms    15
  inworld-tts-2              185 ms    168 ms    25
  eleven_turbo_v2_5 (prev.)  194 ms    175 ms    ~50
  eleven_flash_v2_5          132 ms    141 ms    ~50

With the text arriving word by word, as the brain streams it, `inworld-tts-2` gave first audio 855/700 ms
(es/en) against 933/732 for the ElevenLabs model it replaces. So the flagship model is at least as fast as
what we ran and half the price; `inworld-tts-2-flash` is faster still and is one env var away
(`ZAELAR_INWORLD_TTS_MODEL`). The previous generation (`inworld-tts-1.5-*`) is deprecated by Inworld.

Voices are per language and come from `inworld_voices.py` (Inworld names a voice, it has no opaque id). The
key lives in the credential store (`INWORLD_API_KEY`, the Base64 credential Inworld's dashboard shows), NEVER
in the repo. Selected through the ⚙ (`tts_provider=inworld`) or `ZAELAR_TTS`.
"""
from __future__ import annotations

import os

from livekit.plugins import inworld as _inworld

from ...core import langs as _langs
from ...core.config import SETTINGS
from .. import voices as _voices
from ..voices import selected_voice
from . import registry

DEFAULT_MODEL = "inworld-tts-2"


@registry.register("inworld")
def build():
    kwargs = dict(
        model=os.getenv("ZAELAR_INWORLD_TTS_MODEL", "").strip() or DEFAULT_MODEL,
        api_key=(os.getenv("INWORLD_API_KEY") or getattr(SETTINGS, "inworld_api_key", "") or "").strip() or None,
    )
    # Voice: the operator's ⚙ pick (only if it is an Inworld voice of this language) > the variant's pinned
    # default. Without either, the plugin's own default is an English voice — never what a Spanish turn wants.
    voice = selected_voice("inworld") or _voices.inworld_default_voice()
    if voice:
        kwargs["voice"] = voice
    try:
        lang = _langs.current_code()
        if lang:
            kwargs["language"] = lang
    except Exception:  # noqa: BLE001 — a missing language must not take the TTS down
        pass
    return _inworld.TTS(**{k: v for k, v in kwargs.items() if v is not None})
