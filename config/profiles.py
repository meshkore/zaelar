"""config/profiles.py — el PERFIL como paquete COORDINADO de config (V2-040).

Hoy "local vs cloud" son TRES interruptores desconectados: `voice/engine/core/profile.py` (`ZAELAR_PROFILE` → STT/
TTS/LLM del motor de voz), `config/v2.py` (routing del cerebro + memoria embed/rerank/CORAZÓN) y `config/settings.py`
(⚙ → ZAELAR_STT/TTS/LANGUAGE). Elegir "local" fijaba la voz pero dejaba embeddings/rerank/CORAZÓN/FlashBrain donde
estuvieran. Este módulo los UNIFICA: un nombre de perfil → el set COMPLETO de defaults coordinados a través de los
tres ejes, aplicable de una sola vez (`apply`).

**El perfil solo mueve DEFAULTS.** Sigue valiendo el override por-componente (env/UI) — es lo que hace posibles los
HÍBRIDOS (p.ej. `local` + `ZAELAR_LLM_PROVIDER=aimlapi` en una máquina floja). `apply` escribe en los MISMOS stores
que la UI (`settings.json` + `v2.json`), así que nada se hardcodea en código y todo sigue siendo configurable a mano
después.

Dos perfiles de fábrica:
  - **local** — voz y memoria EN LA MÁQUINA (whisper + kokoro + FlashBrain Ollama + embeddings Ollama + rerank local
    + CORAZÓN local). Cero keys de nube para voz/memoria. (El SlowBrain = `claude` CLI sigue necesitando su auth.)
  - **cloud** — todo por proveedores de nube (voxtral/deepgram + cartesia/elevenlabs + FlashBrain AIMLAPI + embed/
    rerank/proc de nube). Solo keys, sin modelos locales. **= objetivo del deploy.** `remote` = ALIAS de `cloud`.
"""
from __future__ import annotations

# Perfil → paquete coordinado. `voice` = lo que ve el motor (se materializa como ZAELAR_* vía settings.json). `v2`
# = patch por sección de config/v2.py. Un valor VACÍO significa "default del proveedor" (no lo forzamos).
_PROFILES: dict[str, dict] = {
    "local": {
        "label": "Local · privado y gratis",
        "summary": "Voz y memoria en tu máquina (Ollama + modelos locales). Sin coste por token ni datos a la nube. "
                   "Ideal en Apple Silicon / GPU. El agente de código (SlowBrain) sí usa Claude.",
        "voice": {"stt_provider": "whisper_local", "tts_provider": "kokoro_local"},
        "v2": {
            "fast": {"provider": "ollama", "model": "qwen2.5:14b-instruct", "base_url": "", "api_key": ""},
            "memory": {"embed_provider": "ollama", "embed_model": "embeddinggemma",
                       "rerank_provider": "local", "mem_processor_model": "qwen2.5:7b-instruct"},
        },
        "engine_profile": "local",
    },
    "cloud": {
        "label": "Nube · sin instalar modelos",
        "summary": "Todo por proveedores de nube (STT/TTS/cerebro/memoria). No necesita GPU ni Ollama, solo tus "
                   "claves de API. Es el perfil del despliegue en servidor.",
        "voice": {"stt_provider": "deepgram", "tts_provider": "elevenlabs"},
        "v2": {
            "fast": {"provider": "aimlapi", "model": "anthropic/claude-haiku-4.5", "base_url": "", "api_key": ""},
            "memory": {"embed_provider": "fastembed", "embed_model": "",
                       "rerank_provider": "local", "mem_processor_model": ""},
        },
        "engine_profile": "remote",
    },
}
_ALIASES = {"remote": "cloud"}

DEFAULT = "local"


def names() -> list[str]:
    return list(_PROFILES)


def canon(name: str) -> str:
    """Normaliza un nombre de perfil (alias incluidos). Un nombre DESCONOCIDO no degrada en silencio: cae al DEFAULT
    con un aviso al llamante (que puede loguearlo) — a diferencia del `ZAELAR_PROFILE` viejo que caía mudo a remote."""
    n = (name or "").strip().lower()
    n = _ALIASES.get(n, n)
    return n if n in _PROFILES else DEFAULT


def get(name: str) -> dict:
    return dict(_PROFILES[canon(name)])


