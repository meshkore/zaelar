"""Music plays where he listens, and «playing» is read back, not assumed (V2-812 T-01).

Measured on a phone in a moving car: a Spotify account was connected, so every «play» went to Spotify, which played
on its active device or the first one it listed — not the phone. The API answered 204, the card showed the cover,
the agent said «it's playing» and sent play four more times; the phone produced nothing. The class: a provider that
plays on a device ELSEWHERE was chosen without asking where the request came from, and its 204 was taken for sound.

Then (V2-812) the start went to a Spotify device on the asking screen, else that screen's page. Since 2026-11-01
(operator's rule, V2-833 F2) it sounds on the device that asked; since 2026-11-02 a PHONE with its own Spotify app
plays there (the richer source), and without that app the page plays it and the connector says the app is missing;
a computer always uses the page. A connected Spotify identifies the song for the page; the same words again while it sounds are not re-sent; the record of where it went is what the controls reach. The Spotify Web API and the YouTube resolver are faked; nothing
reaches the network or a real device.
"""
from __future__ import annotations

import importlib

import pytest

from connectors import music
from connectors.music import registry
from connectors.music import youtube_audio as yta
from connectors.spotify import client

sp_provider = importlib.import_module("connectors.spotify.provider")

PHONE, COMPUTER = "mobile:aa11", "desktop:bb22"


class _Spotify:
    """A fake Spotify account: devices, and a player that sounds only on devices allowed to."""

    def __init__(self, devices, sounds_on=None):
        self.devices = devices
        self.sounds_on = set(sounds_on if sounds_on is not None else [d["id"] for d in devices])
        self.plays, self.paused, self.volumes = [], 0, []
        self.state = {}

    def list_devices(self):
        return list(self.devices)

    def play(self, uris=None, context_uri="", device_id=""):
        dev = next((d for d in self.devices if d["id"] == device_id), None)
        if dev is None:
            dev = next((d for d in self.devices if d.get("is_active")), None) or self.devices[0]
        self.plays.append({"uris": uris, "device_id": device_id, "on": dev["id"]})
        uri = (uris or ["spotify:track:x"])[0]
        self.state = {"is_playing": dev["id"] in self.sounds_on,
                      "device": {"id": dev["id"], "name": dev["name"], "volume_percent": 40},
                      "item": {"id": uri.rsplit(":", 1)[-1], "uri": uri, "name": "Dai Dai",
                               "artists": [{"name": "Shakira"}]}}
        return {}

    def playback_state(self):
        return dict(self.state)

    def pause(self, device_id=""):
        self.paused += 1
        if self.state:
            self.state["is_playing"] = False
        return {}

    def set_volume(self, pct, device_id=""):
        self.volumes.append(pct)
        return {}


def _dev(i, name, kind, active=False):
    return {"id": i, "name": name, "type": kind, "is_active": active, "is_restricted": False}


@pytest.fixture
def world(monkeypatch, tmp_path):
    import widgets.store as store
    from voice import screens
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(sp_provider, "_SETTLE_S", 0)
    monkeypatch.setattr(sp_provider.SpotifyProvider, "connected", lambda self: True)
    monkeypatch.setattr(yta, "_resolve", lambda q: ("vidDaiDai01", f"{q} (Official Audio)"))
    monkeypatch.setattr(client, "search", lambda q, types="track", limit=5: {"tracks": {"items": [
        {"id": "t1", "uri": "spotify:track:t1", "name": "Dai Dai", "artists": [{"name": "Shakira"}]}]}})
    registry._PROVIDERS.clear()
    registry._loaded = True
    registry.register(sp_provider.SpotifyProvider())
    registry.register(yta.YouTubeAudioProvider())
    screens._reset_for_tests()

    def install(fake: _Spotify):
        monkeypatch.setattr(client, "devices", fake.list_devices)
        for name in ("play", "playback_state", "pause", "set_volume"):
            monkeypatch.setattr(client, name, getattr(fake, name))
        return fake

    yield install
    screens._reset_for_tests()
    registry._PROVIDERS.clear()
    registry._loaded = False


def _ask_from(dev):
    from voice import screens
    screens.begin_turn(dev, "T1")


# Changed on purpose 2026-11-01 (operator's rule, V2-833 F2): a song sounds on OUR device — the page of the screen that
# asked — whatever Spotify session is open somewhere else. Changed again 2026-11-02 (operator): the phone's OWN Spotify
# app is that device, so a phone asking with that app open is the one case that leaves the page (tested below).
# Spotify, when connected, IDENTIFIES the song (a search, no device); the page player plays what it identified.
@pytest.mark.parametrize("asker", [PHONE, COMPUTER, None], ids=["phone", "computer", "no-known-screen"])
@pytest.mark.parametrize("devices", [[], [_dev("pc", "Home computer", "Computer", active=True)],
                                     [_dev("ph", "Ricart's phone", "Smartphone", active=True)]],
                         ids=["no-device", "computer-device", "phone-device"])
