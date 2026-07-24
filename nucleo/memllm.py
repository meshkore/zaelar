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

_DEFAULTS = {
    "rem": ("https://api.openai.com/v1", "gpt-4.1-mini"),
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
        return data["choices"][0]["message"]["content"]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[{task}]: {model} @ {url} falló: {str(e)[:160]} → fail-open")
        return None


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
    system = _REM_SYSTEM.format(lang=_canonical_lang_native())
    content = chat_sync("rem", system, user, max_tokens=1200,
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
