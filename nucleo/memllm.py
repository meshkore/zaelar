"""nucleo/memllm.py — ROUTER interno de modelos del MÓDULO DE MEMORIA (V2-056, 2026-07-20).

El módulo de memoria tiene varias tareas de LLM con perfiles distintos, cada una elegible POR CONFIG y con la
credencial resuelta POR ENDPOINT (lección de la auditoría 2026-07-19: una key suelta de env enviada al endpoint
equivocado tumbó el CORAZÓN 2 días en silencio). Una sola costura para todas:

  - `distill`  → el CORAZÓN de escritura (lo implementa `nucleo/mem_processor.py` con su cola/semántica propia;
                 este router NO lo reemplaza — queda aquí documentado como tarea del catálogo).
  - `rem`      → la SÍNTESIS del sueño profundo (`memory/rem.py` la recibe INYECTADA — la memoria no importa
                 nucleo; el loop cablea `synthesize_concept_groups` como hook, patrón `summarize_fn`).
  - (futuras)  → `context_router` (repesca del dossier), jueces de calidad de píldora…

Todo va OFF-hot-path (jamás en el turno de voz). Cada tarea lee `config §memory.<task>_model/_base_url/_api_key`
con fallback a defaults; la key vacía se resuelve por endpoint (OpenAI/AIMLAPI/xAI/Groq → env correspondiente).
Benchmarks que sustentan los defaults: `zaelar-model-benchmarks.md §12` (write-completeness + síntesis REM).
"""
from __future__ import annotations

import json
import os
import urllib.request

from loguru import logger

# Fallback de última instancia (si `config §memory` no se puede leer). Debe coincidir con el default de
# `config/v2.py §memory` — apuntar a OpenAI aquí significaba, en la nube, fallar siempre: no hay OPENAI_API_KEY
# entre los secretos que inyecta el provisioner (2026-08-09, misma corrección que en mem_processor).
_DEFAULTS = {
    "rem": ("https://api.aimlapi.com/v1", "deepseek/deepseek-v4-flash"),
    # i18n (V2-089): traducción del UI a un idioma nuevo en la INICIALIZACIÓN (i18n/init). Off-hot-path, calidad
    # importa (scripts no-latinos: árabe, chino, japonés…) → modelo fuerte. Override en config §memory.
    #
    # 2026-08-09 — apuntaba a OpenAI DIRECTO (gpt-4o) y era el último resto de esa cuenta en la memoria: en la
    # nube no hay OPENAI_API_KEY, así que generar el bundle de un idioma nuevo habría fallado en silencio (mismo
    # patrón que tumbó el CORAZÓN en julio y el REM hasta ayer). Norma del operador: TODO por el broker AIMLAPI,
    # una sola cuenta que gestionar. Sonda al tamaño REAL del lote (`_BATCH=50`, ja/ar/zh, 15 claves con
    # placeholder) antes de elegir sustituto:
    #   · anthropic/claude-haiku-4.5 → 100% cobertura y 15/15 placeholders en TODOS los idiomas, ~7-10s. ELEGIDO.
    #   · google/gemini-2.5-flash    → correcto casi siempre, pero una pasada de árabe devolvió 0/50 (respuesta
    #                                  cortada a 160 tokens). Un lote perdido = 50 strings en inglés en la UI.
    #   · deepseek/deepseek-v4-flash → acierta, pero RAZONA: 6.700-8.500 tokens de salida para ~1.200 de
    #                                  contenido, 50-60s por lote. Es el mismo perfil que truncaba el REM; aquí
    #                                  no compensa porque la tarea se paga UNA vez por idioma (514 claves = 11
    #                                  lotes ≈ $0,08 con haiku) y la fiabilidad vale más que el precio.
    "i18n": ("https://api.aimlapi.com/v1", "anthropic/claude-haiku-4.5"),
}


