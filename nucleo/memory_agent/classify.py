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
    """Decide WHERE to store `text` — the "heart" of the memory agent (V2-013).

    Returns a plan::

        {
          "state_patch": dict,        # shallow merge into the `state` table (operator profile); {} if none.
          "level":       str | None,  # 'short' | 'mid' | 'long' | None (skip: do not create a `memories`)
          "kind":        str,         # 'profile' | 'pref' | 'fact' | 'event' | 'result'
          "importance":  float,       # 0..1 (initial weight + retriever ordering)
          "pinned":      bool,        # True = untouched by the consolidator (operator identity)
        }

    Rules (cheap heuristic, µs, provider-agnostic):
      - PROFILE detected (name/location/treatment/hardware/car) → `state_patch` + a pinned `long` trace. This is what
        gets lost today: the operator says "my name is Ramón" in a normal turn and it never reaches `state`.
      - Durable DESIRE/PREF ("I want X", "I prefer Y") → `long`, not pinned.
      - TRIVIA (greetings, yes/no) or COMMAND ("close widget") → skip (`level=None`, no state_patch).
      - Remainder → `mid` (deliberation / generic fact). The consolidator decides later whether to promote it to `long`.
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
        # Profile: in addition to state, we leave a durable TRACE in `memories` (long, pinned) for the viewer and
        # recall — "you said that fact on such-and-such a day". The `slot` (V2-013) provides EXACT supersession: the
        # new fact with the same slot invalidates the old one ("the most recent one WINS").
        return {"state_patch": patch, "level": "long", "kind": "profile",
                "importance": 0.9, "pinned": True, "slot": _slot_for_patch(patch)}

    if _TRIVIA_SKIP_RE.match(t) or _COMMAND_RE.search(t):
        return {"state_patch": {}, "level": None, "kind": "event", "importance": 0.0,
                "pinned": False, "slot": None}

    if _DESIRE_RE.search(t):
        return {"state_patch": {}, "level": "long", "kind": "pref",
                "importance": 0.7, "pinned": False, "slot": None}

    # DETERMINISTIC NETWORKS also in the heuristic path (fix 2026-07-20, with the default already hardened): with the
    # LLM down, anything unambiguously durable MUST NOT degrade to short — critical health (the writer also pins it at
    # its chokepoint), commitments/assigned tasks ("what did I ask you?"), routines, reversals, and observations.
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

    # Hardened DEFAULT (2026-07-19 H2 audit): the remainder used to be durable `mid` with the RAW STT TEXT — with
    # the HEART down, the heuristic was dumping current junk into the long term ("Conchacón…", "¡Lera!").
    # Now raw text without a strong signal degrades to SHORT with TTL: visible for a few days (recency), never durable.
    # Truly durable items are rescued by the deterministic networks (commitments/routines/health/…) or the LLM when it returns.
    return {"state_patch": {}, "level": "short", "kind": "fact",
            "importance": 0.4, "pinned": False, "slot": None, "ttl_days": 3.0}