def test_a_song_sounds_in_the_page_of_the_screen_that_asked(world, asker, devices):
    if asker == PHONE and devices and devices[0]["type"] == "Smartphone":
        pytest.skip("a phone with its own Spotify app plays there — test_a_phone_with_spotify_open_plays_in_that_app")
    fake = world(_Spotify(devices))
    if asker:
        _ask_from(asker)
    r = music.control("play", "pon pa tipos como tú de Shakira")
    assert r.ok and r.provider == "youtube" and r.extra.get("placed") == "page"
    assert fake.plays == [], "no Spotify device was asked to play: the song sounds where he is"


def test_a_connected_spotify_names_the_song_the_page_looks_up(world, monkeypatch):
    looked: list = []
    monkeypatch.setattr(yta, "_resolve", lambda q: (looked.append(q), ("vidDaiDai01", f"{q} (Official Audio)"))[1])
    world(_Spotify([]))
    _ask_from(PHONE)
    r = music.control("play", "la de shakira que dice dai dai")
    assert looked == ["Shakira - Dai Dai"], looked
    assert r.ok and r.extra.get("identified_by") == "spotify"


def test_without_spotify_his_words_are_looked_up_as_they_are(world, monkeypatch):
    looked: list = []
    monkeypatch.setattr(yta, "_resolve", lambda q: (looked.append(q), ("vidX0000001", q))[1])
    monkeypatch.setattr(sp_provider.SpotifyProvider, "connected", lambda self: False)
    world(_Spotify([]))
    _ask_from(COMPUTER)
    r = music.control("play", "Bzrp Music Sessions 53")
    assert looked == ["Bzrp Music Sessions 53"] and r.ok and not r.extra.get("identified_by")


def test_the_same_words_again_while_it_sounds_are_not_sent_again(world, monkeypatch):
    looked: list = []
    monkeypatch.setattr(yta, "_resolve", lambda q: (looked.append(q), ("vidDaiDai01", q))[1])
    world(_Spotify([]))
    _ask_from(PHONE)
    assert music.control("play", "Shakira").ok
    again = music.control("play", "shakira")
    assert len(looked) == 1 and again.ok and again.extra.get("noop"), "a repeated play restarted the song"


# 2026-11-02 (operator): «YouTube is only the default when there is no better one». A phone that asks with its own
# Spotify app open plays THERE, read back from the player; the page is only the fallback.
def test_a_phone_with_spotify_open_plays_in_that_app(world):
    from connectors.music import placement
    fake = world(_Spotify([_dev("pc", "Home computer", "Computer", active=True), _dev("ph", "Ricart's phone", "Smartphone")]))
    _ask_from(PHONE)
    r = music.control("play", "pon pa tipos como tú de Shakira")
    assert r.ok and r.provider == "spotify" and r.extra.get("placed") == "provider", r
    assert [p["on"] for p in fake.plays] == ["ph"], "it went to the phone's app, never the computer at home"
    assert placement.recorded().get("provider") == "spotify"
    assert placement.app_missing("spotify") == []


def test_a_phone_without_the_app_plays_in_the_page_and_the_connector_says_what_is_missing(world, monkeypatch):
    from connectors import registry as cx_registry
    from connectors.music import placement
    from connectors.spotify import auth
    fake = world(_Spotify([_dev("pc", "Home computer", "Computer", active=True)]))
    _ask_from(PHONE)
    r = music.control("play", "Bzrp Music Sessions 53")
    assert r.ok and r.provider == "youtube" and fake.plays == [], "no app on the phone: another source, on its own"
    assert placement.app_missing("spotify") == ["phone"]
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": True})
    row = next(x for x in cx_registry._music() if x["id"] == "spotify")
    assert row["connected"] and row.get("warning") == "no_phone_app"
    # The app opened: the next song plays there and the warning is gone.
    fake.devices.append(_dev("ph", "Ricart's phone", "Smartphone"))
    fake.sounds_on.add("ph")
    assert music.control("play", "Dai Dai").provider == "spotify"
    assert placement.app_missing("spotify") == []
    assert "warning" not in next(x for x in cx_registry._music() if x["id"] == "spotify")


def test_a_phone_app_that_stays_silent_falls_back_to_the_page(world):
    fake = world(_Spotify([_dev("ph", "Ricart's phone", "Smartphone")], sounds_on=[]))
    _ask_from(PHONE)
    r = music.control("play", "Dai Dai")
    assert r.ok and r.provider == "youtube", "a 204 from an app that never sounds is not a song playing"
    assert fake.paused >= 1, "the late app is told to stay quiet under the page player"
