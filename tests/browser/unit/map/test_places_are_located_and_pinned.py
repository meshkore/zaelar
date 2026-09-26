"""The map widget (demo run, 2026-09-26): «Show them on a map» got «I don't have a map widget». What is measured:
places said by name + city are geocoded here (with a stand-in when the first service fails), a place nobody can
find is REPORTED instead of pinned at an invented spot, «add» keeps what is there, «select» takes a number or a
name, `view_data` never touches the network, and the card declares that its output only exists on screen."""
import json

import pytest

from widgets.map import data as mp

_mem: dict = {}
_COORDS = {"griffith": (34.118, -118.300), "arena": (34.043, -118.267), "runyon": (34.112, -118.350)}


@pytest.fixture
def fake(monkeypatch):
    _mem.clear()
    calls = []

    def geocode(q, deadline=None):
        calls.append(q)
        for k, (lat, lon) in _COORDS.items():
            if k in q.lower():
                return {"lat": lat, "lon": lon, "found": "Los Angeles"}
        return None
    monkeypatch.setattr(mp, "_geocode", geocode)
    monkeypatch.setattr(mp.store, "load", lambda wid, seed, **k: json.loads(json.dumps(_mem.get(wid, seed))))
    monkeypatch.setattr(mp.store, "save", lambda wid, db: _mem.__setitem__(wid, json.loads(json.dumps(db))))
    return calls


def test_places_by_name_are_located_and_numbered(fake):
    got = mp.apply_action("show", {"places": [{"name": "Griffith Observatory", "address": "Los Angeles"},
                                              {"name": "Crypto.com Arena"}], "near": "Los Angeles"})
    assert got["ok"] and got["places"] == ["1. Griffith Observatory", "2. Crypto.com Arena"], got
    assert any("Los Angeles" in q for q in fake), "a place without an address is searched near the city"
    assert all(isinstance(p["lat"], float) for p in mp.view_data()["places"])


def test_a_place_nobody_finds_is_reported_not_invented(fake):
    got = mp.apply_action("show", {"places": ["Griffith Observatory", "Nowhere Café Zzz"]})
    assert got["ok"] and got["not_found"] == ["Nowhere Café Zzz"]
    assert [p["name"] for p in mp.view_data()["places"]] == ["Griffith Observatory"]
    assert not mp.apply_action("show", {"places": ["Nowhere Café Zzz"]})["ok"]


def test_add_keeps_and_select_takes_a_number_or_a_name(fake):
    mp.apply_action("show", {"places": ["Griffith Observatory"]})
    mp.apply_action("add", {"places": ["Runyon Canyon"]})
    assert [p["name"] for p in mp.view_data()["places"]] == ["Griffith Observatory", "Runyon Canyon"]
    assert mp.apply_action("select", {"item": "2"})["name"] == "Runyon Canyon"
    assert mp.apply_action("select", {"item": "griffith"})["selected"] == 1
    assert not mp.apply_action("select", {"item": "9"})["ok"]


def test_the_stand_in_geocoder_answers_when_the_first_fails(monkeypatch):
    seen = []

    def get(url, timeout=None):
        seen.append(url)
        if "photon" in url:
            raise OSError("down")
        return [{"lat": "34.1", "lon": "-118.3", "display_name": "Griffith Observatory, LA"}]
    monkeypatch.setattr(mp, "_get", get)
    hit = mp._geocode("Griffith Observatory, Los Angeles")
    assert hit and hit["lat"] == 34.1 and [("photon" in u) for u in seen] == [True, False]


def test_view_data_never_touches_the_network(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))

    def boom(*a, **k):
        raise AssertionError("view_data reached the network")
    monkeypatch.setattr(mp.urllib.request, "urlopen", boom)
    assert mp.view_data()["places"] == []


def test_the_card_is_shipped_and_brings_itself_on_screen():
    from widgets import effects as fx, registry
    assert registry.origin_of({"id": "map"}) == "builtin"
    for a in ("show", "add", "select"):
        assert fx.carries("map", a, fx.PRESENT_MOUNT), a


def test_a_slow_geocoder_gets_only_the_time_that_is_left(monkeypatch):
    """V2-773 audit: the deadline was read only BETWEEN places, so one place started with a second to spare
    could still run two services × 2.5 s, and three slow places blew past the widget pool's 8 s. Every call
    is now capped at what is left, and a call that cannot land in time is not made."""
    import time as _t
    seen = []
    now = [1000.0]
    monkeypatch.setattr(mp.time, "time", lambda: now[0])

    def get(url, timeout=mp._TIMEOUT_S):
        seen.append(round(timeout, 2))
        now[0] += timeout                                  # the service uses every second it is given
        raise TimeoutError("slow")
    monkeypatch.setattr(mp, "_get", get)
    assert mp._geocode("Griffith Observatory", deadline=1003.0) is None
    assert seen == [2.5, 0.5], "photon got the full cap, nominatim only the half second that was left"
    seen.clear()
    assert mp._geocode("Somewhere", deadline=1000.2) is None
    assert seen == [], "no time left: no call is made"
    seen.clear()
    now[0] = 1000.0
    mp._geocode("Anywhere")                                # no deadline: the plain cap, twice
    assert seen == [2.5, 2.5]
