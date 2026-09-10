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


# ── 4 · service.file_it() retires the handle once the file has actually moved ──────────────────────────────

def test_file_it_retires_the_handle_once_moved(monkeypatch):
    """A torrent handle whose file just moved out from under it must not linger — its save_path is dead."""
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service.session, "is_complete", lambda rid: True)
    monkeypatch.setattr(service.session, "saved_path", lambda rid: "/tmp/downloads/x.mp3")
    removed = []
    monkeypatch.setattr(service.session, "remove", lambda rid, **k: removed.append((rid, k)))
    monkeypatch.setattr("library.index.file_into_place", lambda path, **k: {"ok": True, "rel": "audio/x.mp3"})
    out = service.file_it("HASH")
    assert out["ok"] and removed == [("HASH", {"delete_files": False})]


def test_file_it_leaves_the_handle_alone_when_the_move_fails(monkeypatch):
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service.session, "is_complete", lambda rid: True)
    monkeypatch.setattr(service.session, "saved_path", lambda rid: "/tmp/downloads/x.mp3")
    removed = []
    monkeypatch.setattr(service.session, "remove", lambda rid, **k: removed.append(rid))
    monkeypatch.setattr("library.index.file_into_place", lambda path, **k: {"ok": False, "error": "disk full"})
    out = service.file_it("HASH")
    assert out["ok"] is False and not removed


def test_file_it_refuses_an_unfinished_download_without_touching_the_session(monkeypatch):
    monkeypatch.setattr(service, "available", lambda: True)
    monkeypatch.setattr(service.session, "is_complete", lambda rid: False)
    out = service.file_it("HASH")
    assert out["ok"] is False and "terminado" in out["error"]


# ── 5 · the widget's backend: a MANAGER over `service.active()`, never its own player (redesign) ────────────

