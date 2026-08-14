"""nucleo/flash/turn_perf.py — VEREDICTO de latencia de un turno del FlashBrain (2026-08-02).

La instrumentación ya existía y era rica (`llm_metrics` + `timings`: TTFT, tokens de entrada/salida, tok/s, tamaño
por bloque del prompt, cold-start, contención). El problema era que vivía ENTERRADA en el `extra` del evento de
respuesta: para saber por qué un turno tardó 8 s había que exportar el jsonl y cruzar campos a mano.

Esto no mide nada nuevo — LEE lo que ya se mide y responde en una línea la única pregunta que importa en vivo:

    ¿este turno fue lento ANTES del primer token, por el PROMPT, por el PROVEEDOR, o por arranque en frío?

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

# ── TTFT: el sospechoso que este veredicto no sabía nombrar (2026-08-14) ──────────────────────────────────────
# El orden de las ramas era frío → prompt → proveedor, y `prompt` gana con `ptok >= 6000`. Como el prompt de VOZ
# es SIEMPRE de 9-10k tokens, **la rama `proveedor` era inalcanzable en el camino de voz, por construcción**: los
# 10 turnos lentos de la sesión b70a45d0 se etiquetaron «PROMPT GRANDE» con un prompt constante (9.363-10.314 tok,
# ±9%) y un TTFT que iba de 0 a 25.703 ms. Un input plano no puede explicar un factor 10; lo explicaba la
# DIFICULTAD de la decisión (los dos picos de 25,6 s son los dos turnos más duros de la sesión), que es la firma
# del razonamiento oculto de V4 Flash ya medido el 2026-08-02 («razona aunque se le pida que no»).
#
# Así que el veredicto deja de decidir por el TAMAÑO del prompt y pasa a mirar DÓNDE se fue el tiempo:
#   · casi todo antes del primer token (TTFT/total alto) → el modelo estaba PENSANDO o el proveedor encolando;
#   · repartido, con throughput bajo → el proveedor genera lento;
#   · repartido, con throughput normal → el prompt/el trabajo.
# El tamaño del prompt sigue nombrándose, pero como DATO, no como culpable: está medido que vale ~150 ms.
TTFT_DOMINATES = 0.70      # fracción del turno gastada antes del primer token para culpar al pre-token
TTFT_SLOW_MS = 4000        # …y a partir de aquí en absoluto (por debajo, un turno de 3 s no es un problema)

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

    `cause` ∈ frio · pre_token · proveedor · trabajo · prompt · reparto · ok — y el `label` es la línea que se
    lee en el visor. El orden de las ramas ES la decisión de diseño: ver la nota de `TTFT_DOMINATES`.
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

    # ¿Cuánto del turno se fue ANTES del primer token? Es la pregunta que separa «piensa mucho» de «escribe
    # despacio», y la que faltaba. Sin ttft medido no se puede afirmar nada → 0.0 (no culpa a nadie).
    ttft_frac = (ttft / total) if (ttft and total) else 0.0
    ttft_bound = ttft >= TTFT_SLOW_MS and ttft_frac >= TTFT_DOMINATES

    if not slow:
        cause = "ok"
        label = f"⏱ turno {int(total)} ms · prompt {int(ptok)} tok · TTFT {int(ttft)} ms"
    elif cold:
        cause = "frio"
        label = (f"⏱ turno LENTO {int(total)} ms — ARRANQUE EN FRÍO "
                 f"({int(gap)} s sin hablar; la 1ª llamada paga handshake)")
    elif ttft_bound:
        # ANTES DEL PRIMER TOKEN se fue casi todo. En este cerebro eso es razonamiento oculto (V4 Flash razona
        # aunque se le pida que no: medido el 2026-08-02, `thinking:disabled` lo reduce a la mitad y no lo apaga)
        # o cola del proveedor. Se nombran las DOS y se da el dato que las distingue, en vez de culpar al prompt.
        cause = "pre_token"
        label = (f"⏱ turno LENTO {int(total)} ms — TODO ANTES DEL 1er TOKEN: TTFT {int(ttft)} ms "
                 f"({int(ttft_frac * 100)}% del turno) con {tps if tps is not None else '?'} tok/s después. "
                 f"Razonamiento oculto o cola del proveedor — el prompt ({int(ptok)} tok) no lo explica")
    elif tps is not None and tps < SLOW_TOKS_PER_S:
        cause = "proveedor"
        label = (f"⏱ turno LENTO {int(total)} ms — PROVEEDOR LENTO: {tps} tok/s con un prompt normal "
                 f"({int(ptok)} tok) · TTFT {int(ttft)} ms")
    elif worked:
        cause = "trabajo"
        label = (f"⏱ turno {int(total)} ms — con TRABAJO en el turno "
                 f"({'escalada' if m.get('escalated') else 'búsqueda'}, 2º pase): normal que suba")
    elif ptok >= BIG_PROMPT_TOKENS and ttft_frac < TTFT_DOMINATES:
        # El prompt solo se culpa cuando el tiempo se repartió DE VERDAD. Si se fue casi todo antes del primer
        # token, el culpable es el pre-token aunque el prompt sea grande — es exactamente el sesgo que hacía que
        # `proveedor` no pudiera salir nunca en voz.
        cause = "prompt"
        label = (f"⏱ turno LENTO {int(total)} ms — PROMPT GRANDE: {int(ptok)} tok"
                 + (f", lo que más pesa es «{block}» ({block_n} chars)" if block else "")
                 + f" · TTFT {int(ttft)} ms ({int(ttft_frac * 100)}%)")
    else:
        # Lento y sin causa dominante. Antes esto se resolvía culpando al prompt o al proveedor por descarte; decir
        # «no lo sé, aquí están los números» es más útil que un culpable inventado.
        cause = "reparto"
        label = (f"⏱ turno LENTO {int(total)} ms — sin causa dominante: TTFT {int(ttft)} ms "
                 f"({int(ttft_frac * 100)}%) · {tps if tps is not None else '?'} tok/s · prompt {int(ptok)} tok")

    return {"slow": slow, "cause": cause, "label": label, "total_ms": int(total), "ttft_ms": int(ttft),
            "gen_ms": int(gen), "prompt_tokens": int(ptok), "tok_per_s": tps, "gap_since_last_s": round(gap, 1),
            "cold": cold, "top_block": block, "top_block_chars": block_n,
            # `ttft_frac` viaja en el evento: es la serie que gobierna el circuito de latencia del failover
            # (`provider_chain.note_slow`) y la que permite ver la VARIANZA del TTFT a prompt constante.
            "ttft_frac": round(ttft_frac, 3),
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
