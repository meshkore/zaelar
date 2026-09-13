"""nucleo/errands/playbooks.py — how a KIND of errand is done, as DATA (V2-683).

The operator asked for workflows — «deberíamos tener workflows para reservar un restaurante, organizar una
reunión…» — and immediately drew the boundary himself: «que esos workflows además fueran dinámicos, porque
las preferencias de otro usuario podrían ser diferentes». The doctrine in CLAUDE.md draws the same line
from the other side: RESOURCES nailed down, REASONING open, and a hardcoded map of the world may say
«start here», never «only here».

So a playbook is a BRIEFING, not a script:

  · `done_when` — the condition that CLOSES it, machine-checkable (`verify.py` runs it). Without this an
    errand can never close itself, which is the requirement he stated out loud.
  · `needs` — what has to be known before acting, so the errand ASKS instead of inventing (the V2-652 scar:
    a worker typed a placeholder NIF into a real form, twice).
  · `brief` — a few sentences of how this kind of thing is done well. Never steps.
  · `stop_when` — what ends it without success.

**Three properties make it a shortcut instead of a fence**, and each is a test:
  1. an errand with NO playbook still runs (the generic path), so a kind nobody wrote is not a dead end;
  2. the operator's own preferences layer OVER genesis (`config/playbooks.json`), which is his «otro
     usuario querría Zoom» in one file — the same two-layer shape `style_policy` already uses;
  3. nothing here names a person, a company or a site: swap «reunión»→«cena» and it still stands.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path

from loguru import logger

_GENESIS = Path(__file__).resolve().parents[1] / "genesis.json"
_cache: dict | None = None
_override_cache: tuple[float, dict] = (0.0, {})

#: The brief travels on EVERY wake and in the pack, so it is bounded — measured in the test, not hoped for.
MAX_BRIEF = 700


def _fold(s) -> str:
    """Accent-stripped lowercase — the same normalisation every matcher in this house uses."""
    n = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(ch for ch in n if unicodedata.category(ch) != "Mn")


def _genesis() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = dict(json.loads(_GENESIS.read_text(encoding="utf-8")) or {})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"errands: no pude leer genesis.json ({e!r})")
            _cache = {}
    return _cache


def _override_path() -> Path:
    try:
        from nucleo import workspace
        return workspace.root() / "config" / "playbooks.json"
    except Exception:
        return Path("config/playbooks.json")


def _override() -> dict:
    """The operator's own file, re-read when it changes on disk (`style_policy`'s mtime cache, same reason:
    a rule he gave by voice has to govern the very next move, and survive a restart)."""
    global _override_cache
    p = _override_path()
    try:
        mtime = p.stat().st_mtime
    except Exception:
        return {}
    if _override_cache[0] == mtime:
        return _override_cache[1]
    try:
        data = dict(json.loads(p.read_text(encoding="utf-8")) or {})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands: config/playbooks.json ilegible ({e!r}) — mandan los valores de fábrica")
        data = {}
    _override_cache = (mtime, data)
    return data


def settings() -> dict:
    """The errand knobs: `shadow`, `grace_h`, `max_days`, `default_window_h`."""
    out = dict(_genesis().get("errands") or {})
    out.update(_override().get("errands") or {})
    return out


def playbooks() -> dict:
    """Every playbook, the operator's file layered over genesis. `_comment` keys are documentation — the
    convention the rest of `genesis.json` already uses — so anything that is not a dict is not a playbook."""
    out = {k: dict(v) for k, v in (_genesis().get("playbooks") or {}).items() if isinstance(v, dict)}
    for k, v in (_override().get("playbooks") or {}).items():
        if isinstance(v, dict):
            merged = dict(out.get(k) or {})
            merged.update(v)
            out[k] = merged
    return out


def get(kind: str) -> dict:
    return dict(playbooks().get(str(kind or "").strip().lower()) or {})


def brief_for(kind: str) -> str:
    return str(get(kind).get("brief") or "")[:MAX_BRIEF]


def done_when(kind: str) -> dict:
    return dict(get(kind).get("done_when") or {})


def needs(kind: str) -> list:
    return list(get(kind).get("needs") or [])


def kind_for(text: str) -> str:
    """Which playbook briefs this errand. A LEXICAL sweep over the objective (`workflows/domains.py`'s
    pattern), and `generic` when nothing matches — never a model call, and never a refusal: an errand whose
    kind we cannot name still runs, which is what keeps this a shortcut and not a gate."""
    # Accent-stripped on BOTH sides, or «resérvame» never matches «reserva» — which is how the operator
    # actually says it, and a table that only fires on the unaccented spelling is a table that does nothing.
    n = _fold(text)
    for kind, spec in playbooks().items():
        for word in (spec.get("matches") or []):
            try:
                if re.search(rf"\b{re.escape(_fold(word))}", n):
                    return kind
            except Exception:
                continue
    return "generic"


# ── what the model is told about the operator's own calendar ────────────────────────────────────────────
def free_slots_line(errand: dict, now: float | None = None) -> str:
    """What is ALREADY TAKEN in the operator's agenda inside this errand's window.

    Deliberately the busy intervals and not «free slots»: a gap this module computed would be a promise
    about his time made by arithmetic — his agenda holds all-day entries, travel and things with no hour,
    and proposing a slot that is technically empty is how a meeting lands on top of something real. Saying
    what is taken lets the model propose around it and say so honestly.
    """
    now = time.time() if now is None else now
    try:
        from widgets.agenda import data as agenda
        rows = (agenda.view_data() or {}).get("meetings") or []
    except Exception:
        return ""
    today = time.strftime("%Y-%m-%d", time.localtime(now))
    end_day = time.strftime("%Y-%m-%d", time.localtime(float(errand.get("deadline") or now)))
    out = []
    for m in rows:
        d = str(m.get("date") or "")
        if not (today <= d <= end_day):
            continue
        hour = str(m.get("startTime") or "").strip()
        title = str(m.get("title") or "").strip()[:40]
        out.append(f"{d} {hour or 'todo el día'} {title}".strip())
        if len(out) >= 8:
            break
    return " · ".join(out)
