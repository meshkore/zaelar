"""Every push through the results sheet's door is ONE event with its counts (V2-837 G10).

`landed` was recorded; why the rest did not land travelled only for the category gate and a correction, so «the
worker found 30 cars and the sheet shows 3» could not be read off the record. Every `present`/`append` now emits one
`widget door` event: handed, landed, the gate that turned each row away (`off`), rows filed as pages (`candidacy`),
copies (`dedupe`), rows past the cap and candidates kept in the pool.

Disarm: drop `push.done(...)` from `actions._a_append` → the append case goes red; drop `_tag(off, 0, "category")` in
`search/row_fit.split` → the per-gate case goes red.
"""
from __future__ import annotations

import pytest

from widgets.results import data as sheet

CAR = "Búscame un coche de segunda mano diésel de menos de 12 mil euros"


@pytest.fixture
def doors(monkeypatch):
    from voice import observer
    got = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: got.append(
        dict(extra or {}, _label=label, _kind=kind)) if label == "door" else None)
    return got


def test_an_append_says_what_landed_and_why_the_rest_did_not(doors):
    s = "t-v837-door-a"
    sheet.apply_action("present", {"sheet": s, "title": CAR, "items": [
        {"title": "Peugeot 3008 1.6 BlueHDi", "price": "11.500 €", "url": "https://cars.example/1"}]})
    doors.clear()
    sheet.apply_action("append", {"sheet": s, "items": [
        {"title": "Peugeot 3008 1.6 BlueHDi", "price": "11.500 €", "url": "https://cars.example/1"},    # a copy
        {"title": "Opel Insignia 1.5 dci", "price": "10.900 €", "url": "https://cars.example/2"},        # lands
        {"title": "Guardabarros delantero derecho Seat Ibiza", "price": "45 €", "url": "https://cars.example/p"},
    ]})
    (ev,) = doors
    assert ev["_kind"] == "widget" and ev["action"] == "append" and ev["handed"] == 3 and ev["landed"] == 1, ev
    assert sum((ev.get("off") or {}).values()) + ev.get("dedupe", 0) + ev.get("candidacy", 0) == 2, ev


def test_the_off_rows_are_counted_by_the_gate_that_turned_them_away(doors):
    sheet.apply_action("present", {"sheet": "t-v837-door-b", "title": CAR, "items": [
        {"title": "Fiat Tipo 1.6 diésel", "price": "9.800 €", "url": "https://cars.example/f"},
        {"title": "piezas de coches de segunda mano", "url": "https://cars.example/parts"},
        {"title": "Locomotora American Flyer Comet", "price": "120 €", "url": "https://cars.example/t"}]})
    (ev,) = doors
    assert ev["action"] == "present" and ev["handed"] == 3 and ev["landed"] >= 1
    off = ev.get("off") or {}
    assert off and all(k in ("category", "route", "ceiling", "place", "spec") for k in off), off
    assert ev["landed"] + sum(off.values()) + ev.get("candidacy", 0) == 3, ev
