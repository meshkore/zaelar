"""Two copies of one event are one thing to LOOK at — never a question (demo pass 135, R2, 2026-10-15).

«when does anna's vacation start? show me in the calendar»: the model answered «December 20» and called
`open_meeting`, and the reply became «Which one exactly? I have Anna vacation (appointment 2026-12-20), Anna vacation
(appointment 2026-12-20 00:00 · every day until …)» — two copies of the same event in his calendar. A lens over rows
that all carry one name opens the best one; an act that writes, or rows with different names, still ask.
"""
from widgets import refs

ROWS = [{"id": "m1", "label": "Anna vacation", "field": "title", "hint": "appointment 2026-12-20"},
        {"id": "m2", "label": "Anna vacation", "field": "title", "hint": "appointment 2026-12-20 00:00 · every day"},
        {"id": "m3", "label": "Dentist", "field": "title", "hint": "appointment 2026-12-29 17:00"}]


def _resolve(monkeypatch, action, ref, rows=ROWS):
    monkeypatch.setattr(refs, "_ref_index", lambda wid: rows)
    monkeypatch.setattr(refs, "id_field_for_action", lambda wid, a: "title", raising=False)
    return refs.resolve("agenda", action, ref, {})


def test_a_lens_over_two_copies_of_one_event_opens_one(monkeypatch):
    r = _resolve(monkeypatch, "open_meeting", "Anna vacation")
    assert r.ok and r.payload.get("title") in ("m1", "m2"), (r.ok, r.needs, getattr(r, "candidates", None))


def test_an_act_that_writes_over_the_same_copies_still_asks(monkeypatch):
    r = _resolve(monkeypatch, "cancel_meeting", "Anna vacation")
    assert not r.ok and r.needs == "ambiguous"


def test_a_lens_over_rows_with_different_names_still_asks(monkeypatch):
    rows = [{"id": "a", "label": "Lunch with Laura", "field": "title", "hint": ""},
            {"id": "b", "label": "Lunch with Lars", "field": "title", "hint": ""}]
    r = _resolve(monkeypatch, "open_meeting", "lunch with la", rows)
    assert r.ok is False or r.payload.get("title") in ("a", "b")
    assert refs._one_name_lens("agenda", "open_meeting", rows) is False
