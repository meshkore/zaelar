"""Read-side composition: the worker dossier (`compose_context`), agenda and state lines.

Split out VERBATIM (audit 2026-08-23). Presentation over `memory.api` — writes nothing.
"""
from __future__ import annotations

import asyncio
import re

from loguru import logger

from memory.concepts import derive_concepts as _derive_concepts  # noqa: F401


_WEAK_SCORE = 0.35


def _state_lines(st: dict) -> list[str]:
    """Compone el bloque ESTADO del prompt a partir del state (todos los campos con valor).

    Antes solo pintaba 5 campos fijos (name/treatment/location/recent/topics). Ahora pinta también CUALQUIER
    otro campo custom con valor (p. ej. `hardware`, `car`, `language≠es`), así el prompt ve lo mismo que el
    visor y no hay campos "invisibles"."""
    lines: list[str] = []
    op = (st.get("operator_name") or "").strip()
    if op:
        lines.append(f"Operador: {op}.")
    if st.get("treatment"):
        lines.append(f"Trato: {st['treatment']}.")
    if st.get("location"):
        lines.append(f"Ubicación: {st['location']}.")
    # Campos custom (hardware, car, empresa, etc.): cualquier clave con valor escalar no en la lista canónica.
    # `mission` fuera: es el prompt del ASISTENTE (identidad de zaelar), no perfil del operador — en el dossier
    # de un worker era ruido de 900 chars (V2-056). `rules` lo pinta compose_context aparte (lista, no escalar).
    _canonical = {"assistant_name", "operator_name", "language", "treatment", "location", "recent", "topics",
                  "mission", "rules", "open_widgets", "activity", "sessions", "rails"}
    for k, v in st.items():
        if k in _canonical:
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            lines.append(f"{k.capitalize().replace('_', ' ')}: {v}.")
    recent = [str(r).strip() for r in (st.get("recent") or []) if str(r).strip()][:5]
    if recent:
        lines.append("Recientes: " + "; ".join(r[:80] for r in recent) + ".")
    topics = [str(t).strip() for t in (st.get("topics") or []) if str(t).strip()][:6]
    if topics:
        lines.append("Temas: " + ", ".join(t[:40] for t in topics) + ".")
    return lines


def _is_ambiguous(prompt: str, res: dict) -> bool:
    """¿Merece el recall una segunda pasada con router LLM? Sí si la query es muy corta o los resultados son
    pocos/flojos. Barato, sin red."""
    mems = res.get("memories") or []
    if not mems:
        return True
    if len((prompt or "").split()) <= 2:
        return True
    top = max((m.get("score", 0.0) for m in mems), default=0.0)
    return top < _WEAK_SCORE


async def _llm_expand_query(prompt: str) -> str:
    """Router LLM BARATO: pide al modelo rápido 3-6 palabras clave para AMPLIAR la búsqueda en memoria. Modelo
    POR INVOCACIÓN (spec de `config/v2`). Best-effort: sin modelo/credencial o ante cualquier fallo → ''."""
    try:
        from nucleo.flash.fast_client import FastClient, spec_from_config
        spec = spec_from_config()
        if not spec.resolved_api_key():        # sin credencial utilizable → nos quedamos con la heurística
            return ""
        msgs = [
            {"role": "system", "content": "Eres un ampliador de consultas para una búsqueda en memoria. "
             "Devuelve SOLO 3-6 palabras clave (sustantivos/temas) separadas por espacios, sin explicar, "
             "en el idioma del texto."},
            {"role": "user", "content": (prompt or "")[:400]},
        ]
        out = []
        async for chunk in FastClient().stream(msgs, spec=spec, max_tokens=40):
            out.append(chunk)
        return "".join(out).strip().replace("\n", " ")[:120]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"memory_agent: router LLM no disponible ({e}); sigo con heurística")
        return ""




def _agenda_lines(limit: int = 6) -> list[str]:
    """Citas próximas del widget agenda (read-only, best-effort) — un dossier de tarea sin las fechas del
    operador planifica a ciegas (auditoría 2026-07-19 P1-2: la agenda vivía FUERA de la composición)."""
    try:
        import datetime as _dt

        from memory.api import now as _now
        from widgets import store as _wstore
        data = _wstore.load("agenda") or {}
        items = data.get("events") or data.get("items") or data.get("meetings") or []
        # The memory's clock, NOT the wall clock. Same rule the distiller's temporal anchor states
        # (`mem_processor._now_line`): the timeline corpus replays 270 simulated days under `clock.travel()`,
        # and `date.today()` answers with the real today throughout. Measured 2026-08-21 — replaying at
        # 2026-03-10 with an appointment six simulated days ahead, this returned NOTHING: every upcoming date
        # reads as past, so the dossier plans blind, which is the exact failure this function was added to
        # prevent (audit 2026-07-19 P1-2). It fails EMPTY, so a replay looks like an operator with no agenda
        # rather than like a broken filter.
        # Scope, stated honestly so nobody reads this as a fire that was put out: NO corpus exercises the
        # dossier under `travel()` today (the timeline runner never calls `compose_context`), and production is
        # unaffected because both clocks agree there. This is PREVENTIVE — it pays off for whoever measures the
        # dossier with the clock pinned, which is the only way to measure it honestly.
        today = _dt.datetime.fromtimestamp(_now()).date().isoformat()
        out = []
        for it in items:
            if not isinstance(it, dict):
                continue
            d = str(it.get("date") or it.get("day") or "")
            label = str(it.get("title") or it.get("label") or it.get("text") or "").strip()
            if not label or (d and d < today):
                continue
            hh = str(it.get("time") or it.get("hour") or "").strip()
            out.append(f"· {d}{(' ' + hh) if hh else ''} — {label[:90]}")
            if len(out) >= limit:
                break
        return out
    except Exception:
        return []


