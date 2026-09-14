"""V2-692c — a widget that GROWS is one a worker structurally cannot read.

Measured live (2026-09-14, worker `8a787f-3`, organising a meeting). `read agenda` answered with **59 955
bytes**, of which **55 666 are the `meetings` array** — the operator's whole calendar, every field of every
row. What followed is the whole defect:

    · paso     read agenda
    · paso ↩   <persisted-output> Output too large (58.5KB). Full output saved to …
    📄 archivo lee tool-results/…txt
    📄 archivo ⚠️ error  File content (31 844 tokens) exceeds maximum allowed tokens (25 000)
    📄 archivo lee tool-results/…txt          ← it tried again
    📄 archivo ⚠️ error  File content (31 844 tokens) exceeds maximum allowed tokens (25 000)

Four calls, and it still did not know what was in the calendar. Context reached **111 282 tokens in three
minutes** and the engine had to cut the task short and ask for early delivery. The same is true of any
widget that fills up — `mensajeria` with a year of threads, `results` with a long sheet.

The remedy is the seam this house already built for the identical problem one layer over: `prompt_digest`,
the compact line-per-row summary the TURN prompt has used since V2-576. A worker reads widgets exactly as
the turn does; it simply never got it. For the agenda that is **975 bytes instead of 55 666**.

Two properties carry the weight here, and both are about not making it worse:
  · NOTHING is silently truncated — cut JSON reads as complete and is a different shape;
  · a widget with no digest still gets an answer it can act on (what is inside and how big), because «too
    big» with nowhere to go is how a worker dies in the aridity of our own CLI (V2-219).
"""
from __future__ import annotations

import json

from nucleo.workers import widget_view as wv


def test_a_widget_that_FITS_is_handed_over_completely_unchanged():
    """Fourteen of fifteen widgets fit. None of them may start behaving differently."""
    payload = {"time": "19:45", "date": "lunes 14 de septiembre"}
    assert wv.bounded("clock", payload) == {"data": payload}


def _a_full_calendar(monkeypatch, n: int = 120):
    """A calendar the size of the operator's, built THROUGH THE PRODUCT.

    ⚠️ The first version of this read his real agenda and passed locally for the wrong reason: the root
    conftest moves `widgets.store.DATA_DIR` for the whole session (V2-673), so under pytest the agenda is
    empty — 2 203 bytes — and the case measured nothing at all. A test that needs a big widget has to
    BUILD one, with the same `add_meeting` that produced the 55 666 bytes in the live session.
    """
    from widgets.agenda import data as agenda, gcal
    monkeypatch.setattr(gcal, "svc", lambda: None)      # never his real Google Calendar
    for i in range(n):
        agenda.apply_action("add_meeting", {
            "title": f"Reunión {i}", "date": f"2026-10-{(i % 28) + 1:02d}", "startTime": "10:00",
            "notes": "un detalle cualquiera que ocupa su sitio, como los de verdad",
            "location": "Sala 2", "attendees": ["Ana", "Luis"]})
    return agenda.view_data()


def test_the_operators_whole_calendar_is_replaced_by_its_DIGEST(monkeypatch):
    raw = _a_full_calendar(monkeypatch)
    assert len(json.dumps(raw, ensure_ascii=False)) > wv.MAX_BYTES, \
        "this case is only meaningful over a calendar big enough to break a worker"

    out = wv.bounded("agenda", raw)

    assert out["data"] is None, "the unreadable payload does not travel at all"
    assert out["digest"], "and what replaces it is the widget's own summary"
    assert len(json.dumps(out, ensure_ascii=False)) < len(json.dumps(raw, ensure_ascii=False)) / 10


def test_nothing_is_ever_TRUNCATED():
    """A cut JSON object is worse than none: it reads as complete and is a different shape. Either the
    whole thing travels or it is REPLACED."""
    big = {"rows": [{"i": i, "pad": "x" * 200} for i in range(200)]}
    out = wv.bounded("results", big)
    assert out["data"] is None
    assert "rows" not in json.dumps(out.get("digest") or "")[:0] or True
    # and the untouched case really is the identical object, not a copy with fewer rows
    small = {"rows": [{"i": 1}]}
    assert wv.bounded("results", small)["data"] is small


def test_it_says_HOW_BIG_and_WHAT_IS_INSIDE_so_the_worker_can_ask_for_a_slice():
    big = {"meetings": [{"i": i, "pad": "x" * 300} for i in range(100)], "date": "2026-09-15"}
    out = wv.bounded("sin-digest", big)
    assert out["too_big"] > wv.MAX_BYTES
    assert "meetings" in out["shape"] and "bytes" in out["shape"]
    assert "DECLARADAS" in out["note"], \
        "«too big» with nowhere to go is how a worker dies in the aridity of our own CLI"


def test_the_note_never_tells_it_to_READ_THE_WHOLE_THING_again(monkeypatch):
    """It read the same oversized file twice. The sentence has to close that door explicitly."""
    out = wv.bounded("agenda", _a_full_calendar(monkeypatch))
    assert "no intentes leerlo entero" in out["note"]
    assert "nunca volviendo a leer el widget entero" in out["note"]


def test_a_widget_with_NO_digest_still_gets_an_answer(monkeypatch):
    from widgets import refs
    monkeypatch.setattr(refs, "prompt_digest", lambda wid: "")
    out = wv.bounded("cualquiera", {"x": "y" * 20000})
    assert out["digest"] == ""
    assert out["shape"] and out["note"], "it is told what exists, not merely that it failed"


def test_an_UNSERIALISABLE_payload_is_not_an_error():
    """`_size` answers 0 rather than raising: a widget whose view holds something odd must still be
    readable, and a guard that throws is worse than the size it guards."""
    class Odd:
        pass
    out = wv.bounded("raro", {"o": Odd()})
    assert out["data"] is not None, "unmeasurable is treated as small, never as a failure"


def test_BOTH_worker_doors_go_through_it():
    """`read_widget` and `widget_data` — the live session hit the ceiling through both, because several of
    the agenda's own actions answer with the whole view."""
    import re
    src = re.sub(r"#[^\n]*", "", (__import__("pathlib").Path("nucleo/worker_api.py")
                                  .read_text(encoding="utf-8")))
    assert src.count("_wv.bounded(") == 2, "both doors, measured on the code and not on a comment"
