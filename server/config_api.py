"""server/config_api.py — plano de control de la CONFIGURACIÓN completa (V2-043).

El área de configuración full-screen del frontend (elegir QUÉ API/modelo usa CADA pieza + resumen de APIs con
saldo) se apoya aquí. Config gestionada por la UI (invariante de producto): el usuario lo cambia TODO desde la
interfaz, nunca editando ficheros. Reúne lo que ya existía disperso (v2.py, settings.py, connectors.py,
credentials.py, doctor.py, spotify) bajo una sola boca — sin duplicar la lógica, delegando en cada módulo dueño.

  · GET  /api/config            → vista agregada REDACTADA (nunca una key en claro): v2 (fast/code_agent/memory/
                                   flags) + voz (settings) + conectores + spotify + credenciales + catálogo de
                                   proveedores por pieza + resumen de APIs con saldo.
  · POST /api/config/v2         → {section, patch} → v2.set(section, patch) (por pieza: modelo/proveedor/params).
  · POST /api/config/credential → {key|provider, value} → credentials.set_key (resuelve provider→env por doctor).
  · GET  /api/config/apis       → resumen/alertas de saldo (proactivo donde se expone + reactivo por último error).

Loopback (app local single-user), como el resto de la API. Voz sigue por `/api/settings`; el área de config la
consume igual. Los cambios de v2 (fast/code_agent/memory) son POR INVOCACIÓN → aplican sin reconectar.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

# Sections of config/v2.json that pick a PROVIDER/model (as opposed to `flags`, which doesn't). In the
# cloud profile (ZAELAR_USER_ID set) these are centrally managed by the operator, not user-editable —
# see INI-019 addenda "Cambio B", 2026-08-05. Self-host is completely unaffected (is_cloud_account()
# is always False there) — this NEVER restricts the OSS product, only the hosted cloud accounts.
_CLOUD_LOCKED_V2_SECTIONS = frozenset({"fast", "code_agent", "memory", "triage", "susurro"})


# Catálogo de PROVEEDORES por pieza (hints para los desplegables de la UI). No es exhaustivo ni obliga a nada —
# el usuario puede teclear un modelo/base_url a mano; esto solo acelera la elección. Cloud vs local marcado.
_PROVIDER_CATALOG = {
    "fast": {                       # FlashBrain — NO-razonador, por invocación
        "providers": [
            {"id": "xai", "label": "xAI (grok, direct)", "base_url": "https://api.x.ai/v1", "key_env": "XAI_API_KEY",
             "cloud": True, "models": ["grok-4.20-0309-non-reasoning"]},
            {"id": "aimlapi", "label": "AIMLAPI (cloud)", "base_url": "https://api.aimlapi.com/v1",
             "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["anthropic/claude-haiku-4.5", "x-ai/grok-4-fast-non-reasoning", "deepseek/deepseek-v4-flash"]},
            {"id": "zai", "label": "Z.AI (GLM, direct — under evaluation 2026-07-26)",
             "base_url": "https://api.z.ai/api/anthropic", "key_env": "Z_AI_API_KEY", "cloud": True,
             "models": ["glm-4.5-air", "glm-4.6", "glm-5.2"]},
            {"id": "groq", "label": "Groq (cloud, fast)", "base_url": "https://api.groq.com/openai/v1",
             "key_env": "GROQ_API_KEY", "cloud": True, "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]},
            {"id": "openai", "label": "OpenAI (cloud, reliable tool-calling)", "base_url": "https://api.openai.com/v1",
             "key_env": "OPENAI_API_KEY", "cloud": True, "models": ["gpt-4o-mini", "gpt-4.1-mini"]},
            {"id": "mistral", "label": "Mistral (cloud)", "base_url": "https://api.mistral.ai/v1",
             "key_env": "MISTRAL_API_KEY", "cloud": True, "models": ["mistral-small-latest"]},
            {"id": "ollama", "label": "Ollama (local/free)", "base_url": "http://localhost:11434/v1",
             "key_env": "", "cloud": False, "models": ["qwen2.5:14b-instruct", "qwen2.5:7b-instruct"]},
        ],
        "note": "Only NON-reasoners (the voice turn must close fast). Local is free but slower.",
    },
    "code_agent": {                 # SlowBrain / workers
        "providers": [
            {"id": "claude_code", "label": "Claude Code (CLI)", "cloud": True, "models": []},
            {"id": "codex", "label": "Codex (CLI)", "cloud": True, "models": []},
        ],
        "note": "Headless agent that drives tasks (memory/web/code). Per-task-type model optional.",
    },
    "memory_processor": {           # CORAZÓN de escritura (mem_processor / distiller de píldoras)
        "providers": [
            {"id": "openai", "label": "OpenAI (RULE: memory ALWAYS OpenAI)", "base_url": "https://api.openai.com/v1",
             "key_env": "OPENAI_API_KEY", "cloud": True, "models": ["gpt-4.1-mini", "gpt-4o"]},
            {"id": "ollama", "label": "Ollama (local — only if local usage is accepted)", "base_url": "http://localhost:11434/v1",
             "key_env": "", "cloud": False, "models": ["qwen2.5:7b-instruct", "qwen2.5:3b"]},
        ],
        "note": "Off-hot-path (does not touch voice latency) but WRITE-COMPLETENESS is the nº1 lever of recall. "
                "TESTED 2026-07-17: gpt-4o-mini swallows the allergy (0 pills); gpt-4.1-mini catches it → CHOSEN. "
                "Operator rule: memory ALWAYS via OpenAI.",
    },
    "triage": {                     # clasificador de mensajería (relevancia WhatsApp/Telegram)
        "providers": [
            {"id": "xai", "label": "xAI grok (cheap, uses existing credit)", "base_url": "https://api.x.ai/v1",
             "key_env": "XAI_API_KEY", "cloud": True, "models": ["grok-4.20-0309-non-reasoning"]},
            {"id": "openai", "label": "OpenAI", "base_url": "https://api.openai.com/v1",
             "key_env": "OPENAI_API_KEY", "cloud": True, "models": ["gpt-4o-mini"]},
            {"id": "ollama", "label": "Ollama (local — PRIVATE, nothing leaves the machine)", "base_url": "http://localhost:11434/v1",
             "key_env": "", "cloud": False, "models": ["qwen2.5:3b"]},
        ],
        "note": "⚠️ PRIVACY: in external mode, personal messages LEAVE to the cloud (that is why it used to be local). "
                "Simple classification task (no tool-routing) → grok is fine. Operator accepted the tradeoff (battery).",
    },
    "susurro": {                    # «Susurro» (V2-053) — auditor conversacional off-hot-path
        "providers": [
            {"id": "openai", "label": "OpenAI (same key as memory)", "base_url": "https://api.openai.com/v1",
             "key_env": "OPENAI_API_KEY", "cloud": True, "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-4o"]},
            {"id": "xai", "label": "xAI grok", "base_url": "https://api.x.ai/v1",
             "key_env": "XAI_API_KEY", "cloud": True, "models": ["grok-4.20-0309-non-reasoning"]},
            {"id": "off", "label": "Disabled (enabled=false)", "cloud": False},
        ],
        "note": "Audits stretches with FRICTION (complaint/repetition/failure) and returns structured corrections. "
                "OUTSIDE the voice path → here a reasoner IS worth it (benchmark §10 pending). "
                "pulse_turns=0 → friction only; N → also every N turns.",
    },
    "memory_embed": {
        "providers": [
            {"id": "auto", "label": "Auto (ollama→fastembed→hash)", "cloud": False},
            {"id": "ollama", "label": "Ollama (local)", "cloud": False, "models": ["embeddinggemma", "bge-m3"]},
            {"id": "fastembed", "label": "fastembed (local CPU)", "cloud": False},
            {"id": "openai", "label": "OpenAI (cloud)", "cloud": True, "key_env": "OPENAI_API_KEY"},
            {"id": "voyage", "label": "Voyage (cloud)", "cloud": True, "key_env": "VOYAGE_API_KEY"},
        ],
        "note": "Changing the embedding REQUIRES re-embed (memory/reembed.py). Local by default.",
    },
    "memory_rerank": {
        "providers": [
            {"id": "local", "label": "Local (jina, CPU/free)", "cloud": False},
            {"id": "openai", "label": "OpenAI (listwise, cloud)", "cloud": True, "key_env": "OPENAI_API_KEY"},
            {"id": "cohere", "label": "Cohere (cloud)", "cloud": True, "key_env": "COHERE_API_KEY"},
            {"id": "voyage", "label": "Voyage (cloud)", "cloud": True, "key_env": "VOYAGE_API_KEY"},
            {"id": "off", "label": "Disabled", "cloud": False},
        ],
        "note": "Reorders LONG recall (off-hot-path). Local raises recall@1 at no cost.",
    },
}


@router.get("/api/config")
async def get_config():
    """Vista agregada REDACTADA para el área de configuración. NUNCA contiene una API key en claro."""
    out: dict = {}
    try:
        from config import v2
        out["v2"] = v2.public_all()
    except Exception as e:  # noqa: BLE001
        out["v2"] = {"error": str(e)[:120]}
    try:
        from config import settings
        out["voice"] = settings.effective()
    except Exception as e:  # noqa: BLE001
        out["voice"] = {"error": str(e)[:120]}
    try:
        from config import connectors
        out["connectors"] = connectors.public_all()
    except Exception as e:  # noqa: BLE001
        out["connectors"] = {"error": str(e)[:120]}
    try:
        from connectors.spotify import auth as _sp
        out["spotify"] = _sp.status()
    except Exception:
        out["spotify"] = {"can_connect": False}
    try:
        from config import doctor
        out["credentials"] = doctor.credentials()
    except Exception:
        out["credentials"] = []
    out["catalog"] = _PROVIDER_CATALOG
    try:
        from nucleo import cloud_account
        out["cloud_profile"] = cloud_account.is_cloud_account()
    except Exception:
        out["cloud_profile"] = False
    try:
        from config import balances
        out["apis"] = balances.summary_with_workers()
    except Exception:
        out["apis"] = []
    return JSONResponse(out)


@router.post("/api/config/v2")
async def set_v2(payload: dict | None = None):
    """Escribe una sección de v2 (fast/code_agent/memory/flags) por pieza. `{section, patch}`. Devuelve la vista
    pública (redactada) de esa sección. Los cambios son POR INVOCACIÓN → aplican sin reconectar."""
    payload = payload or {}
    section = (payload.get("section") or "").strip()
    patch = payload.get("patch") or {}
    if not section or not isinstance(patch, dict):
        return JSONResponse({"ok": False, "error": "missing section/patch"}, status_code=400)
    if section in _CLOUD_LOCKED_V2_SECTIONS:
        try:
            from nucleo import cloud_account
            if cloud_account.is_cloud_account():
                return JSONResponse(
                    {"ok": False, "error": "provider/model selection is centrally managed in the cloud profile"},
                    status_code=403,
                )
        except Exception:
            pass
    try:
        from config import v2
        v2.set(section, patch)
        return JSONResponse({"ok": True, "section": section, "config": v2.public(section)})
    except KeyError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:160]}, status_code=500)


@router.post("/api/config/credential")
async def set_credential(payload: dict | None = None):
    """Guarda/actualiza una credencial en el store (chmod 600). `{key|provider, value}`. Resuelve un `provider`
    conocido (aimlapi/xai/groq/elevenlabs…) a su variable de entorno principal vía el catálogo de doctor; o acepta
    un nombre de env literal (power-user). Valor vacío = borra. NUNCA devuelve el valor."""
    payload = payload or {}
    raw = (payload.get("key") or payload.get("provider") or "").strip()
    value = payload.get("value")
    if not raw:
        return JSONResponse({"ok": False, "error": "missing key/provider"}, status_code=400)
    env_name = raw
    try:
        from config import doctor
        for c in doctor.CREDENTIALS:
            if c["key"] == raw and c.get("env"):
                env_name = c["env"][0]           # variable principal del proveedor
                break
    except Exception:
        pass
    try:
        from config import credentials
        credentials.set_key(env_name, value or "")
        return JSONResponse({"ok": True, "key": raw, "env": env_name, "set": bool(value)})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(e)[:160]}, status_code=500)


@router.get("/api/config/benchmarks")
async def get_benchmarks():
    """Réplica CURADA (solo lectura) de las decisiones de modelo — de dónde sale cada elección, coste, latencia,
    fiabilidad de tool-calling/alucinación, y qué candidatos se han evaluado. Ver `config/model_benchmarks.py`."""
    try:
        from config import model_benchmarks
        return JSONResponse(model_benchmarks.snapshot())
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"modules": [], "error": str(e)[:160]})


@router.get("/api/config/apis")
async def get_apis(refresh: bool = False):
    """Resumen de APIs/servicios externos con SALDO (proactivo donde se expone + reactivo por último error).
    Para el resumen de la config y las alertas del diálogo de estado. `refresh=1` fuerza resondeo."""
    try:
        from config import balances
        return JSONResponse({"apis": balances.summary_with_workers(refresh=refresh), "alerts": balances.alerts(refresh=refresh)})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"apis": [], "alerts": [], "error": str(e)[:120]})


# ── Conectores (V2-083) — registro único + control de los que se autentican por TOKEN dinámico ──────────────
@router.get("/api/connectors")
async def get_connectors():
    """Inventario ÚNICO de conectores (mensajería/música/infra) con estado + config REDACTADA — para la pestaña
    Conectores. Las escrituras van por los endpoints de cada familia (`/api/messaging/*`, `/api/spotify/*`,
    `/api/meshkore/*`) + los de architect de aquí abajo."""
    try:
        from connectors import registry
        return JSONResponse({"connectors": registry.descriptors()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"connectors": [], "error": str(e)[:160]})


@router.post("/api/connectors/architect/connect")
async def architect_connect(payload: dict):
    """Fija el TOKEN (y url opcional) del daemon Architect en el store DINÁMICO (config/connectors.json), NO en
    .env — configurable/revocable desde la UI. El token es secreto (se redacta al leer)."""
    from config import connectors as cfg
    tok = str((payload or {}).get("token") or "").strip()
    if not tok:
        return JSONResponse({"ok": False, "error": "empty token"}, status_code=400)
    patch = {"token": tok, "enabled": True}
    url = str((payload or {}).get("url") or "").strip()
    if url:
        patch["url"] = url
    cfg.set("architect", patch)
    return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})


@router.post("/api/connectors/architect/disconnect")
async def architect_disconnect():
    """REVOCA el token de Architect (lo borra del store). Deja el conector desconectado."""
    from config import connectors as cfg
    cfg.set("architect", {"token": "", "enabled": False})
    return JSONResponse({"ok": True, "id": "architect", "config": cfg.public("architect")})
