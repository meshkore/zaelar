"""A write the card absorbs into a row it already held is MET by that row, for any card (T-19 R10).

Demo sandbox pass 2: «Vet appointment for Pixel» 16:00 was on the agenda; `add_meeting «Pixel — veterinarian»`
16:00-17:00 ran, the agenda dropped the same-slot duplicate and answered an empty success, the spec over the new title
read unmet and he heard «I couldn't create the calendar event» — while the list said every task was done. The write
now answers `existing: <row>` and the circuit reads that outcome as met, the same one the list's done count reads.
"""
import pytest

from nucleo.circuit import compose as wh
from nucleo.circuit import spec as _spec
from widgets import rows

CASES = [("agenda", "add_meeting", "meetings", "Pixel — veterinarian", {"title": "Vet appointment for Pixel"}),
         ("agenda", "add_meeting", "meetings", "Pixel — veterinario", {"title": "Veterinario de Pixel"}),
         ("contactos", "add_contact", "contacts", "Rowan Example", {"name": "Rowan"})]


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(_spec, "persist", lambda *a, **k: None)
    _spec.reset()
    wh.reset()
    yield
    _spec.reset()
    wh.reset()


@pytest.mark.parametrize("wid,action,coll,title,held", CASES)
def test_an_absorbed_write_meets_its_end_state(monkeypatch, wid, action, coll, title, held):
    monkeypatch.setattr(rows, "_rows", lambda w, c: [dict(held)])
    e = _spec.open({"all": [{"widget": wid, "collection": coll, "where": {"title~": title}}]},
                   text=title, widget=wid, action=action)
    assert _spec.attest(e) is False                          # the new wording is not on the card
    wh.remember(wid, action, title, {"ok": True, "existing": dict(held)})
    assert _spec.attest(e) is True


@pytest.mark.parametrize("res", [{"ok": True}, {"ok": False, "existing": {"title": "x"}}, {"ok": True, "existing": {}}])
def test_only_a_landed_existing_row_meets_it(monkeypatch, res):
    monkeypatch.setattr(rows, "_rows", lambda w, c: [{"title": "Vet appointment for Pixel"}])
    e = _spec.open({"all": [{"widget": "agenda", "collection": "meetings", "where": {"title~": "Pixel — veterinarian"}}]},
                   text="x", widget="agenda", action="add_meeting")
    wh.remember("agenda", "add_meeting", "x", res)
    assert _spec.attest(e) is False
