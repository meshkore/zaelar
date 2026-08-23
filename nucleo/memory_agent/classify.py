"""Deterministic heuristic classifier: decides WHERE each utterance is stored (V2-013).

Split out VERBATIM (audit 2026-08-23). Reads only the language-mark bank.
"""
from __future__ import annotations

import re

from nucleo.memory_agent.gates import _slot_for_patch  # noqa: F401
from nucleo.memory_agent.lang_marks import (  # noqa: F401
    _COMMAND_RE, _COMMITMENT_RE, _DESIRE_RE, _OBSERVATION_RE, _PROFILE_CAR_RE, _PROFILE_GOAL_RE,
    _PROFILE_HW_RE, _PROFILE_LOC_RE, _PROFILE_NAME_RE, _PROFILE_PROJECT_RE, _PROFILE_TREATMENT_RE,
    _REVERSAL_RE, _ROUTINE_RE, _TRIVIA_SKIP_RE)


def classify(text: str) -> dict:
    """Decide DÓNDE guardar `text` — el "corazón" del agente de memoria (V2-013).

    Devuelve un plan::

        {
          "state_patch": dict,        # merge superficial en la tabla `state` (perfil del operador); {} si nada.
          "level":       str | None,  # 'short' | 'mid' | 'long' | None (skip: no crear un `memories`)
          "kind":        str,         # 'profile' | 'pref' | 'fact' | 'event' | 'result'
          "importance":  float,       # 0..1 (peso inicial + orden en el retriever)
          "pinned":      bool,        # True = intocable por el consolidador (identidad del operador)
        }

    Reglas (heurística barata, µs, agnóstica del proveedor):
      - PERFIL detectado (nombre/ubicación/trato/hardware/coche) → `state_patch` + traza `long` pinned. Es lo
        que hoy se pierde: el operador dice "me llamo Ramón" en un turno normal y no llegaba a `state`.
      - DESEO/PREF durable ("quiero X", "prefiero Y") → `long`, no pinned.
      - TRIVIA (saludos, sí/no) o COMANDO ("cierra widget") → skip (`level=None`, sin state_patch).
      - Resto → `mid` (deliberación / hecho genérico). El consolidador decide más adelante si sube a `long`.
    """
    t = (text or "").strip()
    if not t:
        return {"state_patch": {}, "level": None, "kind": "event", "importance": 0.0, "pinned": False}

    patch: dict = {}
    m = _PROFILE_NAME_RE.search(t)
    if m:
        patch["operator_name"] = m.group(1).strip().strip(",.")
    m = _PROFILE_LOC_RE.search(t)
    if m:
        patch["location"] = m.group(1).strip().strip(",.")
    m = _PROFILE_TREATMENT_RE.search(t)
    if m:
        patch["treatment"] = m.group(1).lower().strip()
    m = _PROFILE_HW_RE.search(t)
    if m:
        patch["hardware"] = m.group(1).strip().strip(",.")
    m = _PROFILE_CAR_RE.search(t)
    if m:
        patch["car"] = m.group(1).strip().strip(",.")
    m = _PROFILE_GOAL_RE.search(t)
    if m:
        patch["objetivo"] = m.group(1).strip().strip(",.")
    m = _PROFILE_PROJECT_RE.search(t)
    if m:
        patch["proyecto"] = m.group(1).strip().strip(",.")

    if patch:
        # Perfil: además del state, dejamos una TRAZA durable en `memories` (long, pinned) para el visor y el
        # recall — "ese dato lo dijiste tal día". El `slot` (V2-013) da supersede EXACTO: el dato nuevo con el
        # mismo slot invalida el viejo ("el más reciente MANDA").
        return {"state_patch": patch, "level": "long", "kind": "profile",
                "importance": 0.9, "pinned": True, "slot": _slot_for_patch(patch)}

    if _TRIVIA_SKIP_RE.match(t) or _COMMAND_RE.search(t):
        return {"state_patch": {}, "level": None, "kind": "event", "importance": 0.0,
                "pinned": False, "slot": None}

    if _DESIRE_RE.search(t):
        return {"state_patch": {}, "level": "long", "kind": "pref",
                "importance": 0.7, "pinned": False, "slot": None}

    # REDES DETERMINISTAS también en la ruta heurística (fix 2026-07-20, con el default ya endurecido): con el
    # LLM caído, lo inequívocamente durable NO puede degradar a short — salud crítica (writer la pinnea además en
    # su chokepoint), compromisos/tareas encargadas ("¿qué te pedí?"), rutinas, reversiones y observaciones.
    from memory import writer as _mw
    if _mw._is_critical_health(t):
        return {"state_patch": {}, "level": "long", "kind": "fact",
                "importance": 0.95, "pinned": True, "slot": None}
    if _COMMITMENT_RE.search(t):
        return {"state_patch": {}, "level": "mid", "kind": "event",
                "importance": 0.6, "pinned": False, "slot": None}
    if _ROUTINE_RE.search(t) or _OBSERVATION_RE.search(t) or _REVERSAL_RE.search(t):
        return {"state_patch": {}, "level": "long", "kind": "fact",
                "importance": 0.6, "pinned": False, "slot": None}

    # DEFAULT endurecido (auditoría 2026-07-19 H2): el resto era `mid` durable con el TEXTO CRUDO del STT — con
    # el CORAZÓN caído la heurística metía a chorro basura vigente en el largo plazo ("Conchacón…", "¡Lera!").
    # Ahora el crudo sin señal fuerte degrada a CORTO con TTL: visible unos días (recencia), jamás durable. Lo
    # durable de verdad lo rescatan las redes deterministas (compromisos/rutinas/salud/…) o el LLM al volver.
    return {"state_patch": {}, "level": "short", "kind": "fact",
            "importance": 0.4, "pinned": False, "slot": None, "ttl_days": 3.0}



