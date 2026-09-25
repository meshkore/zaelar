"""widgets/agenda/index.py — the TWO views the brain reads of this card, and they must agree.

Extracted from `data.py` under the architecture ratchet (V2-707 F0): the file sat one line under its 900
ceiling and the fix below needed room. The split is not a convenience — these two functions are the whole
of what the agenda tells the brain ABOUT ITSELF, and the defect being fixed was that they DISAGREED.

  · `ref_index()` — what can be NAMED: rows with the payload key that identifies them, so `widgets/refs.py`
    resolves a spoken reference to a real id, and so `widgets/contract.guard` can offer a menu when a
    destructive action arrives with an empty selector.
  · `prompt_digest()` — what is INSIDE, in prose, for every turn's prompt while the card is open.

Measured 2026-09-16 (session cb0ac5da, i=7911): asked to remove a meeting today at five, the operator was
read back «¡Feliz cumpleaños! (cita 2027-08-19); Cristina Sergio Primo Raquel - Cumplea…» — birthdays eleven
months away — because the index handed its rows back in Google-sync order while the digest had always sorted
by (date, hour). The model was holding two views of one calendar that named different things as «next», and
re-emitted the same empty selector. Both sort here now, and a test pins that they return the same order.

`data.py` re-exports both names, so `refs._ref_index` and `refs.prompt_digest` (which import them off the
widget's `data` module by contract) need no change.
"""
from __future__ import annotations



def ref_index() -> list[dict]:
    """Items the brain can reference by voice (V2-026): live tasks (by title) and active projects (by name).
    `field` is the payload key that identifies them in actions (`taskId` for a task, `projectId` for a project),
    so `widgets/refs.py` resolves a spoken task reference to its id without the model guessing it.
    Only current items are exposed; completed/dropped tasks are no longer referenceable."""
    from . import tasklists
    from .data import _today, load_db

    db = load_db()
    # V2-744 — a task is named by its LIST and its NUMBER as often as by its title («la 2 de la compra»),
    # so the rows come from the same function the section renders with. `tasklists.ref_rows` already skips
    # what is done or dropped, which is the rule this index has always had.
    out: list[dict] = list(tasklists.ref_rows(db))
    for p in db.get("projects", []):
        if p.get("status") == "frozen":
            continue
        out.append({"id": p["id"], "label": p.get("name") or p["id"], "field": "projectId", "hint": "proyecto"})
    # V2-639 — meetings are referenceable too («la cita del dentista» -> payload.title), so set_reminder /
    # cancel_meeting / move_meeting resolve a spoken reference without the model re-typing the title. Only
    # today-or-future ones: a past appointment is history, not a target.
    today = _today()
    # V2-707 F0 — SOONEST FIRST. The rows come off the store in Google-sync order, and this index is what
    # `widgets/contract.guard` turns into the menu a refused destructive action offers («which of these?»),
    # capped at the first eight. Measured 2026-09-16 (session cb0ac5da, i=7911): asked to remove a meeting
    # today at five, the operator was read back «¡Feliz cumpleaños! (cita 2027-08-19); Cristina Sergio Primo
    # Raquel - Cumplea…» — birthdays eleven months away, while the two meetings he could have meant were
    # further down the list. The model then re-emitted the same empty selector, because the menu it was
    # handed named nothing it could use. `prompt_digest` has always sorted this way; the index that feeds
    # the REFUSAL never did, so the brain's two views of the same card disagreed on what comes next.
    # V2-769 — a SERIES is named once, by its next day: «el piano» is one thing, not forty Tuesdays.
    from . import recur
    _future = [(recur.next_occurrence(m, today), m) for m in db.get("meetings", [])]
    for nxt, m in sorted(((n, m) for n, m in _future if n), key=lambda t: (t[0], str(t[1].get("startTime") or ""))):
        label = m.get("title") or "Cita"
        _rule = f" · {recur.describe(m['repeat'])}" if isinstance(m.get("repeat"), dict) else ""
        out.append({"id": label, "label": label, "field": "title",
                    "hint": f"cita {nxt} {m.get('startTime', '')}".strip() + _rule})
    return out


def prompt_digest() -> str:
    """What the brain sees while the agenda card is OPEN (`refs.prompt_digest` contract, capped there).

    V2-639 — the operator asks the AGENDA questions («¿qué tengo mañana?», «¿qué es esa cita del
    dentista?») and the model could not answer them: `coach_context` only carries TODAY's plan, so every
    meeting beyond today was invisible and the reply was a guess. Upcoming meetings with their date, hour,
    reminder and notes ARE the interior of this widget — same seam as contactos/fotos (V2-544)."""
    from . import tasklists
    from .data import _today, load_db

    db = load_db()
    today = _today()
    # V2-769 — a SERIES is listed once, at its NEXT day, with its rule said out loud: the model read «una
    # única fecha, la del 1 de octubre» off a row that had no rule, and told him so.
    from . import recur
    _nx = [(recur.next_occurrence(m, today), m) for m in db.get("meetings", [])]
    _nx = sorted(((n, m) for n, m in _nx if n), key=lambda t: (t[0], str(t[1].get("startTime") or "")))
    meets = [m for _n, m in _nx]
    lines: list[str] = []
    for nxt, m in _nx[:12]:
        _hour = "todo el día" if m.get("allDay") else str(m.get("startTime") or "")
        row = f"  · {nxt} {_hour} «{m.get('title', 'Cita')}»"
        if isinstance(m.get("repeat"), dict):
            row += f" · SE REPITE {recur.describe(m['repeat'])} (primera: {m.get('date')})"
        if m.get("location"):
            row += f" en {str(m['location'])[:60]}"
        # V2-643 — who is coming and whether they answered. «¿Cuántos somos el jueves?» and «¿me lo
        # confirmaron?» are questions about THIS card; without these two fields the model had to guess.
        _who = [w for w in (m.get("attendees") or []) if str(w).strip()]
        _n = len(m.get("attendees") or [])
        if _n:
            row += f" · {_n} persona{'s' if _n != 1 else ''}"
            if _who:
                row += f" ({', '.join(_who[:6])})"
        if m.get("status") == "pending":
            row += " · SIN confirmar por la otra parte"
        elif m.get("status") == "confirmed" and _n:
            row += " · confirmada"
        if m.get("remindAt"):
            row += f" (aviso {m['remindAt']})"
        if m.get("notes"):
            row += f" — {str(m['notes'])[:120]}"
        lines.append(row)
    if len(meets) > 12:
        lines.append(f"  · … y {len(meets) - 12} citas más")
    pend = [t for t in db.get("tasks", []) if t.get("status") in (None, "todo", "in_progress")]
    head = f"citas próximas ({len(meets)}) · tareas vivas ({len(pend)}):"
    if not lines:
        lines = ["  · sin citas apuntadas de hoy en adelante"]
    # V2-744 — the TAREAS section is the other half of this card, and a digest that only described the
    # calendar is why «¿qué me falta de la compra?» had to be guessed. Built by `tasklists.digest` from the
    # very numbering the render shows: two views of one card that disagree is the defect this file exists for.
    _tasks = tasklists.digest(db)
    return head + "\n" + "\n".join(lines) + (("\n" + _tasks) if _tasks else "")


