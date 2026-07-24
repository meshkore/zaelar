"""ElevenLabs TTS — remote streaming (V2-035, TTS cloud FIABLE).

Motivo (informe 2026-07-13): el Kokoro LOCAL (mlx-audio Metal) petaba mucho por contención de GPU con Ollama →
voz lenta/entrecortada/muda. Para producción (y el deploy en la nube) la voz debe ir SIEMPRE bien; ElevenLabs es
un TTS cloud bueno y con un modelo BARATO/rápido (`eleven_flash_v2_5`, multilingüe → castellano nativo). Streaming;
`AgentSession` lo auto-cancela en barge-in, igual que Cartesia. La clave vive en el credential store
(`ELEVENLABS_API_KEY`), NUNCA en el repo. Se selecciona por la UI (⚙ `tts_provider=elevenlabs`) o `ZAELAR_TTS`.
"""
from __future__ import annotations

from livekit.plugins import elevenlabs as _eleven

from ...core.config import SETTINGS
from ...core import langs as _langs
from ..voices import selected_voice
from . import registry


@registry.register("elevenlabs")
def build():
    # Modelo multilingüe ESTABLE (turbo_v2_5 por defecto) + LOCK de idioma al del operador. El drift de acento
    # (inglés/portugués sobre castellano) se combatió en V2-035: (1) voz CASTELLANA nativa (no la voz por defecto
    # anglo del plugin), (2) `language` explícito al idioma activo → el modelo no "adivina" ni deriva.
    kwargs = dict(
        model=SETTINGS.elevenlabs_model or "eleven_turbo_v2_5",
        api_key=SETTINGS.elevenlabs_api_key or None,
    )
    # Voz: la elegida por el operador en el ⚙ (voces.py provider 'elevenlabs') > env ELEVENLABS_VOICE_ID > default
    # castellano de config. ElevenLabs identifica la voz por voice_id.
    voice = selected_voice("elevenlabs") or SETTINGS.elevenlabs_voice_id
    if voice:
        kwargs["voice_id"] = voice
    # LOCK de idioma: fija el idioma del operador (es/en) para que el modelo NO derive de acento (turbo/flash v2.5
    # aceptan language_code). Sin esto, ante texto corto/ambiguo el multilingüe se va a otro acento.
    try:
        lang = _langs.current_code()
        if lang:
            kwargs["language"] = lang
    except Exception:
        pass
    return _eleven.TTS(**kwargs)
