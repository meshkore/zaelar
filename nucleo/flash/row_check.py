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

#: At most this many named rows are read back: past three it stops being an answer and becomes a list.
_MAX_ROWS = 3
_MAX_ROW_CHARS = 40


def _short(item: dict) -> str:
    t = " ".join(str(item.get("title") or "").split()).rstrip("…")
    return t if len(t) <= _MAX_ROW_CHARS else t[:_MAX_ROW_CHARS - 1].rstrip() + "…"


def line(heard: str, data: dict, reply: str = "") -> str:
    """The sentence the sheet `data` owes to his sentence `heard`. "" when it owes none.

    2026-10-14 (cheapest-monitor ES): read clause by clause (`row_ask`) — a clause that names a row is answered with
    what that row carries about what the clause asks: its hard-requirement fact, another fact of the row whose label
    is the thing asked, or — when the turn's `reply` leaves that row unsaid — «not verified». Never the criteria
    block. A row whose reply speaks of it, or a call with no reply, gets no «not verified»: the row's price or
    title may be the very answer, and the reply is the one reading them."""
    from widgets.results import hard_checks as H
    from . import row_ask as RA
    if "?" not in str(heard or ""):
        return ""
    items = [i for i in ((data or {}).get("items") or [])
             if isinstance(i, dict) and i.get("title") and not RA.is_lead(i)]
    if not items:
        return ""
    hard = H.hard_of(data)
    from i18n import langs as _lg
    lang = _lg.current_language()

    def _say(item, crit) -> str:
        f = H.fact_for(item, crit)
        verdict, source = H.status((f or {}).get("value"))
        if verdict in (H.YES, H.NO):
            said = lang.row_check_yes if verdict == H.YES else lang.row_check_no
            return said.format(source=source) if source else said.split(" (")[0]   # no source: the bare word
        return lang.row_check_unknown

    pairs = RA.asks(heard, items)
    if pairs:
        in_reply = RA.named_in(reply, items) if reply else []
        parts = []
        for item, about in pairs[:_MAX_ROWS]:
            crits = [c for c in hard if RA.content_stems(c) & about]
            if crits:
                parts += [f"{_short(item)}: {crit}, {_say(item, crit)}" for crit in crits]
                continue
            fact = RA.fact_asked(item, about)
            if fact:
                parts.append(f"{_short(item)}: {fact.get('label')} — {fact.get('value')}")
            elif reply and all(item is not r for r in in_reply):   # a reply that left the row unsaid
                parts.append(lang.row_check_row_unknown.format(row=_short(item)))
        return ("; ".join(parts) + ".") if parts else ""
    about = set().union(*(RA.content_stems(c) for c in RA.clauses(heard) if "?" in c))
    asked = [c for c in hard if RA.content_stems(c) & about]
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


def for_turn(heard: str, reply: str = "") -> str:
    """`line` over the live errands' sheets — the first that owes a sentence. Never raises."""
    if "?" not in str(heard or ""):
        return ""
    try:
        from widgets.results import data as _sheet
        for sheet in _live_sheets():
            out = line(heard, _sheet.view_data(sheet) or {}, reply)
            if out:
                return out
    except Exception as e:  # noqa: BLE001 — a sheet that cannot be read leaves the reply as the model wrote it
        from voice.observer import emit
        emit("rail", "row_check: sheet unreadable", text=f"{type(e).__name__}: {e}"[:160], role="system")
    return ""
