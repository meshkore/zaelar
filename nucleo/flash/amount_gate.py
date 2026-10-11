"""nucleo/flash/amount_gate.py — when an amount in a reply needs a source, and what counts as one.

`delivery.strip_unbacked_amounts` (V2-472) cut invented market figures only while an errand was LIVE. Measured on
`search-buy-phone__es` (2026-10-11 20:41): the errand had just FAILED for lack of quota, the operator said «intenta
por otra vía», and the reply was «He revisado las principales tiendas online y operadores… MediaMarkt por 1.079
euros, AT&T a un total de 830 dólares, Bodega Aurrera por unos 17 mil pesos» — zero sheet rows, and the two web
results of that turn named none of those figures. Three holes, one per half of the rule:

  · the GATE — an errand that just died is the moment with the LEAST to say, so it counts like a live one;
  · the SHAPE — «1.079 euros», «830 dólares», «17 mil pesos» never matched: only symbols and ISO codes did;
  · the BACKING — the in-turn search's own results are a legitimate source, so they back a figure (a price the
    search really returned survives) — and it is the same reader for both channels' fact door.
"""
from __future__ import annotations

import re
import time

#: A just-run search backs a figure for this long (the composing pass is the same turn; the next turn may cite it).
SEARCH_BACKING_S = 240.0

_LAST_SEARCH: dict = {"at": 0.0, "text": ""}
_MIL_RE = re.compile(r"\bmil\b", re.I)


def note_search(res: dict | None) -> None:
    """Keep what a web search returned (titles, snippets, synthesized answer) as backing for figures."""
    try:
        res = res or {}
        parts = [str(res.get("answer") or "")]
        for r in res.get("results") or []:
            if isinstance(r, dict):
                parts += [str(r.get(k) or "") for k in ("title", "snippet", "body", "content", "description")]
        _LAST_SEARCH.update(at=time.time(), text=" ".join(p for p in parts if p)[:20000])
    except Exception:  # noqa: BLE001 — backing is an allowance: failing to record it only cuts more
        _LAST_SEARCH.update(at=0.0, text="")


def search_backing(now: float | None = None) -> str:
    return _LAST_SEARCH["text"] if ((now or time.time()) - _LAST_SEARCH["at"]) <= SEARCH_BACKING_S else ""


def an_errand_just_failed() -> bool:
    """An errand of this conversation ended badly within the just-ended window (cancelled ones do not count)."""
    try:
        from nucleo import dispatch as _d
        return any(not e.get("ok") and str(e.get("status") or "") != "cancelled"
                   for e in _d.recently_ended_sessions())
    except Exception:  # noqa: BLE001
        return False


def amount_digits(amount: str) -> str:
    """The digits an amount names, with «mil» read as ×1000 («17 mil pesos» is 17000, not the «17» of iPhone 17)."""
    digits = "".join(c for c in str(amount or "") if c.isdigit())
    return digits + "000" if (digits and _MIL_RE.search(str(amount or ""))) else digits


def backed(digits: str, backing: set[str]) -> bool:
    """Exact digits, or — from three digits up — the leading digits of a backing figure («1079» in «1.079,00»)."""
    if not digits or digits in backing:
        return True
    return len(digits) >= 3 and any(b.startswith(digits) for b in backing)


def unbacked_line() -> str:
    try:
        from i18n import langs as _lg
        return _lg.current_language().amounts_unbacked
    except Exception:  # noqa: BLE001
        return ""
