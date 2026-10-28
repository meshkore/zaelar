"""`compose_state` — the SHARED STATE both brains read: small, ordered, in the operator's language (V2-027).

  A. **QUIÉN ERES** — the mission (state.mission, seeded at init from `langs`; `mission_fallback` until then).
  B. **QUIÉN TIENES DELANTE** — the operator, the critical facts and tastes, the durable state fields, the open
     widgets, the live processes and rails, and the salient durable profile — errands apart from facts.
  C. **DE QUÉ ÍBAIS HABLANDO** — the last few lines of the short term (a cut, never a model summary).

A DIRECT read (µs, no LLM, no retriever), cached off the hot path (`nucleo/flash/memory_cache`). The readers it
calls are looked up on the package (`_p()`), so a patch on `memory._prompt` governs them.
"""
from __future__ import annotations

from .. import state as _state

_STATE_RENDERED = {"assistant_name", "operator_name", "language", "treatment", "location", "recent", "topics",
                   "open_widgets", "activity", "sessions", "mission", "rails", "rules"}

_RAIL_STATUS = {"searching": "buscando", "playing": "sonando", "paused": "en pausa",
                "sin_resolver": "SIN RESOLVER"}

#: Pills about an ERRAND, not about him: what he asked for (`request`) and what an errand delivered (`result`).
_ERRAND_KINDS = frozenset({"request", "result"})


def _p():
    from memory import _prompt
    return _prompt


def compose_state(*, mission_fallback: str = "") -> tuple[str, str, dict]:
    """`(block, operator_name, stats)`. Best-effort: `('', '', {...})` when memory is unavailable."""
    stats = {"has_state": False, "state_fields": 0, "short_count": 0, "short_chars": 0,
             "salient_count": 0, "has_mission": False, "op": ""}
    try:
        st = _state.read()
    except Exception:
        return "", "", stats
    op = (st.get("operator_name") or "").strip()
    stats["op"] = op
    mission = (st.get("mission") or "").strip() or (mission_fallback or "").strip()
    stats["has_mission"] = bool(mission)

    sit, crit, screen_listed = _situation(st, op)
    stats["state_fields"] = len(sit)
    stats["has_state"] = bool(sit)

    # AN ERRAND IS NOT A FACT ABOUT THE PERSON (V2-337): under one «dalo por sabido» list the agent opened a monitor
    # search talking about CARS, and 3 of 5 live slots were errands. The distiller writes a delegated task as
    # `request`, the circuit writes what an errand delivered as `result`; both stay VISIBLE (hiding them makes an
    # agent forget what it was asked) but are not presented as things known about him.
    salient: list[str] = []
    errands: list[str] = []
    try:
        for m in _p().salient_long(limit=5, max_chars=440):
            t = (m.get("text") or "").strip().replace("\n", " ")
            if not t:
                continue
            # An ASK is never an outcome, and a delivery nobody checked is never «done» (its verdict says which).
            if m.get("kind") == "request":
                errands.append(f"· pidió: {t[:140]} [sin resultado registrado]")
            elif m.get("kind") == "result" and (m.get("verdict") or "met") != "met":
                errands.append(f"· entregado, sin verificar: {t[:140]}")
            else:
                (errands if m.get("kind") in _ERRAND_KINDS else salient).append(f"· {t[:140]}")
    except Exception:
        pass
    stats["salient_count"] = len(salient)
    stats["errand_count"] = len(errands)

    convo: list[str] = []
    short_chars = 0
    try:
        for m in _p().recent_short(limit=5, max_chars=550):
            t = (m.get("text") or "").strip().replace("\n", " ")
            if t:
                convo.append(f"· {t[:180]}")
                short_chars += len(t)
    except Exception:
        pass
    stats["short_count"] = len(convo)
    stats["short_chars"] = short_chars

    if not screen_listed and (mission or sit or salient or errands or convo):
        # An empty canvas says so out loud: silence let the model claim a card was on screen (2026-09-19).
        sit.append("Pantalla VACÍA ahora: ningún widget a la vista.")
        stats["state_fields"] = len(sit)

    if not (mission or sit or salient or errands or convo):
        return "", op, stats
    return _render(mission, sit, salient, errands, convo, crit), op, stats


def _situation(st: dict, op: str) -> tuple[list[str], list[str], bool]:
    """B · the situational lines, the critical facts, and whether the screen was listed."""
    sit: list[str] = []
    # IDENTITY WITHOUT AMBIGUITY (2026-09-09): renamed «Johnny», it greeted the OPERATOR as «Johnny». The OPERATOR
    # goes FIRST in the sentence — the small model takes the first name it sees as the vocative. Never «⚠️» here:
    # that marker is reserved for the critical facts (pinned by test_the_limit_is_the_last_thing_read.py).
    aname = (st.get("assistant_name") or "Zaelar").strip() or "Zaelar"
    if op:
        sit.append(f"El operador se llama {op}: para dirigirte a él usa «{op}» y SOLO «{op}». Tú te llamas "
                   f"{aname} — «{aname}» eres TÚ (y es tu palabra de activación), JAMÁS un modo de llamarle "
                   f"a él.")
    elif aname != "Zaelar":
        sit.append(f"Te llamas {aname}.")      # a rename is something to say even before his name is known
    if st.get("treatment"):
        sit.append(f"Trato preferido: {st['treatment']}.")
    # Spoken rules are rows of the rules table since V2-806: the voice turn composes them, not memory.
    if st.get("location"):
        sit.append(f"Ubicación: {st['location']}.")
    # CRITICAL safety facts (allergies, conditions) ALWAYS, outside the salient ranking: forgetting one is a safety
    # failure. The writer's guard marks them `meta.critical='health'`.
    try:
        crit = _p().critical_facts(limit=6)
    except Exception:
        crit = []
    if crit:
        sit.append("⚠️ CRÍTICO (tenlo SIEMPRE presente): " + " · ".join(crit))
    # Tastes are ACTIVE state, on their own line: in the top-5 ranking they always lost their seat.
    try:
        gustos = _p().tastes(limit=6)
    except Exception:
        gustos = []
    if gustos:
        sit.append("GUSTOS Y PREFERENCIAS suyos (dalo por sabido, sin buscar): " + " · ".join(gustos))
    for k, v in st.items():                    # the custom scalar fields of the state: his durable «stack»
        if k in _STATE_RENDERED:
            continue
        if isinstance(v, (str, int, float)) and str(v).strip():
            sit.append(f"{k.capitalize().replace('_', ' ')}: {v}.")
    open_w = [str(w).strip() for w in (st.get("open_widgets") or []) if str(w).strip()]
    if open_w:
        sit.append("Widgets ABIERTOS ahora en su pantalla: " + ", ".join(open_w[:12]) + ".")
    sit += _processes(st) + _rails(st)
    return sit, crit, bool(open_w)


