"""config/v2.py — esquema de configuración v2 «Colmena» (ADITIVO, INI V2-001).

Convive con `config/settings.py` (⚙: STT/TTS/voz/idioma) y `config/connectors.py` sin tocarlos — nada se
borra todavía (la limpieza de la config de Hermes/duo es V2-009). Aquí vive lo NUEVO del cerebro v2:

  - **routing de modelos** — el modelo del FlashBrain (capa rápida no-razonadora) y el del CodeAgent del
    SlowBrain. **Modelo POR INVOCACIÓN** (regla dura): esto guarda los DEFAULTS que el llamador lee y pasa en
    cada invocación; NUNCA una env global de modelo que fuerce a todas las sesiones a la vez.
  - **flags** — interruptores de despliegue v2 (memoria, loop orquestador…), para la estrategia strangler-fig.

Igual que el resto de config de zaelar: **la gestiona la UI**, persiste en `config/v2.json` (gitignored, lleva
credenciales), y el store MANDA sobre `.env` (env = fallback power-user/headless). **Vista pública REDACTADA**:
las API keys nunca salen al frontend → `<key>_set: bool`.
"""
import json
import os
import threading
from pathlib import Path

from nucleo import workspace as _workspace

# `<workspace>/config/v2.json` — unset `ZAELAR_WORKSPACE` is byte-identical to the old
# `Path(__file__).resolve().parent / "v2.json"`.
_PATH = _workspace.root() / "config" / "v2.json"
_lock = threading.Lock()

