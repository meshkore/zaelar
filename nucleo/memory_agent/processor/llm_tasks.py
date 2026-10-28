"""The memory's own off-hot-path LLM tasks: REM synthesis, its independent grounding check, and paraphrases.

All three run from REM sleep (`memory/rem.py` receives them INJECTED by the loop — memory does not import nucleo).
"""
from __future__ import annotations

import json

from loguru import logger

from nucleo.memory_agent.processor import llm

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



def _default_lang() -> str:
    """`langs.current_code()` already reads ZAELAR_LANGUAGE and falls back to DEFAULT_LANG ("en")."""
    try:
        from voice.engine.core import langs
        return langs.current_code()
    except Exception:
        return "en"


def _canonical_lang_native() -> str:
    """Native name of the memory's CANONICAL language — memory is MONOLINGUAL, in the operator's `state.language`.
    The fallback is the engine's own default, never a hardcoded language (that would win on a cold first run)."""
    code = _default_lang()
    try:
        from memory import api as _memory
        code = (_memory.state().get("language") or code)
    except Exception:
        pass
    try:
        from voice.engine.core import langs
        return langs.spec(code).native
    except Exception:
        return "castellano"


def _json_array(content: str):
    start, end = content.find("["), content.rfind("]")
    return json.loads(content[start:end + 1])


def synthesize_concept_groups(groups: list[dict], *, model_override: str | None = None,
                              url_override: str | None = None) -> list[dict]:
    """Synthesis hook for `memory/rem.py` (SYNCHRONOUS — REM runs in to_thread). `groups` =
    [{"concept": str, "pills": [str, …]}, …] → [{"concept": str, "insight": str|None}, …]. Fail-open: []."""
    if not groups:
        return []
    user = json.dumps(
        [{"concept": g["concept"], "recuerdos": g["pills"][:12]} for g in groups],
        ensure_ascii=False, indent=1,
    )
    # `.replace`, NOT `.format`: the prompt ends with a literal JSON example whose braces `format` reads as fields
    # (KeyError on EVERY call, swallowed by REM). Pinned by tests/memory/unit/test_rem_prompt.py.
    system = _REM_SYSTEM.replace("{lang}", _canonical_lang_native())
    # Generous budget and timeout: REM runs once a night and nobody waits; with 1200 tokens 1 call in 3 came back
    # truncated → «no insights» with no error. Emitted tokens are what is paid, not the ceiling.
    content = llm.chat_sync("rem", system, user, max_tokens=4000, timeout=240.0,
                            model_override=model_override, url_override=url_override)
    if not content:
        return []
    try:
        out = []
        for it in _json_array(content):
            if isinstance(it, dict) and it.get("concept"):
                ins = it.get("insight")
                out.append({"concept": str(it["concept"]),
                            "insight": (str(ins).strip() or None) if ins else None})
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[rem]: respuesta no parseable: {str(e)[:120]}")
        return []


# V2-104: a second fidelity opinion, in a FRESH call independent of the one that generated the insight.
_GROUNDING_SYSTEM = (
    "Verificas la fidelidad de un INSIGHT de memoria contra los DATOS que lo originaron. Responde SOLO la "
    "palabra true si CADA afirmación del insight está respaldada directamente por los datos (sin inventar "
    "nombres, cifras, fechas, ni generalizar más de lo que los datos permiten). Responde SOLO la palabra false "
    "si el insight añade CUALQUIER cosa que no esté en los datos. Nada más en tu respuesta."
)


def verify_insight_grounded(insight: str, pills: list[str], *, model_override: str | None = None,
                            url_override: str | None = None) -> bool:
    """Optional REM hook. Fail-CLOSED, unlike the other tasks: losing a legitimate insight is cheaper than letting
    an invented one through, now that `writer.demote_summarized` displaces the facts it summarises (V2-103)."""
    if not insight or not pills:
        return False
    user = json.dumps({"insight": insight, "datos": pills[:12]}, ensure_ascii=False, indent=1)
    content = llm.chat_sync("rem", _GROUNDING_SYSTEM, user, max_tokens=200, timeout=60.0,
                            model_override=model_override, url_override=url_override)
    if not content:
        return False
    return content.strip().lower().startswith("true")


# V2-031 T2: reformulations for the paraphrase index (off the hot path, from REM).
_PARAPHRASE_SYSTEM = (
    "Reformulas una frase de memoria de un asistente personal para dar VOCABULARIO ALTERNATIVO — sinónimos, "
    "categoría/hiperónimo, forma de referirse al mismo hecho con OTRAS palabras — para que una pregunta con "
    "vocabulario distinto SIGA encontrando el mismo dato (vocab-gap). NO sirve reordenar o cambiar levemente "
    "la misma frase: 'toca la guitarra los sábados' → 'los sábados toca la guitarra' NO VALE, no aporta "
    "vocabulario nuevo. SÍ vale: 'toca la guitarra los sábados' → 'es músico, toca un instrumento de cuerda'. "
    "MANTIENES el significado exacto — ni añades ni quitas información, ni cifras, ni nombres — pero CAMBIAS "
    "las palabras de contenido por su categoría o un sinónimo real. Responde SOLO un array JSON de 1 a 2 "
    "strings, sin explicación: [\"reformulación 1\", \"reformulación 2\"]"
)


def generate_paraphrases(text: str, *, model_override: str | None = None,
                         url_override: str | None = None) -> list[str]:
    """1-2 reformulations of `text` for `writer.index_paraphrases()`. Fail-open: [] — without them the pill is still
    retrieved through its own embedding; this only ADDS retrieval surface."""
    text = (text or "").strip()
    if not text:
        return []
    content = llm.chat_sync("paraphrase", _PARAPHRASE_SYSTEM, text, max_tokens=300, timeout=60.0,
                            model_override=model_override, url_override=url_override)
    if not content:
        return []
    try:
        return [str(s).strip() for s in _json_array(content) if isinstance(s, str) and str(s).strip()][:2]
    except Exception as e:  # noqa: BLE001
        logger.warning(f"memllm[paraphrase]: respuesta no parseable: {str(e)[:120]}")
        return []
