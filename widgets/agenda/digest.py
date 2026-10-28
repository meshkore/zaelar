#
# Agenda widget — the text views of the card that are not the contract: the line the operator HEARS
# (`_spoken`), the coach context and today's block for the turn prompt; `data.py` re-exports them. State
# (`load_db`, `_today`, `view_data`) is read through `data` so a test that patches it there reaches these.
#
from . import recur


def _spoken(field: str) -> str:
    """A line the operator HEARS, read from the language table, never a two-way `_en` branch (V2-689).
    Fail-safe: an unreadable table falls back to the field's default — a refusal in the wrong language beats
    one he cannot hear."""
    try:
        from i18n import langs as _langs
        return str(getattr(_langs.spec(), field, "") or "")
    except Exception:  # noqa: BLE001
        from dataclasses import fields as _fields
        try:
            from i18n.langs import LangSpec as _LS
            return str(next(f.default for f in _fields(_LS) if f.name == field))
        except Exception:  # noqa: BLE001
            return ""



def coach_context() -> str:
    """The 'memory seam' (HANDOFF §7 note): mission + workday + projects-by-priority + today's plan + free gaps,
    rendered for the assistant to adopt the COACH role over the agenda."""
    d = _d.view_data()
    db = _d.load_db()
    lines = [f"MISIÓN GLOBAL: {d['mission']}", "", "PROYECTOS (por prioridad):"]
    for p in sorted(db.get("projects", []), key=lambda p: p.get("priority", 5)):
        lines.append(f"- [{p.get('priority')}] {p['name']}: {p.get('objective','')} "
                     f"(valor {p.get('expectedValue')}, prob {p.get('successProbability')}, {p.get('hoursRemaining')}h)")
    lines.append("\nAGENDA DE HOY:")
    for b in d["plan"]["blocks"]:
        lines.append(f"  {b['start']}–{b['end']} · {b['label']} ({b['kind']})")
    if d["active"]:
        lines.append(f"\nAHORA ({d['now']}): {d['active']['label']} · quedan {d['active'].get('remaining_min','?')} min")
    if d["warnings"]:
        lines.append("\nNO CABE HOY: " + " | ".join(d["warnings"]))
    return "\n".join(lines)


def today_line(limit: int = 8) -> str:
    """TODAY's and TOMORROW's meetings as ONE compact block for the turn prompt, open card or not (V2-668b).
    A memory pill in the prompt outranks a widget a tool call away, so the calendar rides in the state and the
    header says the widget WINS a disagreement. Each day is named by its DATE; nothing on either day → ""."""
    try:
        import datetime as _dt
        db = _d.load_db()
        today = _d._today()
        days = [("HOY", today), ("MAÑANA", (_dt.date.fromisoformat(today) + _dt.timedelta(days=1)).isoformat())]
        per = [(label, day, sorted(recur.on_date(db.get("meetings", []), day),
                                   key=lambda m: (bool(not m.get("allDay")), str(m.get("startTime") or ""))))
               for label, day in days]
    except Exception:
        return ""
    if not any(meets for _l, _d, meets in per):
        return ""
    rows = []
    for label, day, meets in per:
        rows.append(f"{label} ({day}):" + ("" if meets else " nada"))
        for m in meets[:limit]:
            if m.get("allDay"):
                when = "todo el día"
            else:
                when = str(m.get("startTime") or "?") + (f"–{m['endTime']}" if m.get("endTime") else "")
            row = f"  {when} · {str(m.get('title') or 'Cita')[:80]}"
            if m.get("location"):
                row += f" · {str(m['location'])[:40]}"
            rows.append(row)
        if len(meets) > limit:
            rows.append(f"  … y {len(meets) - limit} más (read_widget agenda)")
    return ("AGENDA — lo que GUARDA el widget agenda; si un recuerdo dice otra hora u otro día, MANDA esto "
            "(para otro día o más detalle: read_widget):\n" + "\n".join(rows))


from widgets.agenda import data as _d  # noqa: E402 — the facade, read at call time
