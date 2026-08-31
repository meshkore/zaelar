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
    """Compose the STATE block of the prompt from the state (all fields with a value).

    Previously it rendered only 5 fixed fields (name/treatment/location/recent/topics). It now also renders ANY
    other custom field with a value (e.g. `hardware`, `car`, `language≠es`), so the prompt sees the same thing as
    the viewer and there are no "invisible" fields."""
    lines: list[str] = []
    op = (st.get("operator_name") or "").strip()
    if op:
        lines.append(f"Operador: {op}.")
    if st.get("treatment"):
        lines.append(f"Trato: {st['treatment']}.")
    if st.get("location"):
        lines.append(f"Ubicación: {st['location']}.")
    # Custom fields (hardware, car, company, etc.): any key with a scalar value not in the canonical list.
    # Exclude `mission`: it is the ASSISTANT's prompt (zaelar's identity), not the operator's profile — in a worker's
    # dossier it was 900-character noise (V2-056). `rules` is rendered separately by compose_context (a list, not a scalar).
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
    """Does recall warrant a second pass with the LLM router? Yes if the query is very short or the results are
    few/weak. Cheap, with no network."""
    mems = res.get("memories") or []
    if not mems:
        return True
    if len((prompt or "").split()) <= 2:
        return True
    top = max((m.get("score", 0.0) for m in mems), default=0.0)
    return top < _WEAK_SCORE


async def _llm_expand_query(prompt: str) -> str:
    """CHEAP LLM router: asks the fast model for 3-6 keywords to EXPAND the memory search. Model
    PER INVOCATION (`config/v2` spec). Best-effort: without a model/credential or on any failure → ''."""
    try:
        from nucleo.flash.fast_client import FastClient, spec_from_config
        spec = spec_from_config()
        if not spec.resolved_api_key():        # without a usable credential → fall back to the heuristic
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
    """Upcoming appointments from the agenda widget (read-only, best-effort) — a task dossier without the operator's
    dates plans blindly (audit 2026-07-19 P1-2: the agenda lived OUTSIDE composition)."""
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
    """SYNCHRONOUS part of the dossier (all memory I/O) — intended for `asyncio.to_thread`."""
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
    # CONCEPT-BASED axis (T178/T183 — by_concepts had been built and had NO production caller): concepts
    # derived from the request surface the complete cluster (vacation→travel/family/finances; restaurant→food
    # and with it the celiac restriction) even when the plain embedding does not retrieve them.
    try:
        concepts = _derive_concepts(prompt) or []
        by_c = memory.by_concepts(concepts, limit=8) if concepts else []
    except Exception:
        by_c = []
    agenda = _agenda_lines()
    rules = [str(r).strip() for r in (st.get("rules") or []) if str(r).strip()][:8]
    return st, res, critical, by_c, agenda, rules


async def compose_context(prompt: str, *, budget: int = 2000) -> str:
    """Worker DOSSIER (v2, V2-056 — audit 2026-07-19 P1-2): MULTI-AXIS context for a task, within
    `budget` tokens. Previously it was state + ONE RRF query: a "prepare a vacation for me" request did not bring family, budget,
    allergies, or dates. Now: §profile (state + operator rules) + §⚠️ ALWAYS-CRITICAL (an allergy must reach the worker
    booking a restaurant — it never depends on ranking) + §semantic recall + §CONCEPT axis
    (`by_concepts`, T178/T183) + §upcoming agenda. DURABLES only (the conv-buffer no longer competes for the slots —
    same fix as compose_recall in voice). ALL I/O runs in `asyncio.to_thread` (the server loop is not blocked).
    Best-effort: if memory is unavailable, returns ''. Never raises."""
    try:
        st, res, critical, by_c, agenda, rules = await asyncio.to_thread(_dossier_sync, prompt, budget)
    except Exception:
        return ""

    # Backfill: if recall is ambiguous, a cheap second pass with the LLM router (best-effort, off-loop).
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

    # Recall + conceptual axis, DEDUPLICATED by text and DURABLE only (kind/level): raw conversation stays out of the dossier.
    seen: set[str] = set()
    lines: list[str] = []
    for m in (res.get("memories") or []) + by_c:
        if (m.get("kind") or "") == "conv" or (m.get("level") or "mid") == "short":
            continue
        if _background_slot_off_topic(m.get("slot") or "", prompt):
            continue
        txt = (m.get("text") or "").strip().replace("\n", " ")
        key = txt.lower()[:120]
        if len(txt) < 8 or key in seen:     # exclude noise snippets (a standalone node such as 'family')
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


# DETERMINISTIC concept backstop (T126): the LLM heart sometimes labels correctly and sometimes returns concepts=[] (e.g.
# "promoted to team lead in 2021" was left without 'work' → outside the cluster). This keyword→concept map
# GUARANTEES coverage of the usual life domains when the LLM contributes none. Off-hot-path, cheap,
# multi-concept (cap 3). It is not intended to be exhaustive — it covers common cases so category recall does not depend
# on the consistency of the small model.
# Concept vocabulary: lives in the SUBSTRATE (`memory/concepts.py`) → one place for how the organization is WRITTEN and
# how it is DRAWN (the viewer derives the SHORT map with the SAME deriver). T126.