# Forma por sección + defaults. Añadir una capacidad = una entrada aquí.
# NB: los `*_model` son DEFAULTS; el cerebro los pasa POR INVOCACIÓN (nunca una env global de modelo).
_DEFAULTS: dict[str, dict] = {
    # FlashBrain — capa rápida no-razonadora (provider `nucleo`, V2-004). Solo no-razonadores.
    "fast": {
        "provider": "aimlapi",                              # 'ollama' (local) | 'aimlapi' (nube)
        # V2-034 (2026-07-12): default = claude-haiku-4.5. El A/B en el canal de prueba (nucleo/flash/probe.py) sobre
        # la sesión manual del operador mostró que grok-4-fast-non-reasoning "parece tonto": no busca cuando debe
        # (alucina), no razona sobre su propia contradicción y reacciona con acciones espurias a preguntas META.
        # Haiku 4.5 (NO-razonador, validado en AIMLAPI) busca fiable, INTROSPECCIONA sus errores y explica en vez de
        # actuar, a latencia comparable (~2-3s). Sigue siendo POR INVOCACIÓN; se cambia por la UI/config.
        "model": "anthropic/claude-haiku-4.5",              # default; se pasa por invocación
        "base_url": "",
        "api_key": "",
    },
    # SlowBrain — agente de código headless tras la interfaz CodeAgent (V2-006).
    # Modelo POR INVOCACIÓN: `model` es el default global; `model_<kind>` permite un modelo distinto por tipo de
    # tarea (memoria/web/código) — vacío = cae a `model`, y `model` vacío = default del proveedor. El dispatcher
    # los LEE y los pasa en cada `RunSpec` (nunca fija una env global de modelo).
    "code_agent": {
        "provider": "claude_code",                          # 'claude_code' | 'codex'
        "model": "",                                        # default global; vacío = default del proveedor
        "model_memory": "",                                 # agente de MEMORIA ★ (trabajo barato/mecánico)
        "model_web": "",                                    # agentes de trabajo web (V2-007)
        "model_code": "",                                   # agentes de trabajo de código (V2-007)
        "api_key": "",
        # base_url: endpoint Anthropic-compatible EXTERNO para los workers `claude` (2026-07-31). Vacío = la
        # cuenta Anthropic normal del sistema. Si apunta a un proveedor compatible (p.ej. Z.AI GLM coding plan,
        # "una API para usar desde Claude Code"), el worker lo usa vía ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN;
        # el token se resuelve del credential store por endpoint (z.ai → Z_AI_API_KEY), nunca desde este JSON.
        "base_url": "",
        "max_parallel": 3,                                  # POOL: máx sesiones Claude Code concurrentes (V2-036) —
        #                                                     no saturar equipo/tokens; env CODE_AGENT_MAX_PARALLEL.
        # Cadena de RELEVO explícita (2026-08-03): el operador ordena a mano principal→failover→failover (cada uno
        # {name, base_url, env|api_key, model, plan}). `nucleo.workers.providers.chain()` la lee si NO está vacía;
        # vacío (default) = comportamiento de siempre (base_url de arriba + catálogo KNOWN + licencia local).
        "providers": [],
    },
    # Cadena del CEREBRO DE CLUSTER (V2-069 «una sola mente», off-voz — `nucleo.flash.provider_chain`, 2026-08-03).
    # Motiva esto el incidente del 429 de Z.AI: un turno de cluster (heartbeat/reply a un peer) solo tenía UN tier
    # fijado al arrancar el server (`connectors/meshkore/brain.py`), sin relevo — agotada su cuota, el turno moría
    # y se reintentaba SIEMPRE contra el mismo proveedor roto. `providers` (vacío = default) deja al operador fijar
    # a mano principal→failover→failover ({name, base_url, env|api_key, model, plan}); vacío = cadena por defecto
    # construida de las credenciales presentes (Z.AI directo → AIMLAPI/DeepSeek → xAI → Groq), igual que siempre.
    "cluster": {
        "providers": [],
    },
    # Memoria — modelos de RECUPERACIÓN (embedding + reranker), MODEL-AGNOSTIC (V2-030). Igual que `fast`/
    # `code_agent`: DEFAULTS que la memoria lee; local por defecto (autosuficiente con nuestra GPU/CPU), listo
    # para cloud/APIs externas cambiando solo el `*_provider`. Detalle en `zaelar-memory.md §Recuperación`.
    "memory": {
        # Reranker del recall LARGO (off-hot-path, fail-open). Sube el correcto del top-10 al top-1/3.
        # DEFAULT `local` (V2-030): jina-reranker-v2-multilingual en CPU sube recall@1 41.6→56.2% y recall@3
        # empata al techo OpenAI (68.7 vs 69.0%) — gratis, 100% local, sin GPU. `openai` = techo cloud opcional.
        "rerank_provider": "local",            # 'off' | 'local' (fastembed CPU, default) | 'openai' (LLM listwise) | 'cohere'/'voyage'
        "rerank_model": "",                    # vacío = default del proveedor (openai→gpt-4o-mini, local→bge-reranker-base)
        "rerank_base_url": "",                 # endpoint OpenAI-compatible alternativo (vacío = OpenAI)
        "rerank_top_n": 20,                    # nº de candidatos del tope que se reordenan
        "rerank_blend": 0.85,                  # peso del rerank vs score original (recencia/importancia)
        "rerank_api_key": "",                  # secreto (redactado); vacío = OPENAI_API_KEY del entorno
        # Embedding de la memoria (Fase 3: abstracción; el default sigue local, sin re-embed automático).
        "embed_provider": "auto",              # 'auto' (ollama→fastembed→hash) | 'ollama' | 'fastembed' | 'voyage'/'openai' (cloud)
        "embed_model": "embeddinggemma",       # modelo de embedding; cambiarlo EXIGE re-embed (memory/reembed.py)
        "embed_api_key": "",                   # secreto (redactado); solo para proveedores cloud
        # El CORAZÓN de escritura (mem_processor): destila cada turno en píldoras. Va OFF-HOT-PATH (cola async) →
        # **su latencia NO la paga la voz**, y la LECTURA no usa ningún LLM. Por eso el eje de elección es
        # calidad-vs-PRECIO, nunca velocidad: aquí un modelo lento y barato es perfectamente válido.
        #
        # **DEFAULT = `deepseek/deepseek-v4-flash` vía AIMLAPI** (ronda 2026-08-09, benchmarks §12.3). Barrido de 21
        # candidatos comerciales × 34 casos × 4 ejes (`tests/memory/e2e/bot/distiller_bench.py`), 3 pasadas a los
        # finalistas. Sustituye a `gpt-4.1-mini` **por precio a igualdad de calidad útil**: completeness 98,5% vs
        # 98,9% (un solo hecho de diferencia, dentro del ruido), precisión 100% vs 100% (ninguno de los dos ensucia
        # jamás un descarte) y **$0,68 vs $1,516 por 1.000 turnos → −55%**. Deroga la directriz previa «memoria =
        # SIEMPRE OpenAI» (2026-07-17), que se tomó cuando el único contendiente barato medido era gpt-4o-mini.
        #   · Capa/slot 94,4% vs 100% del titular — sus DOS únicos fallos, reproducibles: pierde el «somos cinco» de
        #     una enumeración familiar (el resto de nombres sí los guarda) y no marca `change=update` en una
        #     NEGACIÓN pura («ya no trabajo en X», donde no hay valor nuevo con el que superseder). Ninguno destruye
        #     datos ya guardados.
        #   · ⛔ `gpt-4o-mini` es más barato aún ($0,567) y quedó VETADO: con la alergia dicha en INGLÉS le pone
        #     `slot=operator.diet` (3/3 pasadas + 3/3 en reproducción directa). Un slot INVALIDA todo lo anterior con
        #     ese slot → un futuro «ahora soy vegetariano» borraría la alergia. Es el error que el prompt advierte
        #     por escrito, y en una memoria personal es pérdida de datos silenciosa, no un punto porcentual.
        #   · Fallback si AIMLAPI/DeepSeek cae: `google/gemini-2.5-flash` (96,7/100/100) → `openai/gpt-4.1-mini`.
        #   · MISMO modelo en self-host y en la nube (decisión del operador 2026-08-09: un solo modelo comercial que
        #     sirva en los dos sitios). Los dos sitios que lo fijan por env en cloud —`engine/fly.demo.toml` y
        #     `cloud/provisioner/src/machineConfig.js`— van sincronizados con este default.
        #   · La opción LOCAL (Ollama) sigue disponible apuntando `mem_processor_base_url` a `localhost:11434`.
        "mem_processor_model": "deepseek/deepseek-v4-flash",     # vacío = env MEM_PROCESSOR_MODEL o el fallback
        "mem_processor_base_url": "https://api.aimlapi.com/v1",  # endpoint OpenAI-compatible; a Ollama = local
        "mem_processor_api_key": "",                     # secreto (redactado); vacío = key POR ENDPOINT (AIMLAPI_KEY)
        # Sueño PROFUNDO «fase REM» (V2-056, memory/rem.py): consolidación diaria con LLM — síntesis de clusters
        # de píldoras en INSIGHTS de alto nivel (kind='insight', slot insight:<concepto>, supersede por sueño).
        # Off-hot-path total (lo dispara el loop); modelo por tarea (router nucleo/memllm.py, key por endpoint).
        # Bench de síntesis 2026-07-20 → ver zaelar-model-benchmarks.md §12.
        "rem_model": "gpt-4.1-mini",
        "rem_base_url": "https://api.openai.com/v1",
        "rem_api_key": "",                               # secreto (redactado); vacío = key por endpoint
        "rem_every_hours": 24,                           # cadencia del sueño profundo (mín 1h)
    },
    # Triaje de mensajería (clasificador de relevancia de WhatsApp/Telegram). ⚠️ Antes LOCAL (qwen2.5:3b) por
    # PRIVACIDAD (nada personal salía de la máquina). El operador pidió CERO ejecución local (batería) → pasa a
    # EXTERNO; el mensaje personal ahora SÍ sale a la nube (tradeoff aceptado explícitamente 2026-07-17). Tarea de
    # clasificación simple (no tool-routing) → grok vale y aprovecha el saldo de xAI. Configurable por pieza.
    "triage": {
        "provider": "xai",
        "model": "grok-4.20-0309-non-reasoning",
        "base_url": "https://api.x.ai/v1",
        "api_key": "",                                    # secreto (redactado); vacío = XAI_API_KEY del entorno
    },
    # «Susurro» (V2-053) — auditor conversacional off-hot-path: un modelo POTENTE (aquí SÍ puede ser razonador,
    # está FUERA del camino de voz) recibe conversación+eventos cuando hay FRICCIÓN (queja/repetición/turno
    # degradado/rail fail/worker encallado) y devuelve correcciones de un catálogo CERRADO (F1: repair_say +
    # finding). Kill-switch de 1ª clase: `enabled` (UI) + env ZAELAR_SUSURRO. Fail-open duro: sin key/timeout →
    # no pasa nada. NUNCA modifica BRAIN RULES en runtime (invariante V2-053 §3d).
    "susurro": {
        "enabled": True,
        "provider": "openai",
        # ⚠️ Sigue en OpenAI DIRECTO — ya NO comparte endpoint con la memoria (el CORAZÓN pasó a AIMLAPI el
        # 2026-08-09). Ojo si se re-mide: esa cuenta de OpenAI va muy limitada de tasa (429 con pocas llamadas en
        # vuelo, p50 de 20s medido en el barrido §12.3). Benchmark §10 pendiente.
        "model": "gpt-4.1-mini",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",                          # secreto (redactado); vacío = resuelta por endpoint (OPENAI_API_KEY…)
        "pulse_turns": 0,                       # 0 = solo fricción; N = auditoría ligera además cada N turnos
        "cooldown_s": 60,                       # mínimo entre auditorías (anti-ráfaga)
        "window_turns": 8,                      # turnos de conversación verbatim en la ventana de auditoría
        "recency_window_s": 120,                # solo turnos/eventos de esta ventana entran a la auditoría (anti-contaminación)
    },
    # Flags de despliegue v2. Tras el entierro de Hermes (V2-009) el cerebro por defecto es el propio «Colmena».
    "flags": {
        "brain": "nucleo",                                  # cerebro activo: 'nucleo' (propio) · 'direct'/'local' (baselines)
        "memory_enabled": True,                             # memoria central (V2-002/003)
        "loop_enabled": True,                               # loop orquestador (V2-005)
    },
}

