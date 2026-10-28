"""A stopped errand leaves no «Working…» behind, and a complaint about a close is no close (demo 2026-10-22).

The trip plan was cancelled while it waited for a slot: the cancel landed at the pool's door, outside the only
`finally` that closes a sheet, so its card said «Working…» for good, on top of the document he was reading. Then
«You did close the document of Bitcoin without me telling you» was read by the grammar as an order, and the model's
[[close]] closed that document — with the turn's canvas verdict saying `neither` at 0.98.
"""
from __future__ import annotations

from nucleo.acts import canvas as _door

import asyncio
import threading
from types import SimpleNamespace

from nucleo import dispatch, surfaces

from nucleo.dispatch import session as dispatch_session
from nucleo.flash import show_target, turn_brief as _tb

SHEET = sorted(surfaces.SHEET)[0]


def _rec(**kw):
    return SimpleNamespace(surface=SHEET, status="queued", last_event_at=0.0, **kw)


def _wire(monkeypatch, items):
    closed_sheet, events = [], []
    monkeypatch.setattr(dispatch, "_sheet_close", lambda rec: closed_sheet.append(rec))
    monkeypatch.setattr(dispatch, "sheet_of", lambda rec: "48ac70-3")
    from widgets.results import data as _sheet
    monkeypatch.setattr(_sheet, "view_data", lambda sid="": {"items": items})
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: events.append((kind, label, k.get("extra"))))
    return closed_sheet, events


def test_an_empty_sheet_of_an_errand_that_never_ran_stops_and_leaves(monkeypatch):
    closed_sheet, events = _wire(monkeypatch, [])
    dispatch_session._settle_unrun(dispatch, _rec(), "3")
    assert closed_sheet, "the loader was never stopped"
    assert ("widget", "close", {"id": "results::48ac70-3", "src": "worker:3"}) in events


def test_a_sheet_with_rows_stops_its_loader_and_stays(monkeypatch):
    closed_sheet, events = _wire(monkeypatch, [{"title": "a row he may want"}])
    dispatch_session._settle_unrun(dispatch, _rec(), "3")
    assert closed_sheet and not [e for e in events if e[:2] == ("widget", "close")]


def test_a_cancel_while_waiting_for_a_slot_settles_the_sheet(monkeypatch):
    settled: list = []
    monkeypatch.setattr(dispatch_session, "_settle_unrun", lambda _d, rec, key: settled.append(key))
    monkeypatch.setattr(dispatch_session, "_say_queued_behind", lambda _d, key: None)

    async def run():
        monkeypatch.setattr(dispatch, "_sem", asyncio.Semaphore(1))
        await dispatch._pool().acquire()                     # both slots taken

        async def waiter():
            async with dispatch_session._a_slot(dispatch, "3", _rec()):
                pass
        t = asyncio.ensure_future(waiter())
        await asyncio.sleep(0.05)
        t.cancel()                                           # what `cancel_session` does to a queued errand
        try:
            await t
        except asyncio.CancelledError:
            pass
        dispatch._pool().release()
        assert not dispatch._pool().locked(), "the cancelled waiter leaked a slot"
    asyncio.run(run())
    assert settled == ["3"]


def _brief(canvas: str, kind: str = "complaint"):
    """`request_type` rides with `canvas` as in every real brief: since V2-812 T-05 a `neither` vetoes a grammar close
    only when the turn is also read as something other than an order — a complaint, as this one is."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": ["documento"],
            "result": {_tb.CANVAS_KEY: {"choice": canvas, "confidence": 0.98},
                       _tb.REQUEST_KEY: {"choice": kind, "confidence": 0.9}}}


COMPLAINT = "You did close the document of Bitcoin without me telling you, also it seems that ended the trip."


def test_a_complaint_about_a_close_licenses_no_close():
    assert _door.close_ordered(COMPLAINT, brief=_brief("neither"), called=True, handle=None) == (False, "verdict")


def test_an_order_to_close_is_still_one():
    assert _door.close_ordered("Close the calendar.", brief=_brief("close"), called=True, handle=None)[0] is True
    assert _door.close_ordered("Close the calendar.", called=True, handle=None)[0] is True        # no brief: as before
