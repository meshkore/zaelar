"""V2-794 — the music card's resource for a list somebody else puts together: `add_tracks`.

A list curated for him («we are 45 to 55, rock lovers, little reggaeton, Spanish pop and party classics») is built
by a Brain Worker a few songs at a time. The card has to offer the op that takes several songs at once, maps each to
a PLAYABLE track through whichever music account is connected (a streaming account first, another connected one
next, the free YouTube-audio last), keeps a song no provider finds as its words, grows the same list call after call
— which is what lets him watch it grow — and declares the end state the errand is checked against.

Providers here are fakes registered in the real registry's priority order; nothing reaches the network.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from connectors.music import base as mb
from widgets.musica import curated
from widgets.musica import data as md


class _Fake(mb.MusicProvider):
    def __init__(self, name: str, scheme: str, *, connected: bool = True, knows=None, delay: float = 0.0):
        self.name, self._scheme, self._conn, self._knows, self._delay = name, scheme, connected, knows, delay
        self.searched: list[str] = []

    def connected(self):
        return self._conn

    def search(self, query, limit=5):
        self.searched.append(query)
        if self._delay:
            time.sleep(self._delay)
        if self._knows is not None and not any(k.lower() in query.lower() for k in self._knows):
            return []
        return [mb.Track(id=f"{self.name}-{len(self.searched)}", uri=f"{self._scheme}:{len(self.searched)}",
                         title=f"{query} (official)", artist="channel")]

    def play(self, query="", uri=""):
        return mb.MusicResult(ok=True, provider=self.name, action="play", message="ok")

    def pause(self): ...
    def resume(self): ...
    def next(self): ...
    def previous(self): ...
    def set_volume(self, percent): ...
    def now_playing(self): return None


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False, "can_connect": True})
    yield


def _providers(monkeypatch, *provs):
    from connectors.music import registry
    monkeypatch.setattr(registry, "available", lambda: [p for p in provs if p.connected()])


#: The operator's acceptance scenario, as a worker would hand it over in three batches (rock, Spanish pop, party).
SCENARIO = [
    [{"title": "Sweet Child O' Mine", "artist": "Guns N' Roses"}, {"title": "Back in Black", "artist": "AC/DC"},
     {"title": "Livin' on a Prayer", "artist": "Bon Jovi"}],
    [{"title": "La chica de ayer", "artist": "Nacha Pop"}, {"title": "Lucha de gigantes", "artist": "Nacha Pop"},
     {"title": "Entre dos tierras", "artist": "Héroes del Silencio"}],
    [{"title": "September", "artist": "Earth, Wind & Fire"}, {"title": "Dancing Queen", "artist": "ABBA"}],
]


def test_each_song_maps_to_the_connected_streaming_account_first(monkeypatch):
    spotify, youtube = _Fake("spotify", "spotify"), _Fake("youtube", "yt")
    _providers(monkeypatch, spotify, youtube)
    r = md.apply_action("add_tracks", {"playlist": "Cumple rock", "tracks": SCENARIO[0]})
    assert r["ok"] and r["created"] and r["added"] == 3 and r["resolved"] == 3, r
    pl = md._find_playlist(md._load_db(), "Cumple rock")
    assert [t["provider"] for t in pl["tracks"]] == ["spotify"] * 3
    assert pl["tracks"][0]["title"] == "Sweet Child O' Mine" and pl["tracks"][0]["artist"] == "Guns N' Roses", \
        "the caller's own title and artist win over a provider's label"
    assert not youtube.searched, "the first provider that finds it is enough"


def test_without_a_streaming_account_the_free_provider_maps_it(monkeypatch):
    _providers(monkeypatch, _Fake("spotify", "spotify", connected=False), _Fake("youtube", "yt"))
    r = md.apply_action("add_tracks", {"playlist": "Fiesta", "tracks": SCENARIO[2]})
    assert r["resolved"] == 2
    assert {t["provider"] for t in md._find_playlist(md._load_db(), "Fiesta")["tracks"]} == {"yt"}


def test_a_provider_that_does_not_find_a_song_hands_it_to_the_next(monkeypatch):
    _providers(monkeypatch, _Fake("spotify", "spotify", knows=["AC/DC"]), _Fake("youtube", "yt"))
    md.apply_action("add_tracks", {"playlist": "Mix", "tracks": SCENARIO[0]})
    got = {t["artist"]: t["provider"] for t in md._find_playlist(md._load_db(), "Mix")["tracks"]}
    assert got == {"Guns N' Roses": "yt", "AC/DC": "spotify", "Bon Jovi": "yt"}


def test_a_song_nobody_finds_is_kept_as_its_words(monkeypatch):
    _providers(monkeypatch)                                       # nothing connected at all
    r = md.apply_action("add_tracks", {"playlist": "Mix", "tracks": ["Nacha Pop - La chica de ayer"]})
    assert r["ok"] and r["added"] == 1 and r["resolved"] == 0
    t = md._find_playlist(md._load_db(), "Mix")["tracks"][0]
    assert t["title"] == "La chica de ayer" and t["artist"] == "Nacha Pop" and not t.get("uri")


def test_the_list_grows_call_after_call_without_repeating_a_song(monkeypatch):
    _providers(monkeypatch, _Fake("youtube", "yt"))
    counts = [md.apply_action("add_tracks", {"playlist": "Cumple 45-55", "tracks": batch})["count"]
              for batch in SCENARIO]
    assert counts == [3, 6, 8], "each batch is appended to the SAME list — he watches it grow"
    again = md.apply_action("add_tracks", {"playlist": "cumple 45-55", "tracks": SCENARIO[0]})
    assert again["added"] == 0 and again["count"] == 8
    assert md._load_db()["view"] == {"kind": "playlist", "id": again["playlist"]}, "the card shows the list"


def test_one_slow_provider_never_holds_the_card(monkeypatch):
    _providers(monkeypatch, _Fake("youtube", "yt", delay=1.0))
    monkeypatch.setattr(curated, "RESOLVE_BUDGET_S", 0.2)
    t0 = time.monotonic()
    r = md.apply_action("add_tracks", {"playlist": "Slow", "tracks": SCENARIO[1]})
    assert time.monotonic() - t0 < 1.0 and r["ok"] and r["added"] == 3, "what is not resolved keeps its words"


def test_an_empty_or_nameless_call_writes_nothing(monkeypatch):
    _providers(monkeypatch, _Fake("youtube", "yt"))
    assert md.apply_action("add_tracks", {"playlist": "X", "tracks": []})["error"] == "no_tracks"
    assert md.apply_action("add_tracks", {"tracks": SCENARIO[0]})["error"] == "playlist_missing"
    assert not md._load_db().get("playlists")


def test_a_track_mapped_on_one_provider_plays_by_its_words_on_another():
    yt_track = {"title": "September", "uri": "yt:abc", "provider": "yt"}
    assert curated.playable_uri(yt_track, "youtube") == "yt:abc"
    assert curated.playable_uri(yt_track, "spotify") == "", "Spotify cannot play a YouTube id: it resolves the words"
    assert curated.playable_uri({"uri": "spotify:1"}, "youtube") == "spotify:1", "an unmarked row is left as it was"


def test_the_built_list_plays_first_song_now_and_queues_the_rest(monkeypatch):
    _providers(monkeypatch, _Fake("youtube", "yt"))
    for batch in SCENARIO:
        md.apply_action("add_tracks", {"playlist": "Cumple", "tracks": batch})
    calls = []
    from connectors import music
    monkeypatch.setattr(music, "active_provider", lambda prefer="": _Fake("youtube", "yt"))
    monkeypatch.setattr(music, "control", lambda action, query="", uri="", **k: calls.append((action, uri))
                        or mb.MusicResult(ok=True, action=action))
    assert md.apply_action("play_playlist", {"playlist": "Cumple"})["ok"]
    assert calls[0][0] == "play" and calls[0][1].startswith("yt:")
    assert [a for a, _u in calls[1:]] == ["queue"] * 7


def test_the_card_declares_the_op_and_the_end_state_it_leaves():
    from nucleo.circuit import spec, verify
    from widgets import rows, runtime
    act = (runtime.get("musica") or {}).get("actions", {}).get("add_tracks") or {}
    from nucleo.turn import brief as turn_brief
    assert act and len(act["desc"]) <= turn_brief.MAX_DESC_CHARS, "the descriptor is written under the cut"
    assert "playlists" in rows.declared("musica")
    dw = spec.render("musica", "add_tracks", {"playlist": "Cumple"})
    assert spec.target_of(dw) == "musica:playlists"
    assert verify.check(dw) is False, "nothing built yet: not met"


def test_the_end_state_holds_once_the_list_exists(monkeypatch):
    from nucleo.circuit import spec, verify
    _providers(monkeypatch, _Fake("youtube", "yt"))
    md.apply_action("add_tracks", {"playlist": "Cumple", "tracks": SCENARIO[0]})
    assert verify.check(spec.render("musica", "add_tracks", {"playlist": "Cumple"})) is True


def test_a_worker_reaches_the_op_through_its_widget_door(monkeypatch):
    """The Brain Worker's door (`worker_api` → `brain_action`) is allowed to call it and the call lands on the card."""
    from nucleo.cli import worker_policy
    from widgets import server_api
    _providers(monkeypatch, _Fake("youtube", "yt"))
    payload = {"widget_id": "musica", "action": "add_tracks",
               "payload": {"playlist": "Cumple", "tracks": SCENARIO[1]}}
    assert worker_policy.classify_act("widget_data", payload) == worker_policy.ALLOW
    res = asyncio.run(server_api.brain_action("musica", "add_tracks", payload["payload"]))
    assert not (isinstance(res, dict) and res.get("error")), res
    assert len(md._find_playlist(md._load_db(), "Cumple")["tracks"]) == 3