# Claves que NUNCA se devuelven al frontend (→ `<key>_set: bool`). Fail-safe de privacidad. Cualquier clave que
# TERMINE en `api_key` (api_key/rerank_api_key/embed_api_key…) se redacta — no hay que listarlas una a una.
# NB: usar un literal, no builtins.set() — el módulo define una función `set()` que lo sombrearía.
_SECRET_KEYS = {"api_key"}


def _is_secret(key: str) -> bool:
    return key in _SECRET_KEYS or key.endswith("api_key")

# env var de FALLBACK por clave (back-compat / power-user). Solo se consulta si el store no dice nada.
_ENV_FALLBACK = {
    ("fast", "provider"): "FAST_PROVIDER",
    ("fast", "model"): "FAST_MODEL",
    ("fast", "base_url"): "FAST_BASE_URL",
    ("fast", "api_key"): "FAST_API_KEY",
    ("code_agent", "provider"): "CODE_AGENT_PROVIDER",
    ("code_agent", "model"): "CODE_AGENT_MODEL",
    ("code_agent", "model_memory"): "CODE_AGENT_MODEL_MEMORY",
    ("code_agent", "model_web"): "CODE_AGENT_MODEL_WEB",
    ("code_agent", "model_code"): "CODE_AGENT_MODEL_CODE",
    ("code_agent", "api_key"): "CODE_AGENT_API_KEY",
    ("code_agent", "base_url"): "CODE_AGENT_BASE_URL",
    ("memory", "rerank_provider"): "MEMORY_RERANK",
    ("memory", "rerank_model"): "MEMORY_RERANK_MODEL",
    ("memory", "rerank_base_url"): "MEMORY_RERANK_BASE_URL",
    ("memory", "rerank_top_n"): "MEMORY_RERANK_TOP_N",
    ("memory", "rerank_blend"): "MEMORY_RERANK_BLEND",
    ("memory", "rerank_api_key"): "MEMORY_RERANK_KEY",
    ("memory", "embed_provider"): "ZAELAR_EMBED_BACKEND",
    ("memory", "embed_model"): "ZAELAR_EMBED_MODEL",
    ("memory", "mem_processor_model"): "MEM_PROCESSOR_MODEL",
    ("memory", "mem_processor_base_url"): "MEM_PROCESSOR_URL",
    ("memory", "mem_processor_api_key"): "MEM_PROCESSOR_KEY",
    ("triage", "provider"): "MSG_TRIAGE_PROVIDER",
    ("triage", "model"): "MSG_TRIAGE_MODEL",
    ("triage", "base_url"): "MSG_TRIAGE_URL",
    ("triage", "api_key"): "MSG_TRIAGE_KEY",
    ("susurro", "model"): "SUSURRO_MODEL",
    ("susurro", "base_url"): "SUSURRO_URL",
    ("susurro", "api_key"): "SUSURRO_KEY",
    ("susurro", "pulse_turns"): "SUSURRO_PULSE_TURNS",
    ("flags", "brain"): "BRAIN",
}


