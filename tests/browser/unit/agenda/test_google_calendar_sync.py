"""V2-679 — the agenda writes THROUGH to Google Calendar once connected, and the background tick pulls it back.

The operator's own acceptance test: "dicto una cita por voz y en segundos está en el Google Calendar real, y
si yo añado algo desde el móvil, en diez segundos ya lo veo en mi agenda". Neither half is testable by reading
`connectors/calendar/service.py` in isolation — the CONTRACT between it and `widgets/agenda/data.py` is what
this file pins: `_commit_meeting` calls `create_event` before appending, `_patch_google`/`_delete_google` mirror
an edit/cancel onto a Google-origin meeting, `tick` schedules a local reminder for a freshly-synced event, and
`on_calendar_connected` migrates pre-existing LOCAL meetings up without duplicating what Google already has.

A Google failure must never lose the LOCAL write — the same rule `_schedule_reminder` already follows.
"""
from __future__ import annotations

import pytest

from widgets.agenda import data as ag
from widgets.agenda import gcal as ag_gcal


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    return ag


class _FakeSvc:
    """A minimal stand-in for `connectors.calendar.service` — only the functions `data.py` actually calls."""
    def __init__(self, connected=True, create_ok=True, patch_ok=True, sync_result=None):
        self._connected = connected
        self._create_ok = create_ok
        self._patch_ok = patch_ok
        self._sync_result = sync_result or {"ok": True, "changed": False, "new_ids": [], "removed_ids": []}
        self.calls = []

    def connected(self, *a, **k):
        return self._connected

    def create_event(self, meeting, calendar_id=""):
        self.calls.append(("create", dict(meeting), calendar_id))
        if not self._create_ok:
            return {"ok": False, "error": "boom"}
        enriched = dict(meeting)
        enriched.update({"source": "google", "googleId": "g-" + str(meeting.get("title")),
                         "googleCalendarId": calendar_id or "primary", "googleUpdated": "u1"})
        return {"ok": True, "meeting": enriched}

    def patch_event(self, meeting, changes):
        self.calls.append(("patch", dict(meeting), dict(changes)))
        if not self._patch_ok:
            return {"ok": False, "error": "boom"}
        out = dict(meeting)
        out["googleUpdated"] = "u2"
        return {"ok": True, "meeting": out}

    def delete_event(self, meeting):
        self.calls.append(("delete", dict(meeting)))
        return {"ok": True}

    def sync(self, db):
        self.calls.append(("sync", None))
        return self._sync_result


def _use_svc(agenda, monkeypatch, svc):
    monkeypatch.setattr(ag_gcal, "svc", lambda: svc)
    return svc


# ── add_meeting writes THROUGH when connected ───────────────────────────────────────────────────────────────
def test_add_meeting_stays_local_only_when_not_connected(agenda, monkeypatch):
    _use_svc(agenda, monkeypatch, _FakeSvc(connected=False))
    r = agenda.apply_action("add_meeting", {"title": "Dentista", "date": "2026-09-20", "startTime": "10:00"})
    m = r["meetings"][0]
    assert "source" not in m and "googleId" not in m


