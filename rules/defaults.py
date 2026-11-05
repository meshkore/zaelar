"""rules/defaults.py — the factory rules, built from declared data at read time and never stored (V2-806).

Genesis (`nucleo/genesis.json`) is the one source: a `consent` gate per class in `consent.classes`, the global
`ask_at` level and `intent_act_at`, a `voice` preference per knob of `style`, and a `global` preference per knob of `tasks`. A user row at the same scope and key runs after its default and wins; a default
cannot be deleted, only overridden.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import cascade as _cascade
from . import scope as _scope

_GENESIS = Path(__file__).resolve().parent.parent / "nucleo" / "genesis.json"
_cache: dict = {"mtime": None, "rows": []}

#: The global knobs of the consent gate, read from genesis `consent` — values a code path applies, never prose.
GATE_KNOBS = ("ask_at", "intent_act_at")


def _row(scope: str, kind: str, key: str, value, origin: str = "genesis", at: float = 0.0) -> dict:
    sc = _scope.norm(scope)
    return {"id": f"default:{key}@{sc}", "scope": sc, "kind": kind, "key": key, "value": value, "except": [],
            "source": "default", "text": "", "created_at": at, "active": True, "until": None, "origin": origin}


def _build(genesis: dict, at: float) -> list[dict]:
    """`at` is when genesis was written: a factory row can be NEWER than his — which is why the cascade ranks the
    source before the age (`rules/cascade.py`)."""
    out: list[dict] = []
    consent = genesis.get("consent") or {}
    for cls, val in (consent.get("classes") or {}).items():
        v = str(val or "").strip().lower()
        if isinstance(cls, str) and v in _cascade.GATE_VALUES:
            out.append(_row(_scope.class_scope(*_scope.split_key(cls)), "gate", "consent", v, f"genesis:{cls}", at))
    for knob in GATE_KNOBS:
        if knob in consent:
            out.append(_row(_scope.GLOBAL, "gate", knob, consent[knob], "genesis", at))
    for k, v in (genesis.get("style") or {}).items():
        if not str(k).startswith("_"):
            out.append(_row(_scope.VOICE, "pref", str(k), v, "genesis", at))
    for k, v in (genesis.get("tasks") or {}).items():      # V2-851: how long a task waits for his answer, and the like
        if not str(k).startswith("_"):
            out.append(_row(_scope.GLOBAL, "pref", str(k), v, "genesis", at))
    return out


def style_keys() -> list[str]:
    """The knobs of how the voice speaks, as genesis `style` declares them."""
    return [r["key"] for r in rows() if r["scope"] == _scope.VOICE and r["origin"] == "genesis"]


def rows() -> list[dict]:
    try:
        mtime = _GENESIS.stat().st_mtime_ns
    except OSError as e:
        import logging
        logging.getLogger("zaelar.rules").warning(f"rules: no genesis at {_GENESIS} ({e}) — no default rows")
        return []
    if _cache["mtime"] != mtime:
        try:
            _cache.update(mtime=mtime, rows=_build(json.loads(_GENESIS.read_text(encoding="utf-8")), mtime / 1e9))
        except (OSError, ValueError) as e:
            import logging
            logging.getLogger("zaelar.rules").warning(f"rules: genesis unreadable ({e}) — no default rows")
            _cache.update(mtime=mtime, rows=[])
    return [dict(r) for r in _cache["rows"]]
