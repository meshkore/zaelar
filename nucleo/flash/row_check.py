"""nucleo/flash/row_check.py — a question about a row and one of his hard requirements is answered FROM the row.

Measured in `rental-car-automatic-airport` (2026-10-11, ES and EN). «¿Puedes confirmarme que [el Polo] es automático
y que la recogida y devolución son en el aeropuerto de Málaga?» was answered «Voy a pedirle a la búsqueda que lo
confirme… Bueno, de hecho ya hay candidatos en la hoja: «105 € en total»…» — prices, again, to a yes/no question.
The turn had nothing better to read: no row carried the requirement. `widgets/results/hard_checks.py` makes every
row carry one fact per hard requirement (yes · no · «?»); this module is the reading side.

When his sentence is a question that names one of the sheet's hard requirements, the reply gets one sentence from
the sheet: for each row he named, what that row's fact says — «not verified» when it says «?», never silence; and
when he named no row («are these automatic?»), which rows have it verified, or that none has. The sentence states
the field, it does not judge it, and it never claims more than the fact: a value that does not open with yes/no is
read as not verified (`hard_checks.status`).
"""
from __future__ import annotations

import re

#: At most this many named rows are read back: past three it stops being an answer and becomes a list.
_MAX_ROWS = 3
_MAX_ROW_CHARS = 40


def _rows_of(heard_norm: str, items: list[dict]) -> list[dict]:
    """The rows his sentence names: by a word of the title that no OTHER row's title has (so «oferta» or «total»
    never names anything), matched as a whole word."""
    from widgets.results.hard_checks import _norm
    words = [set(re.findall(r"[a-z]{4,}", _norm(i.get("title")))) for i in items]
    named = []
    for i, ws in zip(items, words):
        others = set().union(*(w for w in words if w is not ws)) if len(words) > 1 else set()
        own = ws - others
        if any(re.search(rf"\b{re.escape(w)}\b", heard_norm) for w in own):
            named.append(i)
    return named[:_MAX_ROWS]


def _short(item: dict) -> str:
    t = " ".join(str(item.get("title") or "").split()).rstrip("…")
    return t if len(t) <= _MAX_ROW_CHARS else t[:_MAX_ROW_CHARS - 1].rstrip() + "…"


def line(heard: str, data: dict) -> str:
    """The sentence the sheet `data` owes to his sentence `heard`. "" when it owes none."""
    from widgets.results import hard_checks as H
    h = H._norm(heard)
    if "?" not in str(heard or ""):
        return ""
    items = [i for i in ((data or {}).get("items") or []) if isinstance(i, dict) and i.get("title")]
    asked = [c for c in H.hard_of(data) if H.stems(c) & H.stems(heard)]
    if not (items and asked):
        return ""
    from i18n import langs as _lg
    lang = _lg.current_language()

    def _say(item, crit) -> str:
        f = H.fact_for(item, crit)
        verdict, source = H.status((f or {}).get("value"))
        if verdict in (H.YES, H.NO):
            said = lang.row_check_yes if verdict == H.YES else lang.row_check_no
            return said.format(source=source) if source else said.split(" (")[0]   # no source: the bare word
        return lang.row_check_unknown

    named = _rows_of(h, items)
    if named:
        parts = [f"{_short(i)}: {crit}, {_say(i, crit)}" for i in named for crit in asked]
        return "; ".join(parts) + "."
    out = []
    for crit in asked:
        ok = [_short(i) for i in items if H.status((H.fact_for(i, crit) or {}).get("value"))[0] == H.YES]
        out.append(lang.row_check_some.format(criterion=crit, rows=", ".join(ok[:_MAX_ROWS])) if ok
                   else lang.row_check_none.format(n=len(items), criterion=crit))
    return " ".join(out)


def _live_sheets() -> list[str]:
    """The sheets of the errands live right now (the ones a question about «the Polo» can be about)."""
    sheets: list[str] = []
    from nucleo import dispatch as _disp
    for t in _disp.pending_summaries() or []:
        s = str((t or {}).get("sheet") or "").strip()
        if s and s not in sheets:
            sheets.append(s)
    return sheets


def for_turn(heard: str) -> str:
    """`line` over the live errands' sheets — the first that owes a sentence. Never raises."""
    if "?" not in str(heard or ""):
        return ""
    try:
        from widgets.results import data as _sheet
        for sheet in _live_sheets():
            out = line(heard, _sheet.view_data(sheet) or {})
            if out:
                return out
    except Exception as e:  # noqa: BLE001 — a sheet that cannot be read leaves the reply as the model wrote it
        from voice.observer import emit
        emit("rail", "row_check: sheet unreadable", text=f"{type(e).__name__}: {e}"[:160], role="system")
    return ""
