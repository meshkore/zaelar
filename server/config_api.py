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
        # CERRADO A PROPÓSITO (2026-08-12, norma del operador): el modelo del FlashBrain se ELIGE de una lista, no se
        # teclea, y la lista solo lleva lo que el benchmark avala. Un modelo mal elegido aquí no da un error: da un
        # agente que hace lo que no es (el veto de grok existe justo por eso), y eso es indistinguible de un bug.
        # Fuera, por tanto: `xai`/grok (VETADO en la capa de voz — mis-rutea preguntas de memoria y manda una
        # investigación a `web_search`, re-medido §9.1.b), `openai` y `mistral` directos (la norma es UNA sola cuenta
        # de API: todo lo comercial pasa por el broker AIMLAPI) y `zai` (razonador → viola voz=no-razonador).
        "providers": [
            {"id": "aimlapi", "label": "AIMLAPI (broker — the one account we manage)",
             "base_url": "https://api.aimlapi.com/v1", "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["anthropic/claude-haiku-4.5", "deepseek/deepseek-v4-flash"]},
            {"id": "groq", "label": "Groq (cloud, fastest — routes worse)",
             "base_url": "https://api.groq.com/openai/v1", "key_env": "GROQ_API_KEY", "cloud": True,
             "models": ["llama-3.3-70b-versatile"]},
            {"id": "ollama", "label": "Ollama (local/free — slow, offline fallback)",
             "base_url": "http://localhost:11434/v1", "key_env": "", "cloud": False,
             "models": ["qwen2.5:14b-instruct"]},
        ],
        "closed_models": True,      # la UI pinta un desplegable, no un campo de texto
        "note": "NON-reasoners only (the voice turn must close fast) and only benchmark-endorsed ones. "
                "claude-haiku-4.5 = production default (reliable routing + introspection). "
                "deepseek-v4-flash = the ONLY one that routed 12/12 in §9. Endpoint comes from the provider — "
                "there is no URL to type.",
    },
    "code_agent": {                 # Brain Workers — el agente headless que CONDUCE las tareas
        # Modelos REALES por proveedor (2026-08-12). Antes esta lista estaba VACÍA para los dos, así que la UI
        # pintaba un campo libre: el operador cambiaba a Codex y se quedaban los `glm-5.2` del proveedor anterior
        # —un modelo que Codex no sirve— y la tarea moría con «There's an issue with the selected model». Un
        # proveedor solo puede ofrecer SUS modelos.
        "providers": [
            {"id": "claude_code", "label": "Claude Code (CLI)", "cloud": True,
             # DOS familias, y las dos son legítimas para ESTE proveedor: los alias de la licencia propia, y los
             # modelos de los escalones de RELEVO Anthropic-compatible (`workers/providers.py`), porque quien
             # conduce sigue siendo Claude Code — solo cambia el endpoint por debajo. Dejar fuera los del relevo
             # habría marcado como inválida la config que el operador tiene HOY funcionando (claude_code +
             # glm-5.2 + endpoint de Z.AI), que es correcta.
             "models": ["opus", "sonnet", "haiku", "sonnet[1m]", "opus[1m]",
                        "glm-5.2", "glm-4.6", "kimi-k2.6"],
             "note": "Can restrict Bash to our bridges only (single-writer invariant) → the only backend valid for "
                     "untrusted input (deny_tools) and cluster dev workers. The glm-*/kimi-* entries belong to the "
                     "relay tiers (Z.AI / Moonshot subscription plans): they only work while that endpoint is the "
                     "active tier — see workers/providers.py."},
            {"id": "codex", "label": "Codex (CLI)", "cloud": True,
             # VERIFICADO contra la lista que devuelve el propio servidor de modelos (2026-08-12): son estos tres.
             # No hay familia 5.6 disponible — un `gpt-5.6-*` en el config.toml no lo sirve la API.
             "models": ["gpt-5.5", "gpt-5.4", "gpt-5.4-mini"],
             "note": "Has NO tool allowlist — only sandbox modes, so a Codex worker runs a full shell "
                     "(wider blast radius). Refused for untrusted input and dev workers."},
            {"id": "grok_build", "label": "Grok Build (CLI)", "cloud": True, "key_env": "XAI_API_KEY",
             # VERIFICADO con `grok models` contra la cuenta real (2026-08-13).
             "models": ["grok-4.5", "grok-4.6", "grok-build-0.1", "grok-4.3",
                        "grok-4.20-0309-non-reasoning"],
             "note": "Same wire format AND same allowlist syntax as Claude Code — verified it enforces "
                     "`--deny Bash(...)`, so it CAN hold the single-writer invariant (unlike Codex). "
                     "Pay-per-token: watch the cost, a trivial turn already costs ~$0.03 (large system prompt)."},
        ],
        "closed_models": True,
        # PRESETS (2026-08-13, petición del operador): una opción de Brain Worker no es «un proveedor», es la
        # COMBINACIÓN de quién conduce (el CLI) y quién razona por debajo (el endpoint + su modelo). Elegir las tres
        # piezas a mano es donde se producían los desajustes (`glm-5.2` sobre Codex, `gpt-5.5` sobre Z.AI): un
        # preset las mueve JUNTAS y de una vez. El operador puede seguir afinando a mano después.
        "presets": [
            {"id": "cc_zai", "label": "Claude Code + Z.AI (GLM-5.2)", "provider": "claude_code",
             "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "key_env": "Z_AI_API_KEY",
             "billing": "subscription", "cost": "GLM coding plan (flat rate)",
             "note": "The operator's rule: subscription plans, never pay-per-token. Quota is WEEKLY and when it "
                     "runs out everything on this tier dies at once — that is what the relay chain exists for."},
            {"id": "cc_deepseek", "label": "Claude Code + DeepSeek V4", "provider": "claude_code",
             "base_url": "https://api.deepseek.com/anthropic", "model": "sonnet", "key_env": "DEEPSEEK_API_KEY",
             "billing": "per_token", "cost": "~$0.14/$0.28 per Mtok (v4-flash)",
             "note": "Its gateway MAPS Claude aliases: sonnet/haiku → deepseek-v4-flash, opus → deepseek-v4-pro. "
                     "So the model field is the Claude alias, not a DeepSeek name. Cheapest of the three."},
            {"id": "grok45", "label": "Grok Build + Grok 4.5", "provider": "grok_build",
             "base_url": "", "model": "grok-4.5", "key_env": "XAI_API_KEY",
             "billing": "per_token", "cost": "pay-per-token — measured ~$0.03 for a trivial turn",
             "note": "Native xAI agent CLI. Grok 4.6 ($2/$6 per Mtok, 500k ctx, reasoning) is selectable as the "
                     "model if quality beats cost."},
            {"id": "cc_local", "label": "Claude Code + local licence", "provider": "claude_code",
             "base_url": "", "model": "", "key_env": "",
             "billing": "licence", "cost": "the operator's own Claude licence",
             "note": "LOCAL ONLY — a browser login does not exist inside a container, so this tier cannot be the "
                     "cloud's coverage. It is the last rung of the relay chain."},
        ],
        "note": "Headless agent that drives tasks (memory/web/code). Per-task-type model optional. "
                "Each provider serves ONLY its own models. Pick a preset to move CLI + endpoint + model together.",
    },
    "memory_processor": {           # CORAZÓN de escritura (mem_processor / distiller de píldoras)
        "providers": [
            {"id": "aimlapi", "label": "AIMLAPI (broker — the one account we manage)",
             "base_url": "https://api.aimlapi.com/v1", "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["deepseek/deepseek-v4-flash", "google/gemini-2.5-flash", "openai/gpt-4.1-mini"]},
            {"id": "ollama", "label": "Ollama (local — only if local usage is accepted)", "base_url": "http://localhost:11434/v1",
             "key_env": "", "cloud": False, "models": ["qwen2.5:7b-instruct", "qwen2.5:3b"]},
        ],
        # Actualizado 2026-08-09: la etiqueta anterior («RULE: memory ALWAYS OpenAI») quedó DEROGADA por el bench
        # §12.3 y por la norma de una sola cuenta de API. Se elige con datos, no por reputación del proveedor.
        "note": "Off-hot-path (does not touch voice latency) but WRITE-COMPLETENESS is the nº1 lever of recall. "
                "BENCHMARKED 2026-08-09 (21 candidates × 34 cases, see zaelar-model-benchmarks.md §12.3): "
                "deepseek-v4-flash ties gpt-4.1-mini on capture (98.5 vs 98.9%) and precision (100%) for −55% cost "
                "→ CHOSEN; fallback gemini-2.5-flash → gpt-4.1-mini. ⛔ gpt-4o-mini is VETOED: it files an allergy "
                "under slot=operator.diet, and a slot invalidates every earlier pill with that slot — a later diet "
                "change would erase the allergy. Everything goes through the AIMLAPI broker (one account).",
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
            {"id": "aimlapi", "label": "AIMLAPI (broker — the one account we manage)",
             "base_url": "https://api.aimlapi.com/v1", "key_env": "AIMLAPI_KEY", "cloud": True,
             "models": ["openai/gpt-4.1-mini", "openai/gpt-4.1", "anthropic/claude-haiku-4.5",
                        "deepseek/deepseek-v4-flash"]},
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


def _detected_code_agents() -> dict:
    """¿Qué CLI de Brain Worker está instalado en ESTA máquina, y con qué versión/modelo por defecto?

    Existe porque la UI ofrecía los dos proveedores por igual sin que nada comprobara si el binario estaba: el
    operador elegía Codex, guardaba, y el fallo aparecía minutos después dentro de una tarea muerta. Elegir un
    proveedor que no está instalado tiene que verse ANTES de guardar, en el propio desplegable.

    Barato (`--version` local) y NUNCA lanza: si la detección falla, la UI simplemente no marca nada."""
    det: dict = {}
    try:
        from nucleo.workers import codex_session as _cx
        det["codex"] = _cx.detect()
    except Exception:
        det["codex"] = {"installed": False}
    try:
        import subprocess

        from nucleo.workers import claude_session as _cc
        path = _cc._find_claude()
        det["claude_code"] = {"installed": bool(path), "path": path, "version": "", "default_model": ""}
        if path:
            # La versión también AQUÍ. Codex y Grok la enseñaban y Claude Code no, así que en el panel el proveedor
            # de PRODUCCIÓN era el único sin sello — que es justo la asimetría que hace dudar de si está detectado
            # de verdad. `claude --version` responde «2.1.212 (Claude Code)»: el primer token es la versión.
            try:
                r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8)
                det["claude_code"]["version"] = ((r.stdout or r.stderr or "").strip().split() or [""])[0]
            except Exception:
                pass
    except Exception:
        det["claude_code"] = {"installed": False}
    try:
        from nucleo.workers import grok_session as _gk
        det["grok_build"] = _gk.detect()
    except Exception:
        det["grok_build"] = {"installed": False}
    return det


def _catalog_for_ui() -> dict:
    """El catálogo con la detección de CLIs INYECTADA en cada proveedor de `code_agent` (copia superficial: el
    catálogo del módulo es una constante y no se muta)."""
    cat = dict(_PROVIDER_CATALOG)
    try:
        det = _detected_code_agents()
        ca = dict(cat["code_agent"])
        provs = []
        for p in ca.get("providers", []):
            p = dict(p)
            d = det.get(p["id"]) or {}
            p["detected"] = bool(d.get("installed"))
            if d.get("version"):
                p["version"] = d["version"]
            # Un default que el propio CLI ya usa gana a cualquiera que eligiéramos nosotros — PERO solo si ese
            # modelo existe. El caso real que motiva la guarda: `~/.codex/config.toml` pedía `gpt-5.6-sol`, que la
            # API no sirve para esta cuenta; usarlo de default habría propuesto en la UI un modelo condenado a
            # fallar, y descartarlo en silencio habría escondido que su config apunta a algo que no existe.
            dm = d.get("default_model") or ""
            if dm:
                if dm in (p.get("models") or []):
                    p["default_model"] = dm
                else:
                    p["stale_default"] = dm
            provs.append(p)
        ca["providers"] = provs
        # PRESETS: cada uno se marca READY o no, y por qué. Un preset que no puede funcionar (CLI ausente o clave
        # sin poner) tiene que verse ANTES de elegirlo: elegirlo a ciegas es lo que producía una tarea muerta sin
        # relación aparente con lo que el operador había guardado.
        import os as _os
        pres = []
        for p in ca.get("presets", []):
            p = dict(p)
            d = det.get(p["provider"]) or {}
            cli_ok = bool(d.get("installed"))
            env = p.get("key_env") or ""
            key_ok = (not env) or bool((_os.getenv(env) or "").strip())
            p["cli_ok"], p["key_ok"], p["ready"] = cli_ok, key_ok, bool(cli_ok and key_ok)
            p["blocked_by"] = ("cli" if not cli_ok else ("key" if not key_ok else ""))
            pres.append(p)
        ca["presets"] = pres
        cat["code_agent"] = ca
    except Exception:
        pass
    return cat


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
    out["catalog"] = _catalog_for_ui()
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


_MODEL_FIELDS = {"fast": ("model",),
                 "code_agent": ("model", "model_memory", "model_web", "model_code")}


def _model_mismatch(section: str, patch: dict) -> str:
    """¿Se está guardando un modelo que el proveedor elegido NO sirve? Devuelve el motivo, o "" si todo cuadra.

    El fallo que cierra: al cambiar de proveedor, los modelos del anterior se quedaban puestos (Codex con cinco
    campos a `glm-5.2`). Guardar salía OK y el error aparecía minutos después, DENTRO de una tarea, como «There's
    an issue with the selected model» — el operador no tiene forma de relacionar eso con lo que guardó. Un
    desajuste de config se rechaza AQUÍ, con el nombre de lo que sobra.

    Solo aplica a las secciones de lista CERRADA y solo si el proveedor declara modelos: un proveedor sin lista
    (o una sección abierta) sigue aceptando lo que el llamador ponga — esto valida, no encierra."""
    conf = _PROVIDER_CATALOG.get(section) or {}
    if not conf.get("closed_models"):
        return ""
    prov_id = str(patch.get("provider") or "").strip()
    if not prov_id:
        return ""
    prov = next((p for p in conf.get("providers", []) if p.get("id") == prov_id), None)
    if prov is None:
        return f"unknown provider «{prov_id}» for {section}"
    allowed = set(prov.get("models") or [])
    if not allowed:
        return ""
    for field in _MODEL_FIELDS.get(section, ()):
        val = str(patch.get(field) or "").strip()
        if val and val not in allowed:
            return (f"«{val}» is not served by {prov.get('label') or prov_id} (field {field}). "
                    f"Available: {', '.join(sorted(allowed))}")
    return ""


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
    bad = _model_mismatch(section, patch)
    if bad:
        return JSONResponse({"ok": False, "error": bad}, status_code=400)
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
