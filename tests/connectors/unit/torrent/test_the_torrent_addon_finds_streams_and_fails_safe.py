"""The embedded torrent add-on (V2-637): the mesh hands over a magnet, the client streams it, and everything
degrades to words instead of a traceback.

The libtorrent session itself is never touched here — a unit test does not open a real BitTorrent session or
reach the network. What is pinned is everything AROUND it: pulling the magnet out of whatever shape the mesh
agent answers with, the HTTP Range arithmetic a `<video>` depends on, the streamable-gate the widget waits on,
and the fail-safe facade whose `available()` is DERIVED from the wheel being importable.
"""
from __future__ import annotations

import pytest

from connectors.torrent import search, service
from connectors.torrent.server_api import _parse_range


# ── 1 · the magnet is found wherever the agent put it, and absence is honest ────────────────────────────────

_M = "magnet:?xt=urn:btih:2c6b6858d61da9543d4231a71db4b1c9264b0685&dn=x"


def test_first_magnet_reads_every_shape_an_agent_might_answer_with():
    assert search._first_magnet({"magnet": _M}) == _M
    assert search._first_magnet({"magnet_uri": _M}) == _M
    assert search._first_magnet({"results": [{"link": _M}]}) == _M
    assert search._first_magnet(f"top hit: {_M} enjoy") == _M
    assert search._first_magnet([{"a": 1}, {"uri": _M}]) == _M


def test_a_payload_with_no_magnet_yields_empty_not_a_guess():
    assert search._first_magnet({"title": "a movie", "seeders": 40}) == ""
    assert search._first_magnet(None) == ""
    assert search._first_magnet("no link here") == ""


def test_find_magnet_speaks_the_reason_when_the_mesh_has_nobody(monkeypatch):
    monkeypatch.setattr("nucleo.mesh_agents.serve",
                        lambda *a, **k: {"ok": False, "reason": "no hay agente"}, raising=False)
    out = search.find_magnet("some movie")
    assert out["ok"] is False and "no hay agente" in out["reason"]


def test_find_magnet_reports_an_agent_that_answered_without_a_link(monkeypatch):
    monkeypatch.setattr("nucleo.mesh_agents.serve",
                        lambda *a, **k: {"ok": True, "agent": "torrentfinder", "data": {"note": "nothing"}},
                        raising=False)
    out = search.find_magnet("some movie")
    assert out["ok"] is False and "magnet" in out["reason"].lower()


def test_find_magnet_returns_the_link_and_a_title(monkeypatch):
    monkeypatch.setattr("nucleo.mesh_agents.serve",
                        lambda *a, **k: {"ok": True, "agent": "tf", "data": {"magnet": _M, "title": "The Movie"}},
                        raising=False)
    out = search.find_magnet("the movie")
    assert out["ok"] and out["magnet"] == _M and out["title"] == "The Movie"


def test_an_empty_query_is_refused_without_touching_the_mesh(monkeypatch):
    called = []
    monkeypatch.setattr("nucleo.mesh_agents.serve",
                        lambda *a, **k: called.append(1) or {"ok": True}, raising=False)
    assert search.find_magnet("   ")["ok"] is False
    assert not called


# ── 2 · the Range arithmetic a growing <video> depends on ───────────────────────────────────────────────────

def test_range_header_parses_and_clamps_to_the_file():
    assert _parse_range("bytes=100-199", 1000) == (100, 199)
    assert _parse_range("bytes=500-", 1000) == (500, 999)     # open-ended → to EOF
    assert _parse_range("bytes=-200", 1000) == (800, 999)     # suffix → last N bytes
    assert _parse_range("bytes=5000-9999", 1000) == (999, 999)  # past EOF → clamped, never negative length
    assert _parse_range("", 1000) is None                     # no header → serve whole file (200)
    assert _parse_range("bytes=abc", 1000) is None            # garbage → treated as no range


# ── 3 · the facade fails safe, and available() is DERIVED from the wheel ─────────────────────────────────────

def test_available_is_derived_from_the_wheel_not_a_flag(monkeypatch):
    monkeypatch.setattr(service.session, "available", lambda: False)
    assert service.available() is False
    # every entry point degrades to words, never a raise, when the wheel is absent
    assert service.search_and_play("x")["ok"] is False
    assert service.add_magnet(_M)["ok"] is False
    assert service.status("id")["ok"] is False
    assert service.active() == []