def resolve(task: str) -> tuple[str, str, str]:
    """(url, model, key) para una tarea del catálogo. Config manda; key vacía → por endpoint."""
    base_url, model = _DEFAULTS.get(task, _DEFAULTS["rem"])
    key = ""
    try:
        from config import v2 as _v2
        mem = _v2.get("memory") or {}
        base_url = (mem.get(f"{task}_base_url") or "").strip() or base_url
        model = (mem.get(f"{task}_model") or "").strip() or model
        key = (mem.get(f"{task}_api_key") or "").strip()
    except Exception:
        pass
    return base_url, model, key or _endpoint_key(base_url)


def _endpoint_key(url: str) -> str:
    low = (url or "").lower()
    if "openai.com" in low:
        return os.getenv("OPENAI_API_KEY", "") or "local"
    if "aimlapi" in low:
        return os.getenv("AIMLAPI_KEY", "") or "local"
    if "x.ai" in low:
        return os.getenv("XAI_API_KEY", "") or "local"
    if "groq.com" in low:
        return os.getenv("GROQ_API_KEY", "") or "local"
    return "local"


def chat_sync(task: str, system: str, user: str, *, max_tokens: int = 900,
              temperature: float = 0.2, timeout: float = 60.0,
              model_override: str | None = None, url_override: str | None = None) -> str | None:
    """Chat SÍNCRONO (urllib, sin deps) — pensado para correr DENTRO de un `asyncio.to_thread` (el sueño REM) o
    en scripts/benches. Devuelve el content, o None si el modelo no está/falla (el llamador hace fail-open)."""
    url, model, key = resolve(task)
    if url_override:
        url = url_override
        key = _endpoint_key(url)
    if model_override:
        model = model_override
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 # AIMLAPI va tras Cloudflare y 403ea al UA por defecto de urllib → UA de navegador
                 # (mismo workaround que fast_client)
                 "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                               "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        _record_usage(data.get("usage"), url, model)
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[{task}]: {model} @ {url} falló: {str(e)[:160]} → fail-open")
        return None


# ── CONSUMO REAL (2026-08-09) — mismo cierre que en `mem_processor`: las tareas de LLM de la memoria son
# llamadas de nube como cualquier otra y no reportaban a Energy, así que en una cuenta cloud el sueño REM (y la
# generación de bundles i18n) consumían tokens gratis en el contador. `last_usage()` además da los tokens REALES
# al bench de síntesis (§12.4) para calcular el coste por sueño con números medidos. Fail-open siempre: medir
# NUNCA puede tumbar una consolidación.
_last_usage: dict = {}


def last_usage() -> dict:
    """Tokens de la última llamada (`{prompt_tokens, completion_tokens, total_tokens}`), `{}` si el proveedor no
    los devolvió. Solo diagnóstico/bench."""
    return dict(_last_usage)


