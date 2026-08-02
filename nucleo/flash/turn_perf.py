"""nucleo/flash/turn_perf.py — VEREDICTO de latencia de un turno del FlashBrain (2026-08-02).

La instrumentación ya existía y era rica (`llm_metrics` + `timings`: TTFT, tokens de entrada/salida, tok/s, tamaño
por bloque del prompt, cold-start, contención). El problema era que vivía ENTERRADA en el `extra` del evento de
respuesta: para saber por qué un turno tardó 8 s había que exportar el jsonl y cruzar campos a mano.

Esto no mide nada nuevo — LEE lo que ya se mide y responde en una línea la única pregunta que importa en vivo:

    ¿este turno fue lento por el PROMPT, por el PROVEEDOR, o por arranque en frío?

Premisa del operador (2026-08-02): «DeepSeek Flash es bastante rápido; si un turno pasa de 1-2 s es porque le
estamos lanzando un prompt demasiado extenso o porque el proveedor ha tenido un fallo puntual». El veredicto
distingue exactamente esos dos casos y NOMBRA al culpable concreto (qué bloque infla el prompt), para que no haya
que adivinar. Determinista, sin LLM, fail-open: si falta un dato, degrada a "sin datos" y nunca rompe el turno.
"""
from __future__ import annotations

# Umbrales. `SLOW_MS` = a partir de aquí el turno se marca y se explica; sale del listón del operador (1-2 s es
# lo normal), con margen para no marcar cada turno con tools.
SLOW_MS = 2500
# Un prompt por encima de esto ya explica por sí solo un turno lento en un modelo rápido.
BIG_PROMPT_TOKENS = 6000
# Throughput por debajo de esto con un prompt normal = el proveedor va mal, no nosotros.
SLOW_TOKS_PER_S = 8.0
# Silencio largo antes del turno → la primera llamada paga handshake/arranque del modelo.
COLD_GAP_S = 90.0

# Bloques que componen el prompt, en el orden en que se nombran al operador. `sz_*` son chars ya medidos por el
# constructor del prompt; `tools_chars` lo aporta el catálogo de tools ofrecido en ESTE turno.
_BLOCKS = (
    ("tools_chars", "catálogo de tools"),
    ("sz_resources", "capa de recursos"),
    ("sz_widgets", "catálogo de widgets"),
    ("sz_memory", "estado/memoria"),
    ("sz_recall", "recall largo"),
    ("sz_recent", "conversación reciente"),
    ("sz_live", "estado vivo"),
)


def _num(d: dict, *keys, default=None):
    for k in keys:
        v = d.get(k)
        if isinstance(v, (int, float)):
            return v
    return default


def biggest_block(m: dict) -> tuple[str, int]:
    """El bloque que más infla el prompt de este turno (nombre legible, chars). ('', 0) si no hay datos."""
    best, best_n = "", 0
    for key, label in _BLOCKS:
        n = _num(m, key, default=0) or 0
        if n > best_n:
            best, best_n = label, int(n)
    return best, best_n


def verdict(m: dict) -> dict:
    """Diagnóstico del turno a partir de las métricas YA recogidas. Devuelve `{slow, cause, label, …}`.

    `cause` ∈ frio · prompt · proveedor · trabajo · ok — y el `label` es la línea que se lee en el visor.
    """
    total = _num(m, "total_ms", "fast_ms", default=0) or 0
    ttft = _num(m, "ttft_ms", default=0) or 0
    gen = _num(m, "gen_ms", "llm_total_ms", default=0) or 0
    ptok = _num(m, "prompt_tokens", "prompt_tokens_est", default=0) or 0
    tps = _num(m, "tok_per_s")
    gap = _num(m, "gap_since_last_s", default=0) or 0
    cold = bool(m.get("cold_estimate")) or gap >= COLD_GAP_S
    # un turno que ESCALA o BUSCA hace un 2º pase: es lento por TRABAJO, no por avería.
    worked = bool(m.get("escalated") or m.get("searched"))

    block, block_n = biggest_block(m)
    slow = total >= SLOW_MS

    if not slow:
        cause = "ok"
        label = f"⏱ turno {int(total)} ms · prompt {int(ptok)} tok"
    elif cold:
        cause = "frio"
        label = (f"⏱ turno LENTO {int(total)} ms — ARRANQUE EN FRÍO "
                 f"({int(gap)} s sin hablar; la 1ª llamada paga handshake)")
    elif ptok >= BIG_PROMPT_TOKENS:
        cause = "prompt"
        label = (f"⏱ turno LENTO {int(total)} ms — PROMPT GRANDE: {int(ptok)} tok"
                 + (f", lo que más pesa es «{block}» ({block_n} chars)" if block else ""))
    elif tps is not None and tps < SLOW_TOKS_PER_S:
        cause = "proveedor"
        label = (f"⏱ turno LENTO {int(total)} ms — PROVEEDOR LENTO: {tps} tok/s con un prompt normal "
                 f"({int(ptok)} tok) · TTFT {int(ttft)} ms")
    elif worked:
        cause = "trabajo"
        label = (f"⏱ turno {int(total)} ms — con TRABAJO en el turno "
                 f"({'escalada' if m.get('escalated') else 'búsqueda'}, 2º pase): normal que suba")
    else:
        cause = "proveedor"
        label = (f"⏱ turno LENTO {int(total)} ms — ni prompt grande ({int(ptok)} tok) ni frío: "
                 f"apunta a un fallo puntual del proveedor · TTFT {int(ttft)} ms")

    return {"slow": slow, "cause": cause, "label": label, "total_ms": int(total), "ttft_ms": int(ttft),
            "gen_ms": int(gen), "prompt_tokens": int(ptok), "tok_per_s": tps, "gap_since_last_s": round(gap, 1),
            "cold": cold, "top_block": block, "top_block_chars": block_n,
            "model": m.get("model") or "", "engine": m.get("engine") or m.get("provider") or ""}


def emit_verdict(metrics: dict) -> dict:
    """Publica el veredicto en el bus de observabilidad (`kind="perf"`) y lo devuelve. Fail-open."""
    v = verdict(metrics or {})
    try:
        from voice.observer import emit
        emit("perf", v["label"], role="system", extra=v)
    except Exception:
        pass
    return v