def test_search_and_play_reports_a_search_miss_without_adding(monkeypatch):
    monkeypatch.setattr(service.session, "available", lambda: True)
    monkeypatch.setattr(service.search, "find_magnet",
                        lambda q: {"ok": False, "reason": "nada"})
    added = []
    monkeypatch.setattr(service.session, "add_magnet", lambda m, **k: added.append(m) or {"ok": True})
    out = service.search_and_play("ghost movie")
    assert out["ok"] is False and not added   # a miss must not start a phantom download


def test_search_and_play_starts_the_download_on_a_hit(monkeypatch):
    monkeypatch.setattr(service.session, "available", lambda: True)
    monkeypatch.setattr(service.search, "find_magnet",
                        lambda q: {"ok": True, "magnet": _M, "title": "T", "agent": "a"})
    monkeypatch.setattr(service.session, "add_magnet", lambda m, **k: {"ok": True, "id": "HASH"})
    out = service.search_and_play("the movie")
    assert out["ok"] and out["id"] == "HASH" and out["title"] == "T"


# ── 4 · the widget's backend: the declared actions ARE the skills (V2-544) ──────────────────────────────────

@pytest.fixture
def wdata(monkeypatch, tmp_path):
    """Isolate the widget store (its own DATA_DIR) and stub the connector so no session is opened."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    from widgets.torrent import data as wd
    return wd


def test_search_action_stores_the_id_and_gates_the_stream_url(monkeypatch, wdata):
    monkeypatch.setattr(wdata, "_svc", lambda: _FakeSvc(streamable=False))
    res = wdata.apply_action("search", {"query": "the movie"})
    assert res["ok"] and res["id"] == "HASH"
    view = wdata.view_data()
    # not streamable yet → no stream_url, so widget.js keeps showing progress instead of a dead <video>
    assert view["id"] == "HASH" and view["stream_url"] == "" and view["streamable"] is False


def test_stream_url_appears_only_once_the_file_is_streamable(monkeypatch, wdata):
    monkeypatch.setattr(wdata, "_svc", lambda: _FakeSvc(streamable=True))
    wdata.apply_action("search", {"query": "the movie"})
    view = wdata.view_data()
    assert view["streamable"] is True and view["stream_url"] == "/api/torrent/stream/HASH"


def test_a_search_miss_is_stored_as_a_spoken_error(monkeypatch, wdata):
    monkeypatch.setattr(wdata, "_svc", lambda: _FakeSvc(find_ok=False))
    res = wdata.apply_action("search", {"query": "ghost"})
    assert res["ok"] is False
    view = wdata.view_data()
    assert view["error"] and view["id"] == "" and view["stream_url"] == ""


def test_an_empty_query_never_reaches_the_connector(monkeypatch, wdata):
    hit = []
    monkeypatch.setattr(wdata, "_svc", lambda: hit.append(1) or _FakeSvc())
    out = wdata.apply_action("search", {"query": ""})
    assert out["ok"] is False and not hit


def test_stop_removes_the_download_and_clears_the_card(monkeypatch, wdata):
    fake = _FakeSvc(streamable=True)
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    wdata.apply_action("search", {"query": "the movie"})
    wdata.apply_action("stop")
    assert fake.removed == ["HASH"]
    view = wdata.view_data()
    assert view["id"] == "" and view["stream_url"] == ""


def test_prompt_digest_only_speaks_of_an_active_download(monkeypatch, wdata):
    monkeypatch.setattr(wdata, "_svc", lambda: _FakeSvc(streamable=False))
    assert "no hay ninguna descarga" in wdata.prompt_digest().lower()
    wdata.apply_action("search", {"query": "the movie"})
    dig = wdata.prompt_digest()
    assert "%" in dig and "fuentes" in dig


class _FakeSvc:
    """Stand-in for connectors.torrent.service — no libtorrent, no network."""
    def __init__(self, *, find_ok=True, streamable=False):
        self._find_ok = find_ok
        self._streamable = streamable
        self.removed = []

    def available(self):
        return True

    def search_and_play(self, query):
        if not self._find_ok:
            return {"ok": False, "error": "no encontré nada para eso"}
        return {"ok": True, "id": "HASH", "title": "The Movie", "agent": "a"}

    def add_magnet(self, magnet):
        return {"ok": True, "id": "HASH"}

    def status(self, rid):
        if not rid:
            return {"ok": False, "error": "sin id"}
        return {"ok": True, "id": rid, "name": "The Movie", "progress": 0.42, "num_peers": 7,
                "download_rate": 500000, "downloaded": 42, "size": 100, "state": "downloading",
                "streamable": self._streamable}

    def remove(self, rid):
        self.removed.append(rid)
        return {"ok": True, "removed": True}
