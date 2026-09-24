"""V2-764 — the torrent client is the TORRENTS section of Archivos: Catálogo · Descargas · Semillas.

The operator: *«si hay un widget de torrents separado… lo fusionas con el de los archivos… uno será la biblioteca
y la otra sección será la de torrents… tres subapartados: el dashboard, por si pido catálogos de cosas que se
puedan descargar a través del buscador de MeshKore… descargas y semillas… cuando alguien pida una búsqueda que
implique buscar el torrent, vas a utilizar este widget de archivos en su sección de torrents»*.

Measured before building: the separate `torrent` widget's `search` went straight to DOWNLOADING the first magnet
— there was no catalogue — while the network agent (`seedhound`) already answered ten releases. Its magnets
arrived HTML-escaped (`&amp;tr=…`), and each release carried a `torrent_url` with the agent's own indexer key.

Also kept from the retired widget's own test (session e373d39c): a torrent client DOWNLOADS any format; only
opening it in a player judges playability.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from widgets.archivos import data as arx
from widgets.archivos import torrents as tor

ENGINE = Path(__file__).resolve().parents[4]

_RELEASES = [
    {"title": "Night of the Living Dead (1968) 1080p", "magnet": "magnet:?xt=urn:btih:AAA&dn=notld&tr=udp://t1",
     "info_hash": "aaa", "size_bytes": 2_000_000_000, "size": "1.9 GB", "seeders": 120, "leechers": 4,
     "resolution": "1080p", "kind": "movie", "published": "2020-01-01"},
    {"title": "Night of the Living Dead 1968 720p", "magnet": "magnet:?xt=urn:btih:BBB", "info_hash": "bbb",
     "size_bytes": 900_000_000, "size": "858 MB", "seeders": 40, "leechers": 2, "resolution": "720p",
     "kind": "movie", "published": "2019-05-05"},
    {"title": "Night of the Living Dead OST", "magnet": "magnet:?xt=urn:btih:CCC", "info_hash": "ccc",
     "size_bytes": 90_000_000, "size": "86 MB", "seeders": 3, "leechers": 0, "resolution": "",
     "kind": "music", "published": ""},
]


class _FakeService:
    def __init__(self):
        self.calls = []
        self.rows = []

    def catalog(self, query):
        self.calls.append(("catalog", query))
        return {"ok": True, "releases": [dict(r) for r in _RELEASES], "agent": "seedhound"}

    def add_magnet(self, magnet, *, keep=False):
        self.calls.append(("add", magnet, keep))
        return {"ok": True, "id": "rid1"}

    def status(self, rid):
        return {"ok": True, "id": rid, "kind": "video", "playable": False,
                "file_name": "Disclosure.Day.2026.2160p.UHD.BluRay.REMUX.mkv",
                "name": "Disclosure Day 2026", "progress": 0.5, "state": "downloading"}

    def active(self):
        return list(self.rows)

    def available(self):
        return True

    def unavailable_reason(self):
        return ""

    def remove(self, rid):
        self.calls.append(("remove", rid))
        return {"ok": True}

    def file_it(self, rid):
        self.calls.append(("file", rid))
        return {"ok": True}


@pytest.fixture
def fake(monkeypatch):
    f = _FakeService()
    monkeypatch.setattr(tor, "_svc", lambda: f)
    return f


# ── the catalogue ───────────────────────────────────────────────────────────────────────────────────────────
def test_a_torrent_search_shows_the_catalogue_and_downloads_NOTHING(fake):
    res = arx.apply_action("torrent_search", {"query": "la noche de los muertos vivientes"})
    assert res["ok"] and res["count"] == 3
    assert [m["n"] for m in res["matches"]] == [1, 2, 3], "the reply must carry numbered rows the turn can say"
    assert not any(c[0] == "add" for c in fake.calls), "a SEARCH started a download — the old widget's defect"
    v = arx.view_data()
    assert v["section"] == "torrents" and v["torrents"]["tab"] == "catalogo", "the search did not land on the catalogue"
    assert [r["title"] for r in v["torrents"]["catalog"]["releases"]] == [r["title"] for r in _RELEASES]


def test_the_card_never_receives_a_magnet_or_an_agent_key(fake):
    arx.apply_action("torrent_search", {"query": "x"})
    blob = json.dumps(arx.view_data())
    assert "magnet:" not in blob and "apikey" not in blob and "torrent_url" not in blob


@pytest.mark.parametrize("item,expected", [(2, "BBB"), ("2", "BBB"), ("la segunda", "BBB"), ("la primera", "AAA"),
                                           ("la de 720p", "BBB"), ("OST", "CCC"), ("número 3", "CCC")])
def test_a_catalogue_row_is_picked_the_way_he_says_it(fake, item, expected):
    arx.apply_action("torrent_search", {"query": "x"})
    res = arx.apply_action("torrent_download", {"item": item})
    assert res["ok"], res
    assert fake.calls[-1][0] == "add" and expected in fake.calls[-1][1]
    v = arx.view_data()
    assert v["torrents"]["tab"] == "descargas", "a download must land where it can be watched"


@pytest.mark.parametrize("item", ["la décima", "Night of the Living Dead", ""])
def test_an_unclear_pick_asks_instead_of_guessing(fake, item):
    arx.apply_action("torrent_search", {"query": "x"})
    res = arx.apply_action("torrent_download", {"item": item})
    assert not res["ok"] and "cuál" in res["error"]
    assert not any(c[0] == "add" for c in fake.calls)


# ── kept from the retired widget: a torrent client downloads ANY format ───────────────────────────────────
def test_a_download_keeps_any_format_by_default_and_null_means_default(fake):
    arx.apply_action("torrent_search", {"query": "x"})
    arx.apply_action("torrent_download", {"item": 1})
    arx.apply_action("torrent_download", {"item": 1, "keep": None})
    assert [c[2] for c in fake.calls if c[0] == "add"] == [True, True]


def test_an_explicit_keep_false_is_respected_and_a_raw_magnet_works(fake):
    arx.apply_action("torrent_download", {"magnet": "magnet:?xt=urn:btih:ZZZ", "keep": False})
    assert fake.calls[-1] == ("add", "magnet:?xt=urn:btih:ZZZ", False)


def test_open_still_refuses_an_unplayable_mkv(fake):
    res = arx.apply_action("torrent_open", {"id": "rid1"})
    assert res["ok"] is False and ".mkv" in res["error"]


# ── sections, by any of their names ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload,section,tab", [
    ({"section": "torrents"}, "torrents", None), ({"section": "las descargas"}, "torrents", None),
    ({"tab": "dashboard"}, "torrents", "catalogo"), ({"tab": "semillas"}, "torrents", "semillas"),
    ({"tab": "descargando"}, "torrents", "descargas"), ({"section": "mis archivos"}, "biblioteca", None),
])
def test_show_section_answers_to_his_words(fake, payload, section, tab):
    res = arx.apply_action("show_section", payload)
    assert res["ok"], res
    v = arx.view_data()
    assert v["section"] == section
    if tab:
        assert v["torrents"]["tab"] == tab


def test_a_library_verb_brings_the_library_back(fake, monkeypatch):
    arx.apply_action("show_section", {"section": "torrents"})
    arx.apply_action("go_home", {})
    assert arx.view_data()["section"] == "biblioteca"


def test_a_catalogue_row_and_a_live_download_have_different_fields(fake):
    """«La segunda» of the catalogue must never cancel the second DOWNLOAD (V2-026: one field per class)."""
    fake.rows = [{"ok": True, "id": "rid9", "name": "Algo bajando", "progress": 0.3, "state": "downloading"}]
    arx.apply_action("torrent_search", {"query": "x"})
    refs = {(r["field"], r["id"]) for r in arx.ref_index()}
    assert ("item", "2") in refs and ("id", "rid9") in refs


def test_the_digest_says_what_the_catalogue_holds(fake):
    arx.apply_action("torrent_search", {"query": "la noche"})
    d = arx.prompt_digest()
    assert "TORRENTS" in d and "1. Night of the Living Dead (1968) 1080p" in d


# ── the connector's catalogue ───────────────────────────────────────────────────────────────────────────────
def test_the_network_catalogue_unescapes_magnets_and_drops_the_agents_key(monkeypatch):
    from connectors.torrent import search
    from nucleo import mesh_agents
    rel = {"title": "X 1080p", "magnet": "magnet:?xt=urn:btih:AB&amp;dn=X&amp;tr=udp%3A%2F%2Ft",
           "torrent_url": "http://host/dl/?jackett_apikey=SECRET&amp;path=p", "info_hash": "ab",
           "size_bytes": 1, "size_human": "1 B", "seeders": 9, "quality": {"resolution": "1080p"}, "kind": "movie"}
    monkeypatch.setattr(mesh_agents, "serve",
                        lambda *a, **k: {"ok": True, "agent": "seedhound", "data": {"best": rel, "releases": [rel]}})
    got = search.find_releases("x")
    assert got["ok"] and len(got["releases"]) == 1, "the best and the list are the same release — de-duplicated"
    r = got["releases"][0]
    assert "&amp;" not in r["magnet"] and "&dn=X" in r["magnet"]
    assert "SECRET" not in json.dumps(got), "the agent's indexer key leaked into the catalogue"


# ── the separate widget is gone, and its names reach the section ────────────────────────────────────────────
def test_there_is_one_file_widget_and_its_torrent_words_open_the_section():
    from widgets import runtime
    runtime.invalidate()
    assert runtime.get("torrent") is None, "the separate torrent widget is still in the catalogue"
    for lang in ("es", "en"):
        pack = json.loads((ENGINE / f"nucleo/actionmap/seeds/{lang}.json").read_text(encoding="utf-8"))
        assert '"widget": "torrent"' not in json.dumps(pack), f"{lang}: a seed still targets the retired widget"
    from nucleo.actionmap import store
    from nucleo.actionmap.normalize import normalize
    es = {normalize(e["phrase"]): e["action"] for e in store._pack_entries(
        json.loads((ENGINE / "nucleo/actionmap/seeds/es.json").read_text(encoding="utf-8")))}
    assert es["abreme los torrents"] == {"do": "widget_data", "widget": "archivos", "action": "show_section",
                                         "payload": {"section": "torrents"}}
    assert es["ensename las semillas"]["payload"] == {"tab": "semillas"}


def test_the_manifest_draws_the_frontier_with_the_generic_search():
    m = json.loads((ENGINE / "widgets/archivos/manifest.json").read_text(encoding="utf-8"))
    assert "torrent_search" in m["actions"] and "search" in m["whenToUse"]
    assert "SIEMPRE aquí" in m["whenToUse"], "the frontier «torrent search → here, never search/results» is gone"
    for name, spec in m["actions"].items():
        assert len(spec.get("desc", "")) <= 200, f"{name}: a descriptor over the brief's cut routes nothing"