def _read() -> dict:
    with _lock:
        if _PATH.exists():
            try:
                data = json.loads(_PATH.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
    return {}


def _write(data: dict) -> None:
    with _lock:
        tmp = str(_PATH) + ".tmp"
        Path(tmp).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, _PATH)


def get(section: str) -> dict:
    """Config efectiva de una sección (defaults + store + fallback env). Incluye secretos → uso INTERNO."""
    base = dict(_DEFAULTS.get(section, {}))
    stored = _read().get(section, {}) or {}
    for k in base:
        if stored.get(k) not in (None, ""):
            base[k] = stored[k]
        elif (section, k) in _ENV_FALLBACK:
            env_val = os.getenv(_ENV_FALLBACK[(section, k)], "")
            if env_val:
                base[k] = env_val
    return base


def set(section: str, patch: dict) -> dict:
    """Aplica un patch a una sección (read-modify-write atómico). Solo claves declaradas en _DEFAULTS."""
    if section not in _DEFAULTS:
        raise KeyError(f"config/v2: sección desconocida {section!r}")
    allowed = set_keys(section)
    data = _read()
    cur = dict(data.get(section, {}) or {})
    for k, v in (patch or {}).items():
        if k in allowed:
            cur[k] = v
    data[section] = cur
    _write(data)
    return get(section)