def _record_usage(usage: dict | None, base_url: str, model: str) -> None:
    global _last_usage
    if not isinstance(usage, dict):
        _last_usage = {}
        return
    _last_usage = {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    try:
        from nucleo import energy_meter as _energy
        _energy.report_llm_usage(base_url=base_url, model=model,
                                 prompt_tokens=_last_usage.get("prompt_tokens"),
                                 completion_tokens=_last_usage.get("completion_tokens"))
    except Exception:  # noqa: BLE001
        pass


# ── SÍNTESIS del sueño REM (el hook que el loop inyecta en memory/rem.py) ─────────────────────────────────────
_REM_SYSTEM = (
    "Eres el consolidador de memoria de un asistente personal. Recibes GRUPOS de recuerdos del operador "
    "agrupados por concepto. Para cada grupo, destila 1 INSIGHT: una síntesis de ALTO NIVEL que un buen "
    "asistente sacaría de esos datos (patrón, gusto, situación, hábito) — no un resumen que repita la lista. "
    "Reglas DURAS: (1) SIEMPRE en {lang} (la memoria es MONOLINGÜE, en el idioma canónico del operador — "
    "traduce si los datos vienen en otro idioma); (2) 1-2 frases por insight, en 3ª persona; "
    "(3) CONSERVA nombres propios, cifras y fechas de los datos — nunca los generalices; (4) NO inventes nada "
    "que no esté en los datos; (5) si un grupo no da para un insight con sustancia, devuélvelo con insight null. "
    "Responde SOLO un array JSON: [{\"concept\": str, \"insight\": str|null}, …]"
)


def _canonical_lang_native() -> str:
    """Nombre nativo del idioma CANÓNICO de la memoria (decisión 2026-07-10: la memoria es MONOLINGÜE, en el
    idioma del operador — mismo campo `state.language` que lee `nucleo/mem_processor.py::_render` para el
    CORAZÓN de escritura). Fail-open a español si la memoria o el catálogo de idiomas no están disponibles."""
    code = "es"
    try:
        from memory import api as _memory
        code = (_memory.state().get("language") or "es")
    except Exception:
        pass
    try:
        from voice.engine.core import langs
        return langs.spec(code).native
    except Exception:
        return "castellano"


def synthesize_concept_groups(groups: list[dict], *, model_override: str | None = None,
                              url_override: str | None = None) -> list[dict]:
    """Hook de síntesis para `memory/rem.py` (SÍNCRONO — REM corre en to_thread). `groups` =
    [{"concept": str, "pills": [str, …]}, …] → [{"concept": str, "insight": str|None}, …]. Fail-open: []."""
    if not groups:
        return []
    user = json.dumps(
        [{"concept": g["concept"], "recuerdos": g["pills"][:12]} for g in groups],
        ensure_ascii=False, indent=1,
    )
    # `.replace`, NO `.format` (fix 2026-08-09): el prompt TERMINA con un ejemplo de JSON literal
    # —[{"concept": str, "insight": str|null}]— y `str.format` interpreta esas llaves como marcadores →
    # `KeyError: '"concept"'` en CADA llamada. `rem.synthesize` captura la excepción y devuelve 0 con un
    # `logger.warning`, así que la fase de INSIGHTS del sueño profundo llevaba rota EN SILENCIO desde que se
    # añadió la interpolación `{lang}` de la regla monolingüe (los números de §12.2 son anteriores a ese
    # cambio). Mismo idioma que `mem_processor`, que ya usaba `.replace` para su catálogo de slots.
    # Cubierto por tests/memory/unit/test_rem_prompt.py para que no pueda repetirse.
    system = _REM_SYSTEM.replace("{lang}", _canonical_lang_native())
    # TIMEOUT GENEROSO (2026-08-09): el sueño REM corre UNA vez al día, de madrugada, en `to_thread` — no hay
    # nadie esperando. El default de 60s se quedaba corto: el modelo titular emite ~2.200 tokens de salida para
    # los 8 grupos, y en una tanda lenta del broker se pasa de 60s → la noche entera sin consolidar por prisa
    # que nadie tenía. Escribir puede ser LENTO (invariante V2-013); leer es lo que no puede.
    # `max_tokens` HOLGADO y timeout GENEROSO (2026-08-09). El sueño REM corre UNA vez al día, de madrugada, en
    # `to_thread`: no hay nadie esperando, y escribir puede ser LENTO (invariante V2-013) — leer es lo que no.
    #   · max_tokens 1200 → 4000: con 8 grupos, un modelo verboso o que RAZONA (deepseek-v4-flash piensa aunque
    #     se le pida que no) agota el presupuesto ANTES de cerrar el array → JSON truncado → `_parse` devuelve []
    #     → "sin insights" SIN error. Medido: con 1200 fallaba 1 de cada 3 llamadas (una topó exactamente en
    #     1200); con 4000, 3/3 válidas emitiendo solo ~1.100 tokens. El techo alto NO cuesta: se paga lo emitido.
    #   · timeout 60 → 240s: una tanda lenta del broker se comía la noche entera de consolidación por una prisa
    #     que nadie tenía.
    content = chat_sync("rem", system, user, max_tokens=4000, timeout=240.0,
                        model_override=model_override, url_override=url_override)
    if not content:
        return []
    try:
        start, end = content.find("["), content.rfind("]")
        arr = json.loads(content[start:end + 1])
        out = []
        for it in arr:
            if isinstance(it, dict) and it.get("concept"):
                ins = it.get("insight")
                out.append({"concept": str(it["concept"]),
                            "insight": (str(ins).strip() or None) if ins else None})
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[rem]: respuesta no parseable: {str(e)[:120]}")
        return []
