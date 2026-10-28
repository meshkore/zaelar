"""«Show me the channel of SpaceX» opens the channel's page whether or not he follows it (node 2.913).

Live, 2026-10-28 15:50 (T30–T35): `open_channel` answered «No sigo ese canal» four turns in a row, the correction
(`follow_channel`) was refused as «a different action», and he ended up asking whether this was a feature we lack.
A channel he does not follow is resolved by name on the public channel search and opened; nothing is stored —
following stays his explicit act. A name the search cannot resolve is `not_found`, as before.
"""
from __future__ import annotations

from widgets.youtube import channels


def _db():
    return {"channels": [], "channel_view": {}}


def test_an_unfollowed_channel_resolved_by_name_opens_and_is_not_followed(monkeypatch):
    monkeypatch.setattr(channels, "find", lambda name: {"id": "UCspacex", "title": "SpaceX", "handle": "@SpaceX",
                                                        "avatar": "", "subscribers": 7000000})
    monkeypatch.setattr(channels.store, "save", lambda *_a, **_k: None)
    db = _db()
    r = channels.apply("open_channel", {"channel": "SpaceX"}, db)
    assert r["ok"] is True and r["id"] == "UCspacex" and r["followed"] is False
    assert db["channel_view"]["id"] == "UCspacex" and db["channel_view"]["name"] == "SpaceX"
    assert db["channels"] == []


def test_a_followed_channel_opens_as_before_and_says_so(monkeypatch):
    monkeypatch.setattr(channels, "find", lambda name: (_ for _ in ()).throw(AssertionError("no search for a followed one")))
    monkeypatch.setattr(channels.store, "save", lambda *_a, **_k: None)
    db = {"channels": [{"name": "SpaceX", "id": "UCspacex"}], "channel_view": {}}
    r = channels.apply("open_channel", {"channel": "spacex"}, db)
    assert r["ok"] is True and r["followed"] is True


def test_a_name_the_search_cannot_resolve_is_not_found(monkeypatch):
    monkeypatch.setattr(channels, "find", lambda name: {})
    r = channels.apply("open_channel", {"channel": "zzz nobody"}, _db())
    assert r["ok"] is False and r["error"] == "not_found"
