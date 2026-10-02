"""A mutation the request record already shows is not listed twice (V2-778 F2-19, 2026-10-02).

Two blocks of the live state told the model what had just happened: the request rows («what he asked for lately,
and how each ended», `task_block.recent_lines`) and the done-ops ring (`live_blocks.done_ops_lines`). Every voice or
chat order that changed a card was in BOTH. They are not the same source, though: the ring is written at the widget
funnel and also carries what the operator did with a CLICK, which opens no row — the V2-707 incident («I haven't
deleted anything» over two sweeps) is exactly an act the rows would not show. So the ring keeps listing what no row
shows, and always keeps its two instructions (a destructive act happened; a card that is not on screen).
"""
from __future__ import annotations

import time

import pytest

from nucleo import done_ops as D
from nucleo.flash import live_blocks as LB


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    D.reset()
    monkeypatch.setattr(LB, "_is_open", lambda wid: True)
    yield
    D.reset()


def _rows(monkeypatch, rows):
    from nucleo import tasks as T
    store = T.store()
    monkeypatch.setattr(store, "tasks_where", lambda **k: rows, raising=False)


def test_an_order_the_rows_show_is_not_listed_again(monkeypatch):
    now = time.time()
    _rows(monkeypatch, [{"id": "abcdef-i1", "kind": "inline", "state": "done", "verdict": "met",
                         "outcome": "agenda:move_meeting", "finished_at": now - 5, "started_at": now - 6}])
    D.note("agenda", "move_meeting", {"title": "Dentist"})
    assert LB.done_ops_lines() == [], "the move is already on the request record: once is enough"


def test_a_click_no_row_shows_is_still_said(monkeypatch):
    _rows(monkeypatch, [])
    D.note("agenda", "clear_range", {"date": "2026-10-17"}, n=5, destructive=True)
    lines = LB.done_ops_lines()
    assert lines and "agenda:clear_range" in lines[0] and "TIENE RAZÓN" in lines[0]


def test_a_destructive_order_keeps_its_instruction_even_when_the_rows_show_it(monkeypatch):
    now = time.time()
    _rows(monkeypatch, [{"id": "abcdef-i2", "kind": "inline", "state": "done", "verdict": "met",
                         "outcome": "agenda:clear_range", "finished_at": now - 5, "started_at": now - 6}])
    D.note("agenda", "clear_range", {}, n=4, destructive=True)
    lines = LB.done_ops_lines()
    assert lines and "TIENE RAZÓN" in lines[0], "the rule V2-707 paid for never leaves"
