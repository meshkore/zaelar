"""ElevenLabs TTS — remote streaming (V2-035, RELIABLE cloud TTS).

Reason (2026-07-13 report): LOCAL Kokoro (mlx-audio Metal) failed frequently due to GPU contention with Ollama →
slow/choppy/silent voice. For production (and cloud deployment), the voice must ALWAYS work properly; ElevenLabs is
a good cloud TTS with a CHEAP/fast model (`eleven_flash_v2_5`, multilingual → native Castilian Spanish). Streaming;
`AgentSession` auto-cancels it on barge-in, just like Cartesia. The key lives in the credential store
(`ELEVENLABS_API_KEY`), NEVER in the repo. It is selected through the UI (⚙ `tts_provider=elevenlabs`) or `ZAELAR_TTS`.
"""
from __future__ import annotations

from livekit.plugins import elevenlabs as _eleven

from ...core.config import SETTINGS
from ...core import langs as _langs
from ..voices import selected_voice
from . import registry


@registry.register("elevenlabs")
def build():
    # STABLE multilingual model (turbo_v2_5 by default) + language LOCK to the operator's language. Accent drift
    # (English/Portuguese over Castilian Spanish) was addressed in V2-035: (1) native CASTILIAN voice (not the plugin's
    # default Anglo voice), (2) explicit `language` set to the active language → the model does not "guess" or drift.
    kwargs = dict(
        model=SETTINGS.elevenlabs_model or "eleven_turbo_v2_5",
        api_key=SETTINGS.elevenlabs_api_key or None,
    )
    # Voice: the one selected by the operator in ⚙ (voces.py provider 'elevenlabs') > env ELEVENLABS_VOICE_ID > the
    # Castilian Spanish config default. ElevenLabs identifies the voice by voice_id.
    voice = selected_voice("elevenlabs") or SETTINGS.elevenlabs_voice_id
    if voice:
        kwargs["voice_id"] = voice
    # Language LOCK: fixes the operator's language (es/en) so the model does NOT drift in accent (turbo/flash v2.5
    # accept language_code). Without this, the multilingual model switches to another accent for short/ambiguous text.
    try:
        lang = _langs.current_code()
        if lang:
            kwargs["language"] = lang
    except Exception:
        pass
    return _eleven.TTS(**kwargs)
