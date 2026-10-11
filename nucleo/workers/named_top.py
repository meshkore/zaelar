"""nucleo/workers/named_top.py — a finished shortlist names the options it owes, by name (V2-782).

Two rounds of 2026-10-11, one shape:
  · search-buy-used-car EN — «just send me the top 3 once you have real listings»: the closing notice said «Your
    top three are on screen. Best pick is the 2018 Ford Fusion Hybrid…» — one of three, and «on screen» to a man
    who had said not to bother with the sheet.
  · cheapest-monitor EN — 44 rows on the errand's sheet, and the notice named ONE monitor, with no alternative to
    compare it to.

The spoken line is composed by a model told «at most two short sentences» (`spoken_delivery`), and that brevity is
right for the voice — but how many options he is owed is not the composer's call. It is a fact of his words (a
number: «top 3», «los tres mejores») or, when he named none, of the errand's shape (a sheet with three or more
candidates is a comparison, and a comparison is three). So the line is completed here, from the errand's sheet,
with the options it did not name — never invented, never more than the sheet holds.
"""
from __future__ import annotations

import re

from search.asked import norm as _norm
from search.criteria import _NUMBER_WORDS

_MAX = 5
_DEFAULT = 3
_NUM = r"(\d{1,2}|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")"
_ASKED = re.compile(rf"\btop\s*{_NUM}\b|\b(?:the|los|las|el|la|dame|give me|send me|tell me)\s+{_NUM}\s+"
                    rf"(?:mejores|best|top|opciones|options|primeros|primeras|candidat\w+)\b"
                    rf"|\b{_NUM}\s+(?:mejores|best options|best ones|opciones|options)\b", re.I)


def asked_n(texts) -> int:
    """The number of options his words asked for («top 3», «the three best», «dame tres opciones»), or 0."""
    for t in texts or []:
        m = _ASKED.search(_norm(t))
        if m:
            tok = next(g for g in m.groups() if g)
            n = int(tok) if tok.isdigit() else _NUMBER_WORDS.get(tok, 0)
            if 1 <= n <= 20:
                return min(n, _MAX)
    return 0


def _row(item: dict) -> str:
    title = str(item.get("title") or "").strip().rstrip("…").strip()
    price = str(item.get("price") or "").strip()
    return f"{title} — {price}" if price else title


def _named(said: str, item: dict) -> bool:
    toks = [w for w in _norm(str(item.get("title") or "").rstrip("…")).split()
            if any(c.isdigit() for c in w) or len(w) >= 4]
    s = set(_norm(said).split())
    digits = [t for t in toks if any(c.isdigit() for c in t)]
    words = [t for t in toks if t not in digits]
    if digits and not all(t in s for t in digits):
        return False                          # «2013 Ford C-Max» is not named by a line about «2018 Ford Fusion»
    return bool(toks) and sum(1 for t in words if t in s) >= min(1 if digits else 2, len(words))


def complete(said: str, rec) -> str:
    """`said` plus the options it owes and did not name. Never raises; with nothing owed, `said` unchanged."""
    try:
        sheet = str(getattr(rec, "sheet", "") or "")
        if not sheet or not said:
            return said
        from widgets.results import data as _d
        rows = [i for i in (_d.view_data(sheet).get("items") or []) if str(i.get("title") or "").strip()]
        texts = [str(getattr(rec, "goal", "") or "")] + [str(getattr(j, "text", "") or "")
                                                       for j in (getattr(rec, "injects", None) or [])]
        n = asked_n(texts) or (_DEFAULT if len(rows) >= _DEFAULT else 0)
        n = min(n, len(rows))
        if n < 2:
            return said
        named = [i for i in rows if _named(said, i)]
        if len(named) >= n:
            return said
        picks = (named + [i for i in rows if i not in named])[:n]
        from i18n import langs as _langs
        line = _langs.current_language().top_rows_line.format(n=n, rows="; ".join(_row(i) for i in picks))
        _emit(n, len(named), sheet)
        return f"{said.rstrip()} {line}"
    except Exception as e:  # noqa: BLE001 — the notice still goes out as composed
        __import__("logging").getLogger(__name__).warning("named_top failed: %s", e)
        return said


def _emit(n: int, named: int, sheet: str) -> None:
    try:
        from voice.observer import emit
        emit("task", "📋 delivery names the options it owes", role="system",
             extra={"owed": n, "named_by_line": named, "sheet": sheet})
    except Exception as e:  # noqa: BLE001
        __import__("logging").getLogger(__name__).debug("named_top emit failed: %s", e)