def test_add_meeting_creates_on_google_first_when_connected(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    r = agenda.apply_action("add_meeting", {"title": "Dentista", "date": "2026-09-20", "startTime": "10:00"})
    m = r["meetings"][0]
    assert m["source"] == "google" and m["googleId"] == "g-Dentista"
    assert svc.calls[0][0] == "create"


def test_add_meeting_keeps_the_reminder_across_the_google_enrichment(agenda, monkeypatch):
    _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    r = agenda.apply_action("add_meeting", {"title": "Reunión", "date": "2026-09-20", "startTime": "23:59"})
    m = r["meetings"][0]
    # a reminder is scheduled for a real future instant; here it may or may not land depending on the clock,
    # but the FIELD must survive the enrichment either way — check the mechanism, not the scheduler's verdict.
    assert m.get("source") == "google"
    assert ("reminder_id" in m) == ("reminder_id" in agenda.load_db()["meetings"][0])


def test_a_google_failure_never_loses_the_local_write(agenda, monkeypatch):
    _use_svc(agenda, monkeypatch, _FakeSvc(connected=True, create_ok=False))
    r = agenda.apply_action("add_meeting", {"title": "Dentista", "date": "2026-09-20", "startTime": "10:00"})
    m = r["meetings"][0]
    assert m["title"] == "Dentista" and "source" not in m   # fell back to the plain local write


def test_a_raised_network_exception_never_loses_the_local_write_either(agenda, monkeypatch):
    """The failure-dict path above and an outright exception (a real timeout, a raised httpx error) are TWO
    different risks — a fake that returns {"ok": False} never exercises the try/except that guards a genuine
    raise. Disarmed: removing that try/except makes THIS one crash the turn while the one above stays green."""
    class _RaisingSvc(_FakeSvc):
        def create_event(self, meeting, calendar_id=""):
            raise RuntimeError("network exploded")
    _use_svc(agenda, monkeypatch, _RaisingSvc(connected=True))
    r = agenda.apply_action("add_meeting", {"title": "Dentista", "date": "2026-09-20", "startTime": "10:00"})
    assert r["meetings"][0]["title"] == "Dentista" and "source" not in r["meetings"][0]


def test_allday_twin_settlement_patches_google_when_the_twin_is_a_google_row(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    agenda.apply_action("add_meeting", {"title": "Cita Hacienda", "date": "2026-09-20"})   # all-day, no hour
    db = agenda.load_db()
    db["meetings"][0]["source"] = "google"       # pretend the all-day promise-backstop row is a Google event
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    r = agenda.apply_action("add_meeting", {"title": "Cita Hacienda", "date": "2026-09-20", "startTime": "11:30"})
    assert len(r["meetings"]) == 1                # settled in place, not a second row
    assert any(c[0] == "patch" for c in svc.calls)


# ── cancel/move/update mirror onto Google when the meeting came from there ─────────────────────────────────
def test_cancel_meeting_deletes_the_google_event_too(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    db = agenda.load_db()
    db.setdefault("meetings", []).append({"title": "Dentista", "date": "2026-09-20", "startTime": "10:00",
                                          "source": "google", "googleId": "g1", "googleCalendarId": "primary"})
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    agenda.apply_action("cancel_meeting", {"title": "Dentista"})
    assert any(c[0] == "delete" for c in svc.calls)
    assert agenda.load_db()["meetings"] == []


def test_move_meeting_patches_the_google_event(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    db = agenda.load_db()
    db.setdefault("meetings", []).append({"title": "Dentista", "date": "2026-09-20", "startTime": "10:00",
                                          "endTime": "11:00", "source": "google", "googleId": "g1",
                                          "googleCalendarId": "primary"})
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    r = agenda.apply_action("move_meeting", {"title": "Dentista", "newDate": "2026-09-21"})
    assert any(c[0] == "patch" for c in svc.calls)
    assert r["meetings"][0]["date"] == "2026-09-21"


def test_update_meeting_patches_the_google_event(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    db = agenda.load_db()
    db.setdefault("meetings", []).append({"title": "Dentista", "date": "2026-09-20", "startTime": "10:00",
                                          "source": "google", "googleId": "g1", "googleCalendarId": "primary"})
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    agenda.apply_action("update_meeting", {"title": "Dentista", "location": "Clínica Ruiz"})
    assert any(c[0] == "patch" for c in svc.calls)


def test_a_local_only_meeting_never_touches_google_on_edit(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    db = agenda.load_db()
    db.setdefault("meetings", []).append({"title": "Cumple", "date": "2026-09-20", "startTime": "10:00"})
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    agenda.apply_action("update_meeting", {"title": "Cumple", "location": "Casa"})
    assert svc.calls == []   # no source=google -> no network call attempted


# ── background tick ──────────────────────────────────────────────────────────────────────────────────────
def test_tick_does_nothing_when_not_connected(agenda, monkeypatch):
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=False))
    calls = {"saved": False}
    class _Ctx:
        def save(self, data):
            calls["saved"] = True
    agenda.tick(_Ctx())
    assert svc.calls == [] and calls["saved"] is False


def test_tick_schedules_a_reminder_for_a_fresh_google_event_and_saves(agenda, monkeypatch):
    db = agenda.load_db()
    db["meetings"] = [{"title": "Reunión", "date": "2099-01-01", "startTime": "09:00", "source": "google",
                       "googleId": "g1", "googleCalendarId": "primary"}]
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    _use_svc(agenda, monkeypatch, _FakeSvc(connected=True,
             sync_result={"ok": True, "changed": True, "new_ids": ["g1"], "removed_ids": []}))
    saved = {}
    class _Ctx:
        def save(self, data):
            saved["db"] = data
    agenda.tick(_Ctx())
    assert "db" in saved
    m = saved["db"]["meetings"][0]
    assert m.get("reminder_id"), "a freshly-synced timed event should get a scheduled reminder"


def test_tick_saves_nothing_when_sync_reports_no_change(agenda, monkeypatch):
    _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))   # default sync_result: changed=False
    saved = {"called": False}
    class _Ctx:
        def save(self, data):
            saved["called"] = True
    agenda.tick(_Ctx())
    assert saved["called"] is False


# ── on_calendar_connected: migrate local meetings, skip past ones and google-duplicates ────────────────────
def test_on_calendar_connected_migrates_future_local_meetings(agenda, monkeypatch):
    db = agenda.load_db()
    db["meetings"] = [{"title": "Dentista", "date": "2099-01-01", "startTime": "10:00"}]
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    agenda.on_calendar_connected()
    m = agenda.load_db()["meetings"][0]
    assert m["source"] == "google" and any(c[0] == "create" for c in svc.calls)


def test_on_calendar_connected_never_pushes_a_meeting_google_already_has(agenda, monkeypatch):
    db = agenda.load_db()
    db["meetings"] = [{"title": "Dentista", "date": "2099-01-01", "startTime": "10:00"}]
    from widgets import store
    store.save(agenda.WIDGET_ID, db)

    def _sync_seeds_a_matching_google_event(dbarg):
        dbarg["meetings"].append({"title": "Dentista", "date": "2099-01-01", "source": "google",
                                  "googleId": "g1", "googleCalendarId": "primary"})
        return {"ok": True, "changed": True, "new_ids": ["g1"], "removed_ids": []}
    svc = _FakeSvc(connected=True)
    svc.sync = _sync_seeds_a_matching_google_event
    monkeypatch.setattr(ag_gcal, "svc", lambda: svc)
    agenda.on_calendar_connected()
    kept = agenda.load_db()["meetings"]
    assert len(kept) == 2                                  # the local row is KEPT, not duplicated on Google
    assert not any(c[0] == "create" for c in svc.calls)


def test_on_calendar_connected_never_migrates_a_past_meeting(agenda, monkeypatch):
    db = agenda.load_db()
    db["meetings"] = [{"title": "Cosa vieja", "date": "2020-01-01", "startTime": "10:00"}]
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    svc = _use_svc(agenda, monkeypatch, _FakeSvc(connected=True))
    agenda.on_calendar_connected()
    m = agenda.load_db()["meetings"][0]
    assert "source" not in m and not any(c[0] == "create" for c in svc.calls)
