# Session e373d39c (2026-09-18): the operator asked five times to download a film whose release was
# an .mkv, and `search`/`add_magnet` on the torrent widget refused every time with «es un .mkv y el
# navegador no lo reproduce». A torrent client downloads; only `open` (route to a player) may judge
# playability. These tests pin the split: download actions default to keep, `open` still refuses.
from __future__ import annotations

import widgets.torrent.data as tdata


class _FakeService:
    def __init__(self):
        self.calls = []

    def search_and_play(self, query, *, keep=False):
        self.calls.append(("search", query, keep))
        return {"ok": True, "id": "rid1", "title": query}

    def add_magnet(self, magnet, *, keep=False):
        self.calls.append(("add", magnet, keep))
        return {"ok": True, "id": "rid1"}

    def status(self, rid):
        return {"ok": True, "id": rid, "kind": "video", "playable": False,
                "file_name": "Disclosure.Day.2026.2160p.UHD.BluRay.REMUX.DV.P7.HDR.MULTi[Ben.The.Men].mkv",
                "name": "Disclosure Day 2026", "progress": 0.5, "state": "downloading"}

    def active(self):
        return []

    def available(self):
        return True


def _patched(monkeypatch):
    fake = _FakeService()
    monkeypatch.setattr(tdata, "_svc", lambda: fake)
    return fake


def test_search_downloads_any_format_by_default(monkeypatch):
    """The incident: `search` without keep refused the .mkv. The widget downloads first."""
    fake = _patched(monkeypatch)
    res = tdata.apply_action("search", {"query": "Disclosure Day 2026"})
    assert res["ok"] is True
    assert fake.calls == [("search", "Disclosure Day 2026", True)]


def test_add_magnet_downloads_any_format_by_default(monkeypatch):
    """Same split for a pasted magnet link (the MeshCore agent's MacNet output)."""
    fake = _patched(monkeypatch)
    res = tdata.apply_action("add_magnet", {"magnet": "magnet:?xt=urn:btih:ABC"})
    assert res["ok"] is True
    assert fake.calls == [("add", "magnet:?xt=urn:btih:ABC", True)]


def test_an_explicit_keep_false_is_still_respected(monkeypatch):
    """The override survives: passing keep=false keeps the old playable-only refusal path."""
    fake = _patched(monkeypatch)
    tdata.apply_action("search", {"query": "something", "keep": False})
    assert fake.calls == [("search", "something", False)]


def test_open_still_refuses_an_unplayable_mkv(monkeypatch):
    """The other half of the split: routing an .mkv row to a player still refuses with the way round."""
    _patched(monkeypatch)
    res = tdata.apply_action("open", {"id": "rid1"})
    assert res["ok"] is False
    assert ".mkv" in res["error"]
