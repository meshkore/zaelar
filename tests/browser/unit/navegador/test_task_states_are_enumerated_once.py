"""Every browser task state belongs to ONE set: live or ended (V2-197).

`active_summaries()` used to filter by `("queued","working","needs_input")` and `recently_finished()` by
`("done","failed")`, each with its own hand-maintained list. **A state that is in neither of the two is a task
that the live state does not mention AT ALL** — neither live nor ended— and so the model continues with the last
thing it knew, which is correct when nobody tells it otherwise.

That gap cost us `cancelled` (V2-196, measured in `find-theatre-tickets__es`: “infinite wait loop on a task
that has already failed”). And as soon as the enumeration moved to one place, it became apparent that **`open`
had always been in the same gap**, set by `owner.py` every time a page is opened FOR the operator: you open
Booking for them, then they ask “do you have it?”, and the state says nothing about that tab.

Two lists that have to be kept in sync are two lists that will not stay in sync. This test prevents that, and it
does not inspect the lists: it inspects the CODE, and fails if someone introduces a state without classifying it.
"""
from __future__ import annotations

import re
from pathlib import Path

from widgets.navegador import tasks

ROOT = Path(__file__).resolve().parents[4]
_SET_STATUS = re.compile(r"set_status\(\s*[^,]+,\s*[\"']([a-z_]+)[\"']")


def _statuses_written_anywhere() -> set[str]:
    found: set[str] = set()
    for d in ("nucleo", "widgets", "voice", "server", "connectors"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            try:
                found |= set(_SET_STATUS.findall(py.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    return found


def test_the_two_sets_do_not_overlap():
    assert not (tasks.LIVE_STATES & tasks.ENDED_STATES)


def test_every_status_the_code_writes_is_classified():
    unclassified = sorted(_statuses_written_anywhere() - tasks.LIVE_STATES - tasks.ENDED_STATES)
    assert not unclassified, (
        f"estados de tarea que no están ni en LIVE_STATES ni en ENDED_STATES: {unclassified}. "
        "Una tarea en ese estado NO aparece en el estado vivo —ni viva ni terminada— y el modelo sigue "
        "contando lo último que supo. Clasifícalo, y si es un final decide cómo se DICE en "
        "`nucleo/flash/prompt.py` (un final que suena igual que otro distinto tampoco sirve).")


def test_open_is_an_ENDED_state_and_says_what_it_is():
    """The one that was in the gap. It is neither a failure nor a result: it is a tab that remains in front of them."""
    from nucleo.flash import prompt as _p

    assert "open" in tasks.ENDED_STATES
    tasks._tasks.clear()
    tid = tasks.create("Abrir Booking")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.booking.com/")
    tasks.set_status(tid, "open")
    try:
        state = _p.live_state()
        assert "está ABIERTA en pantalla" in state
        assert "terminó SIN traer nada" not in state
    finally:
        tasks._tasks.clear()


def test_entering_ANY_ended_state_stamps_when_it_ended():
    """`recently_finished()` filters by a time window, so an ending without a timestamp is an ending that nobody
    can date — and it disappears anyway. The stamp is applied when ENTERING an ending, not by each function separately."""
    for st in sorted(tasks.ENDED_STATES):
        tasks._tasks.clear()
        tid = tasks.create("x")
        tasks.set_status(tid, "working")
        tasks.set_status(tid, st)
        assert tasks.get(tid).get("finished"), f"«{st}» no sella cuándo terminó"
        assert [r["id"] for r in tasks.recently_finished()] == [tid], f"«{st}» no sale como final reciente"
    tasks._tasks.clear()
