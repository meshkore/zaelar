#
# selection.py — SELECCIÓN PROGRESIVA del catálogo de widgets (V2-085).
#
# EL PROBLEMA (medido 2026-08-01, con solo 16 widgets): `brief.for_prompt()` metía el catálogo ENTERO en el prompt
# de CADA turno (2.497 chars) y `GET /widgets` devolvía los 16 manifests COMPLETOS (25.639 chars). Los dos crecen
# O(N): con 1.000 widgets el prompt de un "¿qué hora es?" llevaría ~150 KB de catálogo irrelevante, y con 10.000 el
# turno sería inviable (coste, latencia y —peor— ruido de decisión para un modelo pequeño).
#
# LA REGLA: **lo que ve el modelo es O(K), no O(N).** Ampliar el catálogo NO debe engordar el turno de una petición
# que no va de widgets. Este módulo es el único sitio que decide QUÉ widgets entran en el prompt de un turno.
#
# CÓMO — capas de MENOS a MÁS, por PRIORIDAD (extiende la escalera de V2-078, no la sustituye):
#
#   1. `open`   — TODO lo que el operador tiene DELANTE. Nunca se recorta: es su pantalla, la fuente de verdad.
#   2. `named`  — lo que el operador NOMBRA en la frase de este turno, resuelto por `runtime.rank()` (nombre/alias,
#                 V2-082). **Esta es la capa que hace viables los miles de widgets**: un widget en la posición
#                 4.000 del catálogo se PROMOCIONA al prompt en cuanto el operador lo nombra. Sin ella, recortar el
#                 catálogo sería amnesia; con ella, es enfoque.
#   3. `recent` — el MRU (`state.recent_widgets`): lo que acaba de usar, aunque ya no esté abierto (V2-078).
#   4. `fill`   — relleno del resto del catálogo, en orden, SOLO hasta agotar el presupuesto. Es cortesía
#                 (descubribilidad: "¿qué sabes hacer?"), no un requisito de correción — de ahí que sea lo primero
#                 que se cae.
#
# LO QUE **NO** HACE (y es deliberado — invariante del operador, `feedback_no_hardcoded_understand`): NO clasifica
# la intención con tablas de verbos ni palabras clave. No decide si el turno "va de widgets"; solo RECUPERA los
# candidatos más plausibles y deja que el modelo (function-calling) decida. Recuperar ≠ comprender.
#
# ESCOTILLA DE SALIDA (por qué recortar es SEGURO): `show_widget` y `widget_data` resuelven su argumento
# server-side con `runtime.identify()` contra el catálogo COMPLETO (ver `providers/nucleo.py`). Si el operador
# nombra algo que no salió en el prompt, la capa 2 casi siempre lo habrá promocionado; y si no, el modelo puede
# pasar las palabras del operador tal cual y el servidor lo resuelve igual. Recortar el prompt NUNCA recorta lo
# que el sistema es capaz de abrir.
#
from __future__ import annotations

from . import runtime

# Presupuestos DUROS del turno. Son el contrato: pase lo que pase con el catálogo, esto es lo máximo que el
# operador paga en prompt por la capa de widgets.
# K = techo de filas en el prompt. Elegido para que HOY no cambie nada (el catálogo real son 16 widgets → entran
# todos, prompt idéntico al de antes: cero regresión para el operador) y a la vez la garantía O(K) quede escrita
# en código. El valor exacto importa poco; lo que importa es que EXISTA un techo — la corrección no depende de él
# sino de la capa `named`, que promociona lo que el operador nombra esté en la posición que esté.
MAX_WIDGETS = 20
MAX_RECENT = 4              # cuántos del MRU entran (el resto del MRU es ruido: ya no está en pantalla)
MAX_NAMED = 4               # cuántos candidatos por nombre/alias se promocionan (si hay más, es ambigüedad → pregunta)
MAX_OPEN = 10               # techo defensivo: un operador con 40 widgets abiertos no debe reventar el presupuesto

# Motivo por el que cada widget entró — se anota en la fila del prompt y se registra en las stats (observabilidad).
OPEN, NAMED, RECENT, FILL = "open", "named", "recent", "fill"


def _norm_ids(seq) -> list[str]:
    """ids en minúsculas, sin vacíos, sin duplicados y sin sufijo de instancia (`navegador::t1` → `navegador`)."""
    out, seen = [], set()
    for i in (seq or []):
        i = str(i or "").split("::", 1)[0].strip().lower()
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def candidates(query: str = "", open_ids=None, recent_ids=None, *,
               max_widgets: int = MAX_WIDGETS, stats: dict | None = None) -> list[dict]:
    """Los widgets que entran en el prompt de ESTE turno, ya ordenados por prioridad y acotados a `max_widgets`.

    Devuelve `[{"w": <manifest>, "reason": open|named|recent|fill}]`. El orden de salida ES el orden de prioridad
    (open → named → recent → fill), que es también la pista que lee el modelo para desempatar.

    `stats` (opcional, patrón `timings` del resto del núcleo): dict de salida con el desglose para observabilidad
    — n_total, n_selected, cuántos por capa, cuántos quedaron ocultos y si hubo truncado.

    Best-effort de principio a fin: un catálogo roto o un widget corrupto degradan el turno, nunca lo rompen."""
    try:
        cat = list(runtime.catalog())
    except Exception:
        cat = []
    by_id = {str(w.get("id") or "").strip().lower(): w for w in cat if w.get("id")}
    n_total = len(by_id)

    opened = _norm_ids(open_ids)
    recent = [r for r in _norm_ids(recent_ids) if r not in set(opened)]

    picked: list[dict] = []
    taken: set[str] = set()

    def _take(wid: str, reason: str) -> bool:
        w = by_id.get(wid)
        if w is None or wid in taken or len(picked) >= max_widgets:
            return False
        taken.add(wid)
        picked.append({"w": w, "reason": reason})
        return True

    # 1) ABIERTOS — lo que tiene delante. Primero y sin negociación (techo defensivo aparte).
    for wid in opened[:MAX_OPEN]:
        _take(wid, OPEN)

    # 2) NOMBRADOS en la frase del turno — la capa que sostiene los miles de widgets.
    n_ranked = 0
    if query:
        try:
            ranked = runtime.rank(query, limit=MAX_NAMED)
        except Exception:
            ranked = []
        n_ranked = len(ranked)
        for _score, w in ranked:
            _take(str(w.get("id") or "").strip().lower(), NAMED)

    # 3) USADOS HACE POCO (MRU) — continuidad entre turnos aunque ya se cerrara.
    for wid in recent[:MAX_RECENT]:
        _take(wid, RECENT)

    # 4) RELLENO — descubribilidad, y solo si sobra presupuesto. Lo primero en caerse al crecer el catálogo.
    for wid in by_id:
        if len(picked) >= max_widgets:
            break
        _take(wid, FILL)

    if stats is not None:
        counts = {r: 0 for r in (OPEN, NAMED, RECENT, FILL)}
        for p in picked:
            counts[p["reason"]] += 1
        stats.update({
            "n_total": n_total,
            "n_selected": len(picked),
            "n_open": counts[OPEN],
            "n_named": counts[NAMED],
            "n_recent": counts[RECENT],
            "n_fill": counts[FILL],
            "n_ranked": n_ranked,                       # cuántos casó el nombre/alias (antes del techo MAX_NAMED)
            "hidden": max(0, n_total - len(picked)),
            "truncated": len(picked) < n_total,
            "selected_ids": [str(p["w"].get("id") or "") for p in picked],
        })
    return picked