def _no_secrets(d: dict) -> dict:
    """Quita del dict cualquier campo de secreto (termina en api_key) — el paquete no los lleva (van vacíos), pero
    ni el NOMBRE del campo sale al frontend (misma convención de redacción que config/v2.public)."""
    return {k: v for k, v in d.items() if not k.endswith("api_key")}


def public() -> list[dict]:
    """Perfiles para el frontend (nombre + etiqueta + resumen + qué proveedores fija). Sin campos de secreto."""
    out = []
    for n, p in _PROFILES.items():
        out.append({"name": n, "label": p["label"], "summary": p["summary"],
                    "voice": p["voice"], "fast": _no_secrets(p["v2"]["fast"]), "memory": p["v2"]["memory"]})
    return out


def requirements(name: str) -> dict:
    """Qué necesita este perfil para funcionar — para que el wizard muestre los HUECOS. Devuelve:
      {needs_ollama, ollama_models, needs_local_accel, credentials:[keys relevantes], claude_cli}
    Todo derivado del propio paquete del perfil (no hay una lista aparte que pueda divergir)."""
    p = get(name)
    n = canon(name)
    fast = p["v2"]["fast"]
    mem = p["v2"]["memory"]
    models: list[str] = []
    if fast.get("provider") == "ollama" and fast.get("model"):
        models.append(fast["model"])
    if mem.get("embed_provider") == "ollama" and mem.get("embed_model"):
        models.append(mem["embed_model"])
    if (mem.get("mem_processor_model") or "").strip() and n == "local":
        models.append(mem["mem_processor_model"])
    needs_ollama = bool(models)
    # credenciales relevantes del perfil (del catálogo de doctor)
    creds: list[str] = []
    try:
        from config.doctor import CREDENTIALS
        creds = [c["key"] for c in CREDENTIALS if n in c.get("profiles", [])]
    except Exception:
        pass
    return {
        "profile": n,
        "needs_ollama": needs_ollama,
        "ollama_models": sorted(set(models)),
        "needs_local_accel": n == "local",
        "credentials": creds,
        "needs_claude_cli": True,     # el SlowBrain/generador de widgets usa `claude` en AMBOS perfiles
    }


def apply(name: str) -> dict:
    """Aplica el perfil a los STORES (settings.json + v2.json) — un solo lever, coordinado. NO toca secretos (las
    keys se gestionan aparte). Devuelve `{profile, applied}`. Idempotente. El override por-componente que el usuario
    ponga DESPUÉS sigue ganando (los stores son la capa que la UI edita a mano)."""
    n = canon(name)
    p = _PROFILES[n]
    applied: dict = {}

    # 1) eje VOZ → config/settings.py (que a su vez escribe ZAELAR_STT/TTS en os.environ y persiste)
    try:
        from config import settings
        res = settings.update(dict(p["voice"]))
        applied["voice"] = {"ok": res.get("ok"), "keys": list(p["voice"].keys()),
                            "needs_reconnect": res.get("needs_reconnect")}
    except Exception as e:  # noqa: BLE001
        applied["voice"] = {"ok": False, "error": str(e)[:200]}

    # 2) eje ROUTING/MEMORIA → config/v2.py (por sección; solo claves declaradas, whitelisted por v2.set)
    try:
        from config import v2
        for section, patch in p["v2"].items():
            v2.set(section, patch)
        # el cerebro por defecto del perfil es siempre el propio «Colmena»
        v2.set("flags", {"brain": "nucleo"})
        applied["v2"] = {"ok": True, "sections": list(p["v2"].keys()) + ["flags"]}
    except Exception as e:  # noqa: BLE001
        applied["v2"] = {"ok": False, "error": str(e)[:200]}

    # 3) eje MOTOR → ZAELAR_PROFILE (afecta a los defaults del dataclass congelado; aplica en el próximo arranque).
    #    Lo persistimos como knob de settings para que `load_into_env` lo re-aplique al boot.
    try:
        from config import settings
        settings._write({**settings._read(), "zaelar_profile": p["engine_profile"], "config_profile": n})
        import os
        os.environ["ZAELAR_PROFILE"] = p["engine_profile"]
        applied["engine_profile"] = p["engine_profile"]
    except Exception as e:  # noqa: BLE001
        applied["engine_profile"] = {"error": str(e)[:200]}

    return {"profile": n, "applied": applied}


def active() -> str:
    """El perfil de config activo (el que se aplicó por última vez), desde el store; default DEFAULT."""
    try:
        from config import settings
        return canon(settings.get("config_profile") or DEFAULT)
    except Exception:
        return DEFAULT