def set_keys(section: str) -> frozenset:
    # literal, NO builtins.set() — el nombre `set` está sombreado por la función `set()` de arriba.
    return frozenset(_DEFAULTS.get(section, {}).keys())


def public(section: str) -> dict:
    """Vista REDACTADA para el frontend: los secretos NUNCA salen (→ `<key>_set: bool`)."""
    cfg = get(section)
    out = {}
    for k, val in cfg.items():
        if _is_secret(k):
            out[k + "_set"] = bool(val)
        else:
            out[k] = val
    return out


def public_all() -> dict:
    """Toda la config v2 para el frontend, redactada. NUNCA contiene una API key en claro."""
    return {s: public(s) for s in _DEFAULTS}


# ── accesos de conveniencia para el cerebro (modelo POR INVOCACIÓN) ─────────────────────────────────────
def fast_model_spec() -> dict:
    """Selección de modelo del FlashBrain para pasar POR INVOCACIÓN (no fija ninguna env global)."""
    return get("fast")


def code_agent_spec() -> dict:
    return get("code_agent")


def code_agent_model(kind: str = "generic") -> str:
    """Modelo del CodeAgent para un TIPO de tarea, para pasar POR INVOCACIÓN. Cae en cascada:
    `model_<kind>` → `model` (default global) → "" (default del proveedor). Nunca fija una env global."""
    cfg = get("code_agent")
    per_kind = (cfg.get(f"model_{kind}") or "").strip()
    return per_kind or (cfg.get("model") or "").strip()


def external_worker_env() -> dict:
    """Env vars para que un agente `claude` HEADLESS (brain worker o generador de widgets) use el endpoint
    Anthropic-compatible EXTERNO de §code_agent (p.ej. Z.AI GLM coding plan) en vez de la cuenta/licencia Claude
    del sistema — así los agentes headless NO consumen tokens de la licencia Claude Teams (regla del operador
    2026-07-31). Devuelve {} si `base_url` no está configurado (→ comportamiento normal). Fuente ÚNICA para TODOS
    los spawns de `claude` del repo, para que ninguno se quede fuera. El token se resuelve del credential store
    POR ENDPOINT (z.ai → `Z_AI_API_KEY`), NUNCA desde el JSON de config. Fail-open (cualquier fallo → {})."""
    try:
        cfg = get("code_agent")
        base = (cfg.get("base_url") or "").strip()
        if not base:
            return {}
        tok = (cfg.get("api_key") or "").strip()
        if not tok and "z.ai" in base.lower():
            tok = os.getenv("Z_AI_API_KEY", "")
        if not tok:
            # base_url CONFIGURADO pero sin token resoluble → si devolviéramos {} el agente headless caería a la
            # licencia Claude Teams EN SILENCIO (justo lo que el operador quiere evitar). Avisar FUERTE (fail-loud).
            try:
                from loguru import logger
                logger.warning(f"code_agent.base_url={base!r} configurado pero SIN token resoluble "
                               "(¿falta Z_AI_API_KEY en el store?) → los brain workers caerían a la licencia "
                               "Claude Teams. Revisa credenciales.")
            except Exception:
                pass
            return {}
        # ANTHROPIC_API_KEY conviviendo con base_url ambigua al CLI → se quita en el consumidor tras aplicar esto.
        return {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": tok}
    except Exception:
        return {}


def active_brain() -> str:
    """El cerebro seleccionado para este run. Fuente ÚNICA tras el entierro de Hermes (V2-009): antes vivía en
    `brains/__init__.py`. Env-first (`BRAIN`, lo que fija `make run` = nucleo) → store `flags.brain` → default
    `nucleo`. Se lee DESPUÉS de `config.settings.load_into_env()` para honrar overrides en caliente."""
    env = os.getenv("BRAIN")
    if env:
        return env.lower()
    return (get("flags").get("brain") or "nucleo").lower()
