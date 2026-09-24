"""V2-764 — every control of the Torrents section, RENDERED, calls the action it names.

The operator: *«cada botón que hay allí, cada sección, cada tabla, cada breadcrumb, cada botón de navegación,
todo tiene que estar operativo y funcionando y disponible para el sistema de voz estándar»*. The voice half is
the declared actions (`test_torrents_live_inside_archivos.py`); this is the hand half: the real `widget.js`
mounted in Chromium, each control clicked, and the action it sent read back — so a button wired to nothing, or
to the wrong verb, is a red test instead of a dead click.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]

_CAT = [{"n": 1, "title": "Night of the Living Dead (1968) 1080p", "size": "1.9 GB", "seeders": 120, "leechers": 4,
         "resolution": "1080p", "kind": "movie", "published": "2020-01-01"},
        {"n": 2, "title": "Night of the Living Dead 720p", "size": "858 MB", "seeders": 40, "leechers": 2,
         "resolution": "720p", "kind": "movie", "published": ""}]
_DL = [{"id": "d1", "title": "Bajando algo", "kind": "video", "playable": True, "group": "download",
        "state": "downloading", "progress": 42, "complete": False, "download_rate": 1048576, "num_peers": 7,
        "size": 900000000, "can_play": True}]
_SEED = [{"id": "s1", "title": "Ya terminada", "kind": "video", "playable": True, "group": "seed",
          "state": "seeding", "progress": 100, "complete": True, "download_rate": 0, "num_peers": 3,
          "size": 500000000, "can_play": True}]


def _data(tab="catalogo", section="torrents"):
    return {"provider": "local", "providers": [], "connected": True, "folder_id": "", "trail": [], "entries": [],
            "mode": "list", "panel": "", "section": section,
            "torrents": {"tab": tab, "available": True, "unavailable_reason": "", "error": "",
                         "catalog": {"query": "la noche", "error": "", "releases": _CAT},
                         "downloads": _DL, "seeds": _SEED}}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def card():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1300, "height": 900})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async () => {
                const m = await import('/widgets/archivos/widget.js');
                const root = document.createElement('div');
                root.style.cssText = 'width:1100px;height:760px';
                document.body.append(root);
                window.__calls = [];
                window.__mount = (data) => m.render(root, data, { action: async (n, p) => {
                    window.__calls.push([n, p]); return {ok: true}; } });
            }""")
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _mount(pg, data):
    pg.evaluate("d => { window.__calls = []; window.__mount(d); }", data)
    pg.wait_for_timeout(120)


def _calls(pg):
    return pg.evaluate("() => window.__calls.filter(c => c[0] !== 'torrent_poll' || c[1].__keep)")


def _all_calls(pg):
    return pg.evaluate("() => window.__calls")


def test_the_catalogue_is_a_cinema_of_cards_each_with_download(card):
    _mount(card, _data("catalogo"))
    cards = card.evaluate("""() => [...document.querySelectorAll('.arx-film')].map(c => ({
        n: c.dataset.n, t: c.querySelector('.arx-film-t').textContent,
        btn: !!c.querySelector('.arx-dl'), w: c.getBoundingClientRect().width}))""")
    assert [c["n"] for c in cards] == ["1", "2"] and all(c["btn"] for c in cards)
    assert all(c["w"] > 150 for c in cards), f"the cards did not lay out as a grid: {cards}"
    card.click(".arx-film[data-n='2'] .arx-dl")
    assert _all_calls(card)[-1] == ["torrent_download", {"item": 2}]


@pytest.mark.parametrize("tab", ["catalogo", "descargas", "semillas"])
def test_each_sub_tab_button_switches_to_its_tab(card, tab):
    _mount(card, _data("catalogo" if tab != "catalogo" else "descargas"))
    card.click(f".arx-tab[data-tab='{tab}']")
    assert ["show_section", {"section": "torrents", "tab": tab}] in _all_calls(card)


