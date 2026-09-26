"""Two rows with the same name, and a reference that carries the time (demo run, 2026-09-26).

«Move it 30 minutes later» → `move_meeting` with the item «Catch up with Oscar tomorrow September 27 at 16:15»,
over two «Catch up with Oscar» at 15:30 and 16:15. The resolver called it ambiguous although the reference named
the time; and because the agenda card was closed, the provider sent the ambiguity to a Brain Worker. The time
now decides when exactly one tied row's own hint carries it, and an ambiguous reference is a «which one?».
"""
import pathlib
import re

from widgets import refs

ROWS = [{"id": "m1", "label": "Catch up with Oscar", "field": "title", "hint": "cita 2026-09-27 15:30"},
        {"id": "m2", "label": "Catch up with Oscar", "field": "title", "hint": "cita 2026-09-27 16:15"},
        {"id": "m3", "label": "Dentist", "field": "title", "hint": "cita 2026-09-29 17:00"}]


def _resolve(monkeypatch, ref):
    monkeypatch.setattr(refs, "_ref_index", lambda wid: ROWS)
    monkeypatch.setattr(refs, "id_field_for_action", lambda wid, a: "title", raising=False)
    return refs.resolve("agenda", "move_meeting", ref, {})


def test_the_time_in_the_reference_picks_the_row(monkeypatch):
    r = _resolve(monkeypatch, "Catch up with Oscar tomorrow September 27 at 16:15")
    assert r.ok and r.payload.get("title") == "m2", (r.ok, r.needs, getattr(r, "payload", None))


def test_without_a_distinguishing_time_it_still_asks(monkeypatch):
    r = _resolve(monkeypatch, "Catch up with Oscar")
    assert not r.ok and r.needs == "ambiguous"
    r = _resolve(monkeypatch, "Catch up with Oscar on 2026-09-27")        # both rows carry the date
    assert not r.ok and r.needs == "ambiguous", "a token BOTH rows carry decides nothing"


def test_an_ambiguous_reference_is_not_escalated_to_a_worker():
    src = (pathlib.Path(__file__).resolve().parents[4] / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert re.search(r'absent_widget_misroute\(wid, action_name, ref, resolved=res\.ok or res\.needs == "ambiguous"',
                     src), "an ambiguity found in the card's own rows is a question, not an errand"
