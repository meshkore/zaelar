"""Central runtime configuration — one source of truth for every knob.

Reads the environment via ``core.env`` and the profile defaults via
``core.profile``. Components read ``SETTINGS``; nothing else parses the env.

zaelar adaptations (INI-012):
  * env knob prefix ``VL2_`` -> ``ZAELAR_``; provider API keys keep zaelar's
    existing standard names (OPENAI_API_KEY, AIMLAPI_KEY, CARTESIA_API_KEY,
    MISTRAL_API_KEY, DEEPGRAM_API_KEY, GEMINI_API_KEY, Z_AI_API_KEY).
  * web_port 43917, room "zaelar", English prompt/greeting.
  * llm_provider defaults to the ``BRAIN`` env (hermes|duo|direct) when set — the
    hermes/duo/direct LLM providers are added later by another change; this only
    lets the name flow through.
  * log_dir -> .meshkore/logs/voice (MeshKore standard).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .env import ZAELAR_ROOT, env
from .profile import PROFILE, pick


def _llm_provider_default() -> str:
    # BRAIN (hermes|duo|direct) wins when set; else the profile's llm default,
    # overridable by ZAELAR_LLM_PROVIDER.
    return env("BRAIN") or pick("ZAELAR_LLM_PROVIDER", "llm")


@dataclass(frozen=True)
class Settings:
    # --- Web / token server -------------------------------------------------
    web_host: str = env("ZAELAR_WEB_HOST", "127.0.0.1")
    web_port: int = int(env("ZAELAR_WEB_PORT", "43917"))

    # --- LiveKit (self-hosted dev server) -----------------------------------
    livekit_url: str = env("LIVEKIT_URL", "ws://127.0.0.1:7880")
    livekit_api_key: str = env("LIVEKIT_API_KEY", "devkey")
    livekit_api_secret: str = env("LIVEKIT_API_SECRET", "secret")
    room_name: str = env("ZAELAR_ROOM", "zaelar")

    # --- Profile + component selection --------------------------------------
    profile: str = PROFILE                                # remote | local
    vad_provider: str = env("ZAELAR_VAD", "silero")       # local in both profiles
    # Endpointing: default 'disabled' → AgentSession uses VAD-based EOU (turn_detection="vad"). The LiveKit ML
    # turn model ('livekit', MultilingualModel) needs its InferenceRunner registered on the MAIN thread, which the
    # embedded THREAD job executor (INI-012) can't provide → it crashes ("InferenceRunner must be registered on the
    # main thread"). VAD endpointing works in-thread. Re-enabling the ML model is a follow-up (register inference
    # on the main thread before the worker starts). See INI-012 known items.
    turn_provider: str = env("ZAELAR_TURN", "disabled")
    # STT/TTS/LLM default BY PROFILE; an explicit env var overrides (hybrids).
    stt_provider: str = pick("ZAELAR_STT", "stt")          # voxtral|deepgram|whisper_local
    tts_provider: str = pick("ZAELAR_TTS", "tts")          # cartesia|kokoro_local
    # BRAIN (hermes|duo|direct) wins; then profile default; then ZAELAR_LLM_PROVIDER.
    llm_provider: str = _llm_provider_default()            # hermes|duo|direct|aimlapi|openai|gemini|glm|claude|local

    # --- Model ids ----------------------------------------------------------
    # Empty -> each LLM provider falls back to its own sensible default model.
    llm_model: str = env("ZAELAR_LLM_MODEL", "")
    stt_model_voxtral: str = env("ZAELAR_STT_MODEL", "voxtral-mini-transcribe-realtime-2602")
    stt_model_deepgram: str = env("ZAELAR_STT_MODEL_DG", "nova-3")
    tts_model: str = env("ZAELAR_TTS_MODEL", "sonic-3")
    tts_voice_id: str = env("CARTESIA_VOICE_ID", "")

    # --- LOCAL profile endpoints/models (on-machine, no per-token cost) ------
    local_llm_url: str = env("ZAELAR_LOCAL_LLM_URL", "http://localhost:11434/v1")  # Ollama /v1
    local_llm_model: str = env("ZAELAR_LOCAL_LLM_MODEL", "qwen2.5:3b")
    tts_device: str = env("ZAELAR_TTS_DEVICE", "auto")   # auto|metal|fastapi (auto: Metal on Apple Silicon)
    kokoro_url: str = env("ZAELAR_KOKORO_URL", "http://localhost:8880/v1")          # Kokoro-FastAPI (CPU fallback)
    kokoro_mlx_model: str = env("ZAELAR_KOKORO_MLX_MODEL", "mlx-community/Kokoro-82M-bf16")  # Metal
    kokoro_voice: str = env("ZAELAR_KOKORO_VOICE", "af_heart")                       # Kokoro English (f)
    whisper_device: str = env("ZAELAR_WHISPER_DEVICE", "auto")   # auto|metal|cuda|cpu (auto-detect, core.accel)
    whisper_model: str = env("ZAELAR_WHISPER_MODEL", "small")    # faster-whisper size (cpu/cuda)
    whisper_compute: str = env("ZAELAR_WHISPER_COMPUTE", "int8")  # CPU compute type
    whisper_mlx_model: str = env("ZAELAR_WHISPER_MLX_MODEL", "mlx-community/whisper-large-v3-turbo")  # Metal
    # Anti-hallucination gate: Whisper invents fillers ("Thank you.", "Bye.") with
    # high confidence on low-energy/short blips (no_speech_prob can't catch it).
    # Don't transcribe a segment below this energy / duration — energy separates
    # cleanly (noise rms ~0.002 vs speech ~0.05).
    # PROXIMITY gate (2026-07-12): subido 0.012→0.02 para RECHAZAR voz/ruido LEJANO. El operador habla a ~60 cm
    # (rms alto ~0.05-0.1); un grito/TV/tráfico a varios metros llega ATENUADO (~0.005-0.018) → cae bajo el umbral
    # y no se transcribe (así una voz de fondo no "dispara" un turno fantasma que gasta STT+memoria). El VAD Silero
    # (activation 0.55) filtra lo no-humano; este gate filtra lo humano-pero-lejano (que el VAD sí dejaría pasar por
    # ser "voz"). Es el knob PRINCIPAL de robustez al ruido — súbelo si aún se cuela ruido, bájalo si pierde tu voz.
    stt_rms_gate: float = float(env("ZAELAR_STT_RMS_GATE", "0.02"))
    stt_min_sec: float = float(env("ZAELAR_STT_MIN_SEC", "0.25"))

    # --- Debug UI meters (thresholds shown as ticks; do NOT change detection) --
    vad_threshold: float = float(env("ZAELAR_VAD_THRESHOLD", "0.5"))       # Silero activation ref
    voice_rms_floor: float = float(env("ZAELAR_VOICE_RMS_FLOOR", "0.02"))  # visual rms reference

    # --- Behaviour ----------------------------------------------------------
    # Default INTERFACE language. zaelar is MULTILINGUAL (see core/langs.py): this is only the
    # import-time default (Spanish); the operator switches from the ⚙ or by voice and STT/TTS/voice/reply
    # move together. The engine reads the LIVE language via ``core.langs.current_code()``, not this frozen field.
    language: str = env("ZAELAR_LANGUAGE", "es")
    # Language-NEUTRAL persona; the reply LANGUAGE is appended per session from the active language
    # (core.langs reply_directive), so switching language re-languages the assistant coherently.
    system_prompt: str = env(
        "ZAELAR_SYSTEM_PROMPT",
        "You are zaelar, a concise personal voice assistant. Keep replies to short, natural spoken "
        "sentences, no markdown, no emojis.",
    )
    greeting: str = env("ZAELAR_GREETING", "Hola, te escucho.")

    # --- Provider API keys (read where the plugin expects them) -------------
    openai_api_key: str = env("OPENAI_API_KEY")
    aimlapi_api_key: str = env("AIMLAPI_KEY")
    aimlapi_base_url: str = env("AIMLAPI_BASE_URL", "https://api.aimlapi.com/v1")
    cartesia_api_key: str = env("CARTESIA_API_KEY")
    elevenlabs_api_key: str = env("ELEVENLABS_API_KEY")    # TTS cloud fiable (V2-035) — clave en el credential store
    # 2026-07-13: turbo_v2_5 (más ESTABLE de acento que flash) + voz CASTELLANA nativa (Sara Martin, es/peninsular).
    # Con el tier CREATOR (créditos + library voices desbloqueadas) esta es la voz titular: acento castellano estable,
    # sin el drift inglés/portugués que daba la voz premade anglo del free. El `language` lock (es) va en el provider.
    elevenlabs_model: str = env("ELEVENLABS_MODEL", "eleven_turbo_v2_5")  # turbo = baja latencia y acento estable
    elevenlabs_voice_id: str = env("ELEVENLABS_VOICE_ID", "KHCvMklQZZo0O30ERnVn")  # Sara Martin (es, peninsular)
    mistral_api_key: str = env("MISTRAL_API_KEY")
    deepgram_api_key: str = env("DEEPGRAM_API_KEY")
    gemini_api_key: str = env("GEMINI_API_KEY")
    zai_api_key: str = env("Z_AI_API_KEY")
    zai_base_url: str = env("Z_AI_BASE_URL", "https://api.z.ai/api/paas/v4")
    glm_model: str = env("GLM_MODEL", "glm-4.6")

    # --- Logging ------------------------------------------------------------
    log_dir: Path = ZAELAR_ROOT / ".meshkore" / "logs" / "voice"


SETTINGS = Settings()
__all__ = ["SETTINGS", "ZAELAR_ROOT"]