def _background_slot_off_topic(slot: str, prompt: str) -> bool:
    """Delegates to `memory.api.background_slot_off_topic` — the rule has ONE home (see its docstring: three
    surfaces render pills to a model and all three must apply it). Kept as a name here because the dossier's
    tests and the wiring guard call it."""
    from memory.api import background_slot_off_topic as _rule
    return _rule(slot, prompt)


def _dossier_sync(prompt: str, budget: int) -> tuple[dict, dict, list, list, list, list]:
    """Parte SÍNCRONA del dossier (todo el I/O de memoria) — pensada para `asyncio.to_thread`."""
    from memory import api as memory
    try:
        st = memory.state()
    except Exception:
        st = {}
    try:
        res = memory.query(prompt, budget_tokens=budget)
    except Exception:
        res = {"memories": []}
    try:
        critical = memory.critical_facts()
    except Exception:
        critical = []
    # eje por CONCEPTOS (T178/T183 — by_concepts estaba construida y SIN caller de producción): los conceptos
    # derivados de la petición afloran el cluster completo (vacaciones→viajes/familia/finanzas; restaurante→comida
    # y con él la restricción del celíaco) aunque el embedding plano no los traiga.
    try:
        concepts = _derive_concepts(prompt) or []
        by_c = memory.by_concepts(concepts, limit=8) if concepts else []
    except Exception:
        by_c = []
    agenda = _agenda_lines()
    rules = [str(r).strip() for r in (st.get("rules") or []) if str(r).strip()][:8]
    return st, res, critical, by_c, agenda, rules


async def compose_context(prompt: str, *, budget: int = 2000) -> str:
    """DOSSIER del worker (v2, V2-056 — auditoría 2026-07-19 P1-2): contexto MULTI-EJE para una tarea, dentro de
    `budget` tokens. Antes era estado + UNA query RRF: un «prepárame unas vacaciones» no traía familia, presupuesto,
    alergias ni fechas. Ahora: §perfil (estado + reglas del operador) + §⚠️ CRÍTICOS SIEMPRE (una alergia debe
    llegar al worker que reserva restaurante — nunca depende del ranking) + §recall semántico + §eje por CONCEPTOS
    (`by_concepts`, T178/T183) + §agenda próxima. Solo DURABLES (el conv-buffer ya no compite por los huecos —
    mismo fix que compose_recall en voz). TODO el I/O va en `asyncio.to_thread` (el loop del server no se bloquea).
    Best-effort: si la memoria no está disponible, devuelve ''. Nunca lanza."""
    try:
        st, res, critical, by_c, agenda, rules = await asyncio.to_thread(_dossier_sync, prompt, budget)
    except Exception:
        return ""

    # repesca: si el recall es ambiguo, una segunda pasada barata con el router LLM (best-effort, off-loop).
    if _is_ambiguous(prompt, res):
        expanded = await _llm_expand_query(prompt)
        if expanded:
            try:
                from memory import api as memory
                res2 = await asyncio.to_thread(memory.query, prompt + " " + expanded, budget_tokens=budget)
                if len(res2.get("memories") or []) > len(res.get("memories") or []):
                    res = res2
            except Exception:
                pass

    parts: list[str] = []
    sl = _state_lines(st)
    if rules:
        sl.append("Reglas del operador: " + "; ".join(rules) + ".")
    if sl:
        parts.append("── ESTADO (perfil del operador) ──\n" + "\n".join(sl))
    if critical:
        parts.append("── ⚠️ CRÍTICO (respetar SIEMPRE) ──\n" + "\n".join(f"· {c}" for c in critical))

    # recall + eje conceptual, DEDUP por texto y SOLO durable (kind/level): la charla cruda fuera del dossier.
    seen: set[str] = set()
    lines: list[str] = []
    for m in (res.get("memories") or []) + by_c:
        if (m.get("kind") or "") == "conv" or (m.get("level") or "mid") == "short":
            continue
        if _background_slot_off_topic(m.get("slot") or "", prompt):
            continue
        txt = (m.get("text") or "").strip().replace("\n", " ")
        key = txt.lower()[:120]
        if len(txt) < 8 or key in seen:     # fuera píldoras-ruido (un nodo suelto tipo 'familia')
            continue
        seen.add(key)
        lines.append(f"· {txt[:200]}")
        if len(lines) >= 16:
            break
    if lines:
        parts.append("── LO QUE SABES DEL OPERADOR (relevante a la tarea) ──\n" + "\n".join(lines))
    if agenda:
        parts.append("── AGENDA PRÓXIMA ──\n" + "\n".join(agenda))
    return "\n\n".join(parts)


# Backstop DETERMINISTA de conceptos (T126): el LLM heart etiqueta bien a veces y otras devuelve concepts=[] (p. ej.
# "ascendido a jefe de equipo en 2021" se quedó sin 'trabajo' → fuera del cluster). Este mapa keyword→concepto
# GARANTIZA cobertura de los dominios de vida habituales cuando el LLM no aporta ninguno. Off-hot-path, barato,
# multi-concepto (cap 3). No pretende ser exhaustivo — cubre lo común para que el recall por categoría no dependa
# de la consistencia del modelo pequeño.
# Vocabulario de conceptos: vive en el SUBSTRATO (`memory/concepts.py`) → un solo sitio para cómo se ESCRIBE y
# cómo se DIBUJA la organización (el visor deriva el mapa de CORTO con el MISMO deriver). T126.