@pytest.fixture
def wdata(monkeypatch, tmp_path):
    """Isolate the widget store (its own DATA_DIR) and stub the connector so no session is opened."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store._last_hash.clear()
    from widgets.torrent import data as wd
    return wd


def test_search_action_adds_a_row_to_downloads(monkeypatch, wdata):
    fake = _FakeSvc()
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("search", {"query": "the movie"})
    assert res["ok"] and res["id"] == "HASH"
    view = wdata.view_data()
    assert view["seeds"] == [] and len(view["downloads"]) == 1
    row = view["downloads"][0]
    assert row["id"] == "HASH" and row["kind"] == "video" and row["playable"] is True


def test_a_search_miss_is_stored_as_a_spoken_error_and_adds_nothing(monkeypatch, wdata):
    fake = _FakeSvc(find_ok=False)
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("search", {"query": "ghost"})
    assert res["ok"] is False
    view = wdata.view_data()
    assert view["error"] and view["seeds"] == [] and view["downloads"] == []


def test_an_empty_query_never_reaches_the_connector(monkeypatch, wdata):
    hit = []
    monkeypatch.setattr(wdata, "_svc", lambda: hit.append(1) or _FakeSvc())
    out = wdata.apply_action("search", {"query": ""})
    assert out["ok"] is False and not hit


def test_add_magnet_action_adds_a_row(monkeypatch, wdata):
    fake = _FakeSvc()
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("add_magnet", {"magnet": _M})
    assert res["ok"] and res["id"] == "HASH2"
    assert len(wdata.view_data()["downloads"]) == 1


def test_downloads_and_seeds_are_split_by_group(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="video", state="downloading")
    fake.put("B", kind="video", state="seeding", progress=1.0)
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    view = wdata.view_data()
    assert [r["id"] for r in view["downloads"]] == ["A"]
    assert [r["id"] for r in view["seeds"]] == ["B"]
    assert view["seeds"][0]["complete"] is True


def test_remove_action_deletes_and_drops_the_row(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="video")
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("remove", {"id": "A"})
    assert res["ok"] and fake.removed == ["A"]
    assert wdata.view_data()["downloads"] == []


def test_open_on_a_playable_streaming_video_routes_to_the_video_widget(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="video", playable=True, streamable=True, name="The Movie")
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    seen = {}
    monkeypatch.setattr("nucleo.torrent_router.route_video",
                        lambda rid, title: seen.update(rid=rid, title=title) or {"ok": True})
    res = wdata.apply_action("open", {"id": "A"})
    assert res["ok"] and seen == {"rid": "A", "title": "The Movie"}


def test_open_refuses_an_unplayable_video_and_names_the_file(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="video", playable=False, file_name="Movie.mkv")
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("open", {"id": "A"})
    assert res["ok"] is False and "Movie.mkv" in res["error"]


def test_open_refuses_a_video_with_not_enough_downloaded_yet(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="video", playable=True, streamable=False, progress=0.01)
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("open", {"id": "A"})
    assert res["ok"] is False and "suficiente" in res["error"]


def test_open_on_a_finished_audio_files_it_and_routes_to_music(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="audio", playable=True, state="seeding", progress=1.0, name="Song")
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    seen = {}
    monkeypatch.setattr("nucleo.torrent_router.route_audio",
                        lambda rid, title: seen.update(rid=rid, title=title) or {"ok": True})
    res = wdata.apply_action("open", {"id": "A"})
    assert res["ok"] and seen == {"rid": "A", "title": "Song"}


def test_open_on_an_unfinished_audio_row_refuses(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="audio", playable=True, state="downloading", progress=0.5)
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("open", {"id": "A"})
    assert res["ok"] is False and "termine" in res["error"]


def test_save_action_files_a_finished_download(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="audio", playable=False, state="seeding", progress=1.0)
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    res = wdata.apply_action("save", {"id": "A"})
    assert res["ok"] and fake.filed == ["A"]


def test_prompt_digest_names_downloading_and_seeding_counts(monkeypatch, wdata):
    fake = _FakeSvc()
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    assert "no hay ninguna descarga" in wdata.prompt_digest().lower()
    fake.put("A", kind="video", state="downloading", progress=0.3, name="The Movie")
    fake.put("B", kind="video", state="seeding", progress=1.0, name="Old Film")
    dig = wdata.prompt_digest()
    assert "1 descargando" in dig and "The Movie" in dig
    assert "1 completadas" in dig or "completada" in dig


def test_ref_index_lists_live_rows_by_title(monkeypatch, wdata):
    fake = _FakeSvc()
    fake.put("A", kind="video", name="The Movie")
    monkeypatch.setattr(wdata, "_svc", lambda: fake)
    idx = wdata.ref_index()
    assert idx == [{"id": "A", "label": "The Movie", "field": "id"}]


def test_view_data_reports_unavailable_with_a_reason(monkeypatch, wdata):
    monkeypatch.setattr(wdata, "_svc", lambda: _UnavailableSvc())
    view = wdata.view_data()
    assert view["available"] is False and "desactivado" in view["unavailable_reason"]


class _UnavailableSvc:
    def available(self):
        return False

    def unavailable_reason(self):
        return "el cliente de descargas está desactivado en la configuración"


class _FakeSvc:
    """Stand-in for connectors.torrent.service — no libtorrent, no network. Holds several handles at once,
    the way `list_active()` really does, so grouping/routing can be exercised without a real session."""
    def __init__(self, *, find_ok=True):
        self._find_ok = find_ok
        self._handles: dict = {}
        self.removed: list = []
        self.filed: list = []

    def put(self, rid, *, kind="video", playable=True, streamable=False, state="downloading",
            progress=0.42, name="", file_name=""):
        self._handles[rid] = {
            "ok": True, "id": rid, "name": name, "progress": progress, "num_peers": 7,
            "download_rate": 500000, "downloaded": 42, "size": 100, "state": state,
            "file_name": file_name or (f"x.{'mp4' if kind == 'video' else 'mp3' if kind == 'audio' else 'bin'}"),
            "kind": kind, "playable": playable,
            "group": "seed" if state == "seeding" else "download",
            "streamable": streamable,
        }
        return self._handles[rid]

    def available(self):
        return True

    def unavailable_reason(self):
        return "no disponible"

    def search_and_play(self, query, keep=False):
        if not self._find_ok:
            return {"ok": False, "error": "no encontré nada para eso"}
        self.put("HASH", kind="video", name="The Movie")
        return {"ok": True, "id": "HASH", "title": "The Movie", "agent": "a"}

    def add_magnet(self, magnet, keep=False):
        self.put("HASH2", kind="video")
        return {"ok": True, "id": "HASH2"}

    def status(self, rid):
        return self._handles.get(rid) or {"ok": False, "error": "ese torrent ya no está activo"}

    def active(self):
        return list(self._handles.values())

    def remove(self, rid):
        self._handles.pop(rid, None)
        self.removed.append(rid)
        return {"ok": True, "removed": True}

    def file_it(self, rid):
        st = self._handles.get(rid)
        if not st or float(st.get("progress") or 0) < 1:
            return {"ok": False, "error": "esa descarga todavía no ha terminado"}
        self._handles.pop(rid, None)
        self.filed.append(rid)
        return {"ok": True, "rel": "audio/x.mp3"}


# ── 6 · nucleo/torrent_router.py — the hand-off a widget's own apply_action must never make itself ──────────

def test_route_video_adopts_the_id_shows_the_player_and_pauses_music(monkeypatch):
    from nucleo import torrent_router
    calls = []
    monkeypatch.setattr("widgets.youtube.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    monkeypatch.setattr("widgets.musica.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    shown = []
    monkeypatch.setattr("voice.observer.emit",
                        lambda kind, label, **k: shown.append(k.get("extra")))
    out = torrent_router.route_video("HASH", "The Movie")
    assert out["ok"]
    assert calls[0] == ("play_torrent", {"id": "HASH", "title": "The Movie"})
    assert calls[1] == ("pause", {})                        # the other exclusive-audio surface yields
    assert shown and shown[0]["id"] == "youtube"


def test_route_video_never_shows_or_pauses_on_a_refusal(monkeypatch):
    from nucleo import torrent_router
    monkeypatch.setattr("widgets.youtube.data.apply_action",
                        lambda action, p: {"ok": False, "error": "esa descarga ya no está activa"})
    calls = []
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: calls.append(1))
    out = torrent_router.route_video("GONE")
    assert out["ok"] is False and not calls


def test_route_audio_files_it_then_hands_the_relative_path_to_music(monkeypatch):
    from nucleo import torrent_router
    from connectors.torrent import service
    monkeypatch.setattr(service, "file_it", lambda rid: {"ok": True, "rel": "audio/song.mp3"})
    calls = []
    monkeypatch.setattr("widgets.musica.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    monkeypatch.setattr("widgets.youtube.data.apply_action",
                        lambda action, p: calls.append((action, p)) or {"ok": True})
    shown = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **k: shown.append(k.get("extra")))
    out = torrent_router.route_audio("HASH", "Song")
    assert out["ok"]
    assert calls[0] == ("play_local", {"path": "audio/song.mp3"})
    assert calls[1] == ("pause", {})
    assert shown and shown[0]["id"] == "musica"


def test_route_audio_never_reaches_music_when_filing_fails(monkeypatch):
    from nucleo import torrent_router
    from connectors.torrent import service
    monkeypatch.setattr(service, "file_it", lambda rid: {"ok": False, "error": "esa descarga todavía no ha terminado"})
    hit = []
    monkeypatch.setattr("widgets.musica.data.apply_action", lambda *a, **k: hit.append(1))
    out = torrent_router.route_audio("HASH")
    assert out["ok"] is False and not hit
