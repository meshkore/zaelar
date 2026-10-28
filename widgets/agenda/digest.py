#
# Agenda widget — the text views of the card that are not the contract: the line the operator HEARS
# (`_spoken`), the coach context and today's block for the turn prompt. Moved out of `data.py`
# (refactor2710-12 T-03); `data.py` re-exports every name here. State (`load_db`, `_today`, `view_data`) is
# read back through `data` so a test that patches it there still reaches these functions.
#
from . import recur


def _spoken(field: str) -> str:
    """A line the operator HEARS, read from the language table instead of written here (V2-689).

    His rule, and V2-676's receipt: every text the operator can hear or read lives in ONE place that gets
    translated when the agent is initialised in a language. A hardcoded Spanish refusal is a defect for
    every operator who is not speaking Spanish — and an `_en` ternary is the same defect for the third
    language, which is why this reads the TABLE and never a two-way branch.

    Fail-safe: an unreadable table falls back to the field's own default, which is the Castilian text that
    used to be inline. A refusal the operator cannot hear is worse than one in the wrong language."""
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
    """TODAY's meetings as ONE compact block for the turn prompt, whether or not the card is open (V2-668b).

    Measured live (2026-09-11, 11:33, the very re-run of the Hacienda incident): with the agenda CLOSED, the
    STATE carried a memory pill the processor had distilled from the conversation — «cita con la agencia
    tributaria… a las 11:00» — while this widget held 11:30, and the model answered the pill without calling
    `read_widget`, which it had been offered. A widget-owned fact asserted by a recollection outranks the widget
    for a model, because the recollection is IN the prompt and the widget is a tool call away. So the one
    calendar everybody asks about every day rides in the state, and the block says who wins when they disagree.
    Only when there IS something today or tomorrow (an empty pair costs nothing); the header names the precedence.
    Demo pass 110, Z1: «what's on my plate tomorrow» was answered with TODAY's rows — the only day the block carried
    — so tomorrow rides too, and every day is named by its DATE rather than left for the model to place."""
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
