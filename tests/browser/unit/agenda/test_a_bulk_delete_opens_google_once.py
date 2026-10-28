"""A bulk delete asks Google with ONE token and ONE client for the whole set; each row still gets its own verdict and
a refused row stays (node 2.918).

175 one-by-one deletes took minutes on 2026-10-28 (a prepared token and a fresh HTTPS client per row).
"""
from __future__ import annotations

from connectors.calendar import service
from widgets.agenda import gcal


def _rows():
    return [{"id": "a", "title": "A", "source": "google", "googleId": "ga", "googleCalendarId": "cal"},
            {"id": "b", "title": "B", "source": "google", "googleId": "gb", "googleCalendarId": "cal"},
            {"id": "c", "title": "C", "source": "google", "googleId": "gc", "googleCalendarId": "cal"},
            {"id": "l", "title": "Local", "date": "2099-01-01"}]


def test_one_token_one_client_one_verdict_per_row(monkeypatch):
    prepared, deleted, closed = [], [], []
    monkeypatch.setattr(service, "_prepared", lambda pid=None: (prepared.append(pid) or
                                                                 (type("P", (), {"api_base": "https://g", "id": "google"})(), "tok", None)))
    import httpx
    monkeypatch.setattr(httpx, "Client", lambda: type("C", (), {"close": lambda self: closed.append(1)})())
    monkeypatch.setattr(service._gc, "delete_event",
                        lambda client, base, tok, cid, gid: deleted.append((tok, cid, gid)) or {"ok": gid != "gb", "error": "no" if gid == "gb" else ""})
    gone, stuck = gcal.delete_many(_rows())
    assert len(prepared) == 1 and closed == [1] and [d[2] for d in deleted] == ["ga", "gb", "gc"]
    assert [m["id"] for m in gone] == ["a", "c", "l"] and [m["id"] for m in stuck] == ["b"]


def test_a_connector_that_is_down_keeps_every_google_row(monkeypatch):
    monkeypatch.setattr(service, "_prepared", lambda pid=None: (None, None, {"ok": False, "error": "no conectado"}))
    gone, stuck = gcal.delete_many(_rows())
    assert [m["id"] for m in gone] == ["l"] and len(stuck) == 3


def test_a_single_delete_still_opens_and_closes_its_own_session(monkeypatch):
    closed = []
    monkeypatch.setattr(service, "_prepared", lambda pid=None: (type("P", (), {"api_base": "https://g", "id": "google"})(), "tok", None))
    import httpx
    monkeypatch.setattr(httpx, "Client", lambda: type("C", (), {"close": lambda self: closed.append(1)})())
    monkeypatch.setattr(service._gc, "delete_event", lambda *a: {"ok": True})
    assert gcal.delete_google(_rows()[0]) is True and closed == [1]