def _processes(st: dict) -> list[str]:
    """The live worker sessions (V2-036) — id, goal, phase — so the orchestrator ties each order to the right one.
    DATA only: how to steer workers is the FlashBrain's own layer."""
    sessions = [s for s in (st.get("sessions") or []) if isinstance(s, dict) and (s.get("goal") or s.get("phase"))]
    if not sessions:
        activity = [str(a).strip() for a in (st.get("activity") or []) if str(a).strip()]
        return ["Tareas en marcha ahora: " + "; ".join(a[:80] for a in activity[:6]) + "."] if activity else []
    lines = []
    waiting_any = False
    for s in sessions[:6]:
        sid = str(s.get("id") or "?")
        goal = (str(s.get("goal") or "")).strip().replace("\n", " ")[:90]
        phase = (str(s.get("phase") or "")).strip()[:40]
        line = f"  · [{sid}] «{goal}»" + (f" — fase: {phase}" if phase else "")
        if (s.get("waiting_on") or "") == "user":
            waiting_any = True
            ask = (str(s.get("ask") or "")).strip()[:120]
            line += f" — ESPERA tu respuesta a: «{ask}»" if ask else " — ESPERA una respuesta tuya"
        lines.append(line)
    head = "PROCESOS DE FONDO en marcha ahora:\n"
    if waiting_any:
        head = "⚠️ Un proceso de fondo ESPERA una respuesta del operador (abajo). " + head
    return [head + "\n".join(lines)]


def _rails(st: dict) -> list[str]:
    """Rails with a LIVE run (V2-042): what is being searched, what plays, the unresolved searches he can resume."""
    rails = [a for a in (st.get("rails") or []) if isinstance(a, dict) and (a.get("label") or "").strip()]
    if not rails:
        return []
    lines = []
    for a in rails[:5]:
        status = _RAIL_STATUS.get(str(a.get("status") or ""), str(a.get("status") or ""))
        line = f"  · [{str(a.get('kind') or '?')}] {status}: «{str(a['label']).strip()[:90]}»"
        det = (str(a.get("detail") or "")).strip()
        if det:
            line += f" — {det[:80]}"
        att = int(a.get("attempts") or 0)
        if att > 1:
            line += f" ({att} intentos)"
        lines.append(line)
    return ["Rails en curso (conducciones tuyas):\n" + "\n".join(lines)]


def _render(mission: str, sit: list[str], salient: list[str], errands: list[str], convo: list[str],
            crit: list[str]) -> str:
    parts: list[str] = []
    if mission:
        parts.append("── QUIÉN ERES ──\n" + mission)
    if sit or salient or errands:
        b = "── QUIÉN TIENES DELANTE (trátalo como sabido de siempre; salúdalo por su nombre sin volver a preguntar) ──"
        if sit:
            b += "\n" + "\n".join(sit)
        if salient:
            b += "\n[Lo que sabes de él, dalo por sabido sin buscar]\n" + "\n".join(salient)
        if errands:
            # Says what they ARE and nothing about what to do: «ignore» and «handle» are both measured failures.
            b += ("\n[Encargos que te hizo en algún momento — NO son hechos sobre él, y que lo pidiera no dice "
                  "cómo acabó. No empieces a trabajar en uno salvo que él lo saque en este turno]\n"
                  + "\n".join(errands))
        parts.append(b)
    if convo:
        parts.append("── DE QUÉ ÍBAIS HABLANDO (lo más reciente primero; el último MANDA si hay contradicción) ──\n"
                     + "\n".join(convo))
    # V2-490 — THE LIMIT AGAIN, LAST, AS A CHECK AND NOT AS BIOGRAPHY: with «⚠️ CRÍTICO» present, 2 of 4 rounds
    # still proposed pasta to a coeliac. Here it is the last thing read, worded as a check on what it is about to
    # say, governed by the CLASS of the fact (`meta.critical`) — no domain word anywhere.
    if crit:
        parts.append("── LÍMITES QUE NO PUEDES SALTARTE ──\n"
                     + "⚠️ " + " · ".join(crit) + "\n"
                     + "Antes de PROPONERLE nada que vaya a comer, beber, tomar o hacer, compruébalo contra esa "
                       "línea: si no la cumple, NO lo nombres y ofrécele otra cosa. Proponerlo y matizarlo "
                       "después cuenta como habérselo propuesto.")
    return "\n\n".join(parts)