def test_the_header_chip_opens_the_section_and_the_back_button_leaves_it(card):
    _mount(card, _data(section="biblioteca"))
    card.click(".arx-pchip.tor")
    assert _all_calls(card)[-1] == ["show_section", {"section": "torrents"}]
    _mount(card, _data())
    card.click(".arx-tools .arx-btn:first-child")
    assert _all_calls(card)[-1] == ["show_section", {"section": "biblioteca"}]


def test_the_breadcrumb_names_where_he_is_and_its_root_goes_back_to_the_catalogue(card):
    _mount(card, _data("descargas"))
    crumbs = card.evaluate("() => [...document.querySelectorAll('.arx-crumbs .arx-crumb')].map(c => c.textContent)")
    assert crumbs[:2] == ["Torrents", "Descargas"], crumbs
    card.click(".arx-crumbs .arx-crumb:first-child")
    assert _all_calls(card)[-1] == ["show_section", {"section": "torrents", "tab": "catalogo"}]


def test_the_search_field_searches_torrents(card):
    _mount(card, _data())
    card.fill(".arx-tor-q", "big buck bunny")
    card.press(".arx-tor-q", "Enter")
    assert _all_calls(card)[-1] == ["torrent_search", {"query": "big buck bunny"}]


def test_the_sidebar_reaches_every_tab(card):
    _mount(card, _data())
    card.evaluate("() => document.querySelector('.arx').dataset.tier = 'l'")
    items = card.evaluate("""() => [...document.querySelectorAll('.arx-side-item')].map(b => b.textContent)""")
    assert any("Semillas" in t for t in items), items
    card.evaluate("""() => [...document.querySelectorAll('.arx-side-item')].find(b => b.textContent.includes('Semillas')).click()""")
    assert _all_calls(card)[-1] == ["show_section", {"section": "torrents", "tab": "semillas"}]


def test_a_download_row_plays_and_cancels_only_after_confirming(card):
    _mount(card, _data("descargas"))
    bar = card.evaluate("() => document.querySelector('.arx-trow .arx-tbar > i').style.width")
    assert bar == "42%", f"the progress bar does not show the progress: {bar}"
    card.click(".arx-trow[data-id='d1'] button[title='Reproducir']")
    assert _all_calls(card)[-1] == ["torrent_open", {"id": "d1"}]
    card.click(".arx-trow[data-id='d1'] button[title='Cancelar y borrar el fichero']")
    assert not any(c[0] == "torrent_remove" for c in _all_calls(card)), "✕ deleted without asking"
    _mount_keep_ui(card, _data("descargas"))
    card.evaluate("""() => [...document.querySelectorAll('.arx-trow[data-id="d1"] button')]
                     .find(b => b.textContent === 'Sí, borrar').click()""")
    assert _all_calls(card)[-1] == ["torrent_remove", {"id": "d1"}]


def _mount_keep_ui(pg, data):
    """Re-render on the SAME node (the confirm lives in the node's UI state, like a real SSE repaint)."""
    pg.evaluate("d => window.__mount(d)", data)
    pg.wait_for_timeout(80)


def test_a_seed_row_saves_to_the_library(card):
    _mount(card, _data("semillas"))
    card.click(".arx-trow[data-id='s1'] button[title='Guardar en la biblioteca']")
    assert _all_calls(card)[-1] == ["torrent_save", {"id": "s1"}]


def test_refresh_polls_and_a_live_download_polls_by_itself(card):
    _mount(card, _data("descargas"))
    card.wait_for_timeout(1700)
    assert any(c[0] == "torrent_poll" for c in _all_calls(card)), "a filling download stopped refreshing itself"
    _mount(card, _data("semillas"))
    card.click(".arx-tools .arx-btn:last-child")
    assert _all_calls(card)[-1] == ["torrent_poll", {}]


def test_no_script_error(card):
    assert not card._errors, card._errors
