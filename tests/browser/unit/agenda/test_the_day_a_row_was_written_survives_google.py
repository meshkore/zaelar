"""V2-722 — the `created` stamp survives the Google write, so an errand can close by being ACHIEVED.

`commit_meeting` has stamped the day a row was written since V2-692, and its own docstring says why it is
not decoration: it is the only thing that tells a row this engine just created from one the operator has had
in his calendar for weeks, and `nucleo/errands/verify.meeting_exists` is written against it.

For a CONNECTED operator it never survived. When Google accepts the event, the row is replaced by Google's
enriched version and only `reminder_id`/`remindAt` were carried across — so the stamp was dropped on exactly
the path the operator's own engine takes. Measured 2026-09-18 on his store: 0 of 71 meetings carried one.
The consequence is not cosmetic: `meeting_exists` skips any row without the stamp, so it could only ever
answer False, NO errand in this house could close by being achieved, and every one of them ran to its
deadline and died «abandoned» a day later. Two were still sitting on his process bar as `running`, twelve
hours after the meeting they announced had already happened — which is what he reported:

> «los del IVAN se quedaron running y eso no es correcto»
"""
from __future__ import annotations

import time

import pytest

from widgets import store
from widgets.agenda import gcal


class _Connected:
    """Google accepting the event and answering with ITS shape — which is what drops fields."""

    def connected(self):
        return True

    def create_event(self, m, cal):
        return {"ok": True, "meeting": {"title": m.get("title"), "date": m.get("date"),
                                        "startTime": m.get("startTime"), "endTime": m.get("endTime"),
                                        "source": "google", "googleId": "gid-1",
                                        "googleCalendarId": "x@y.com", "status": "confirmed"}}


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})


def test_a_row_google_accepted_still_says_when_we_wrote_it(isolated, monkeypatch):
    monkeypatch.setattr(gcal, "svc", lambda: _Connected())
    db = {"meetings": []}
    m = gcal.commit_meeting(db, {"title": "Call with Ivan", "date": "2026-09-18", "startTime": "10:00",
                                 "reminder_id": "j1", "remindAt": "2026-09-18 08:00"})
    assert m["googleId"] == "gid-1"                      # it IS the enriched row…
    assert m["created"] == time.strftime("%Y-%m-%d")     # …and it kept the stamp
    assert m["reminder_id"] == "j1"                      # the two that already travelled still do
    assert db["meetings"][0]["created"] == m["created"]


def test_the_stamp_is_also_there_with_no_google_at_all(isolated, monkeypatch):
    monkeypatch.setattr(gcal, "svc", lambda: None)
    db = {"meetings": []}
    m = gcal.commit_meeting(db, {"title": "Dentist", "date": "2026-09-18", "startTime": "17:00"})
    assert m["created"] == time.strftime("%Y-%m-%d")


def test_a_caller_that_brings_its_own_stamp_keeps_it(isolated, monkeypatch):
    """`setdefault`, not overwrite: a row rehydrated from somewhere else keeps the day it was really born."""
    monkeypatch.setattr(gcal, "svc", lambda: _Connected())
    m = gcal.commit_meeting({"meetings": []}, {"title": "Old one", "date": "2026-09-18",
                                              "startTime": "09:00", "created": "2026-09-01"})
    assert m["created"] == "2026-09-01"


def test_the_verifier_can_now_answer_yes_at_all(isolated, monkeypatch):
    """The whole point, end to end: with the stamp present an errand's `done_when` can finally be MET, so
    it closes by achievement instead of by running out of time."""
    from nucleo.errands import verify
    monkeypatch.setattr(gcal, "svc", lambda: _Connected())
    db = {"meetings": []}
    gcal.commit_meeting(db, {"title": "Call with Ivan", "date": time.strftime("%Y-%m-%d"),
                             "startTime": "10:00"})
    monkeypatch.setattr(verify, "_agenda_rows", lambda: db["meetings"])
    now = time.time()
    errand = {"created_at": now - 600, "deadline": now + 3600,
              "done_when": {"widget": "agenda", "has": "meeting", "within": "window"}}
    assert verify.check(errand, now) is True


def test_a_row_the_operator_already_had_still_closes_nothing(isolated, monkeypatch):
    """The half that must NOT loosen (V2-684): an errand is not closed by an appointment that was already
    in the calendar before it was born — that incident announced «hecha y verificada» over his own
    «Cinema with Mary»."""
    from nucleo.errands import verify
    now = time.time()
    old = {"title": "Cinema with Mary", "date": time.strftime("%Y-%m-%d"), "startTime": "20:00",
           "created": "2026-08-01"}
    monkeypatch.setattr(verify, "_agenda_rows", lambda: [old])
    errand = {"created_at": now - 600, "deadline": now + 3600,
              "done_when": {"widget": "agenda", "has": "meeting", "within": "window"}}
    assert verify.check(errand, now) is False
