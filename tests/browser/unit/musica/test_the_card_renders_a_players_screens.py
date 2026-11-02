"""V2-795 — the music card's new screens, RENDERED: what a player shows and what each control asks of the server.

None of this is readable from the source: whether a shelf is a panel one rung up the ladder, whether the «new list»
is a pill and not a giant tile, what a drag between two rows asks, whether the search box keeps the bar to one row,
and whether the text stays legible on the real dark palette. The fixture mounts the REAL card chrome
(.hb-win > .hb-scroll > root) and, for the legibility case, the real `palette.css`.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest
from tests.waiting import port_listening

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_CARD_CSS = """
  .hb-win{position:fixed;left:20px;top:20px;display:flex;flex-direction:column;
          padding:30px 0 0;overflow:hidden;box-sizing:border-box;background:var(--hb-bg,#fff)}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
"""


def _t(title, artist="", art="", **kw):
    d = {"title": title, "artist": artist, "album": "", "art": art, "query": f"{title} {artist}".strip(), "uri": ""}
    d.update(kw)
    return d


def _data(**over):
    d = {"connected": False, "can_connect": True, "own_client_id_set": False, "default_available": True,
         "redirect_uri": "", "now_playing": None, "mode": "idle", "yt": {}, "local": {}, "playlists": [],
         "recent": [], "counts": {}, "top": [], "fav_current": False, "fav": {"id": "", "name": "Favoritos"},
         "modes": {"shuffle": False, "repeat": "off", "supported": False}, "volume": {"level": None, "muted": False},
         "queue": {"items": [], "editable": False, "source": ""}, "browse": {}, "view": {"kind": "home", "id": ""}}
    d.update(over)
    return d


def _yt(**over):
    y = {"videoId": "VID00000001", "title": "Bohemian Rhapsody", "artist": "Queen", "paused": False, "cmd_seq": 1,
         "art": "", "volume": 70}
    y.update(over)
    return y


def _playing(**over):
    base = {"yt": _yt(), "mode": "youtube", "modes": {"shuffle": False, "repeat": "off", "supported": True},
            "volume": {"level": 70, "muted": False}}
    return _data(**{**base, **over})


_IMG = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='4' height='4'><rect width='4' height='4' fill='red'/></svg>"


@pytest.fixture(scope="module")
def _page():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page._hb_port = port
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, w=468, h=540, palette=False):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/musica/")
    link = "<link rel='stylesheet' href='/frontend/app/core/palette.css'>" if palette else ""
    page.set_content(f"{link}<style>{_CARD_CSS}</style><div class='hb-win' style='width:{w}px;height:{h}px'>"
                     f"<div class='hb-scroll'><div id='w'></div></div></div>")
    if palette:
        page.wait_for_function("() => getComputedStyle(document.documentElement).getPropertyValue('--hb-bg').trim()")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             openConnector: () => {}, running: true};
             window.__el = document.getElementById('w');
             mod.render(window.__el, data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/musica/widget.js", data])


def _rerender(page, data):
    page.evaluate("(d) => window.__mod.render(window.__el, d, window.__ctx)", data)


def _calls(page, name=None):
    calls = page.evaluate("() => window.__calls")
    return [c[1] for c in calls if c[0] == name] if name else calls


ROCK = [_t("Sweet Child O' Mine", "Guns N' Roses", _IMG + "#1"), _t("Back in Black", "AC/DC", _IMG + "#2"),
        _t("Livin' on a Prayer", "Bon Jovi", _IMG + "#3"), _t("September", "EWF", _IMG + "#4")]
LISTS = [{"id": "rock", "name": "Rock", "art": "", "tracks": ROCK},
         {"id": "fav", "name": "Favoritos", "art": "", "tracks": [ROCK[1]]}]


# ── the library is SECTIONED ─────────────────────────────────────────────────────────────────────────────

def test_each_shelf_is_a_quiet_panel_and_lists_are_cards(_page):
    _mount(_page, _data(playlists=LISTS, recent=[ROCK[0]], top=[dict(ROCK[0], count=3)],
                        fav={"id": "fav", "name": "Favoritos"}))
    secs = _page.evaluate("""() => [...document.querySelectorAll('.hb-mus2-sec')].map(s => {
        const c = getComputedStyle(s); return {t: s.querySelector('.hb-mus2-sech').textContent,
          bg: c.backgroundColor, border: c.borderTopWidth, shadow: c.boxShadow, radius: c.borderTopLeftRadius}; })""")
    # the responsive pass: Home reads continue listening → your lists → recently played → favourites (most played
    # moved to «Your music», one tab of its own)
    assert [s["t"] for s in secs] == ["Seguir escuchando", "Tus listas", "Recientes", "Favoritos"]
    for s in secs:
        assert s["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), "a shelf sits one rung up, not flat on the card"
        assert s["border"] == "1px" and s["shadow"] != "none" and s["radius"] != "0px"
    names = _page.eval_on_selector_all(".hb-mus2-sec:nth-child(2) .hb-mus2-shelf .hb-mus2-plname",
                                       "els => els.map(e => e.textContent)")
    assert names == ["Favoritos", "Rock"], "the favourites list comes first"
    assert _page.query_selector(".hb-mus2-pl .hb-mus2-mosaic") is not None, "four covers make a mosaic"
    pill = _page.query_selector(".hb-mus2-sechead .hb-mus2-pill.hb-mus2-new")
    assert pill is not None and pill.bounding_box()["height"] <= 32, "«new list» is a pill, not a giant tile"


def test_the_new_list_pill_asks_a_name_and_creates_it(_page):
    _mount(_page, _data(playlists=LISTS))
    _page.click(".hb-mus2-sechead .hb-mus2-new")
    _page.fill(".hb-mus2-newinp", "Domingo")
    _page.press(".hb-mus2-newinp", "Enter")
    assert _calls(_page, "create_playlist") == [{"name": "Domingo"}]


# ── rows do what a player's rows do ──────────────────────────────────────────────────────────────────────

def test_a_rows_heart_saves_into_the_servers_favourites_and_a_lit_one_removes(_page):
    _mount(_page, _data(playlists=LISTS, recent=[ROCK[0], ROCK[1]], fav={"id": "fav", "name": "Favoritos"}))
    rows = _page.query_selector_all(".hb-mus2-sec:nth-last-child(2) .hb-mus2-tr")     # «Recientes»
    rows[0].hover(); rows[0].query_selector(".hb-mus2-trx .hb-mus2-ibtn").click()
    lit = rows[1].query_selector(".hb-mus2-trx .hb-mus2-ibtn.on")
    assert lit is not None, "a song already in Favoritos wears a lit heart"
    rows[1].hover(); lit.click()
    assert _calls(_page, "add_to_playlist")[0]["playlist"] == "fav"
    assert _calls(_page, "remove_from_playlist") == [{"playlist": "fav", "item": "Back in Black"}]


def test_a_row_queues_and_adds_to_a_list(_page):
    _mount(_page, _data(playlists=LISTS, recent=[ROCK[2]]))
    row = _page.query_selector(".hb-mus2-sec:last-child .hb-mus2-tr")
    row.hover()
    btns = row.query_selector_all(".hb-mus2-trx .hb-mus2-ibtn")
    btns[1].click()
    assert _calls(_page, "queue") == [{"query": "Livin' on a Prayer Bon Jovi"}]
    row.hover(); btns[2].click()
    items = _page.eval_on_selector_all(".hb-mus2-menu button", "els => els.map(e => e.textContent)")
    assert items[:2] == ["Rock", "Favoritos"]
    _page.click(".hb-mus2-menu button:first-child")
    assert _calls(_page, "add_to_playlist")[-1]["playlist"] == "rock"


def test_a_hostile_title_is_text_never_markup(_page):
    _mount(_page, _data(recent=[_t("<img src=x onerror=window.__pwned=1>", "<b>x</b>")]))
    assert _page.evaluate("() => window.__pwned") is None
    assert _page.query_selector(".hb-mus2-trt img") is None


# ── a list: rename, delete, shuffle, reorder ─────────────────────────────────────────────────────────────

def test_a_list_is_renamed_in_place(_page):
    _mount(_page, _data(playlists=LISTS, view={"kind": "playlist", "id": "rock"}))
    _page.click(".hb-mus2-acts .hb-mus2-ibtn:not(.risk)")
    _page.fill(".hb-mus2-renin", "Rock clásico")
    _page.press(".hb-mus2-renin", "Enter")
    assert _calls(_page, "rename_playlist") == [{"playlist": "rock", "name": "Rock clásico"}]


def test_deleting_a_list_is_asked_on_the_card_first(_page):
    _mount(_page, _data(playlists=LISTS, view={"kind": "playlist", "id": "rock"}))
    _page.click(".hb-mus2-acts .hb-mus2-ibtn.risk")
    assert _calls(_page, "delete_playlist") == [], "the first click only asks"
    _page.click(".hb-mus2-acts .hb-mus2-pill.risk")
    assert _calls(_page, "delete_playlist") == [{"playlist": "rock"}]


def test_shuffle_plays_the_list_mixed(_page):
    _mount(_page, _data(playlists=LISTS, view={"kind": "playlist", "id": "rock"}))
    _page.click(".hb-mus2-acts .hb-mus2-pill")
    assert _calls(_page, "play_playlist") == [{"playlist": "rock", "shuffle": True}]


def test_dragging_a_song_onto_another_moves_it_once(_page):
    _mount(_page, _data(playlists=LISTS, view={"kind": "playlist", "id": "rock"}))
    _page.drag_and_drop(".hb-mus2-tr:nth-child(3)", ".hb-mus2-tr:nth-child(1)")
    assert _calls(_page, "move_track") == [{"playlist": "rock", "item": "3", "to": "1"}]


# ── the queue ────────────────────────────────────────────────────────────────────────────────────────────

def test_the_queue_screen_edits_the_free_players_queue(_page):
    _mount(_page, _playing(queue={"items": ROCK[:3], "editable": True, "source": "youtube"},
                           view={"kind": "queue", "id": ""}))
    heads = _page.eval_on_selector_all(".hb-mus2-sech", "els => els.map(e => e.textContent)")
    assert heads == ["Sonando ahora", "A continuación"]
    assert "on" in _page.query_selector(".hb-mus2-segb:last-child").get_attribute("class"), "the Cola tab is lit"
    _page.query_selector_all(".hb-mus2-sec:last-child .hb-mus2-x")[1].click()
    _page.click(".hb-mus2-sec:last-child .hb-mus2-pill")
    assert _calls(_page, "queue_remove") == [{"item": "2"}] and _calls(_page, "queue_clear") == [{}]


def test_a_queue_the_player_cannot_edit_is_shown_read_only(_page):
    _mount(_page, _playing(queue={"items": ROCK[:2], "editable": False, "source": "spotify"},
                           view={"kind": "queue", "id": ""}))
    assert _page.query_selector(".hb-mus2-sec:last-child .hb-mus2-x") is None
    assert _page.query_selector(".hb-mus2-sec:last-child .hb-mus2-note") is not None


# ── search, artist, album ────────────────────────────────────────────────────────────────────────────────

SEARCH = {"query": "queen", "source": "itunes", "tracks": [_t("Bohemian Rhapsody", "Queen")],
          "artists": [{"id": "1", "name": "Queen", "art": "", "source": "itunes"}],
          "albums": [{"id": "9", "name": "A Night at the Opera", "artist": "Queen", "art": "", "year": "1975",
                      "uri": "", "source": "itunes"}], "playlists": []}


def test_the_search_box_lives_in_the_one_bar_and_asks_on_enter(_page):
    # a desktop-sized card: the field is in the one bar, always there
    _mount(_page, _data(view={"kind": "search", "id": ""}), w=900, h=600)
    assert _page.query_selector(".hb-mus2-headfix .hb-mus2-sinp") is not None
    assert _page.query_selector(".hb-mus2-headfix").bounding_box()["height"] <= 48
    # a narrow card has no room for it in the bar: it heads the screen instead, still one field
    _mount(_page, _data(view={"kind": "search", "id": ""}))
    assert _page.query_selector(".hb-mus2-headfix .hb-mus2-sinp") is None
    assert len(_page.query_selector_all(".hb-mus2-stop .hb-mus2-sinp")) == 1
    _page.fill(".hb-mus2-sinp", "queen")
    _page.press(".hb-mus2-sinp", "Enter")
    assert _calls(_page, "search") == [{"query": "queen"}]


def test_a_draft_survives_a_repaint(_page):
    _mount(_page, _data(view={"kind": "search", "id": ""}))
    _page.type(".hb-mus2-sinp", "que")
    _rerender(_page, _data(view={"kind": "search", "id": ""}, recent=[ROCK[0]]))
    assert _page.input_value(".hb-mus2-sinp") == "que"


def test_results_open_artist_and_album_pages_and_play_an_album(_page):
    _mount(_page, _data(view={"kind": "search", "id": ""}, browse={"search": SEARCH}))
    heads = _page.eval_on_selector_all(".hb-mus2-sech", "els => els.map(e => e.textContent)")
    assert heads == ["Canciones", "Artistas", "Álbumes"]
    _page.click(".hb-mus2-face")
    assert _calls(_page, "open_view")[-1] == {"kind": "artist", "id": "1", "source": "itunes", "name": "Queen"}
    _page.hover(".hb-mus2-lists .hb-mus2-pl")
    _page.click(".hb-mus2-lists .hb-mus2-plplay")
    assert _calls(_page, "play_album")[-1]["album"] == "A Night at the Opera"


def test_an_album_page_plays_it_and_keeps_it_as_a_list(_page):
    page = {"album": {"id": "9", "name": "A Night at the Opera", "artist": "Queen", "year": "1975", "art": "",
                      "uri": "", "source": "itunes"}, "tracks": [_t("Death on Two Legs", "Queen"), _t("39", "Queen")]}
    _mount(_page, _data(view={"kind": "album", "id": "9"}, browse={"album": page}))
    assert _page.inner_text(".hb-mus2-headk").lower() == "álbum"
    _page.click(".hb-mus2-playfab")
    _page.click(".hb-mus2-acts .hb-mus2-pill")
    assert _calls(_page, "play_album")[-1]["id"] == "9"
    assert _calls(_page, "add_tracks")[-1] == {"playlist": "A Night at the Opera",
                                               "tracks": [{"title": "Death on Two Legs", "artist": "Queen"},
                                                          {"title": "39", "artist": "Queen"}]}


def test_an_artist_page_shows_popular_songs_and_albums(_page):
    page = {"artist": {"id": "1", "name": "Queen", "art": "", "source": "itunes"},
            "top": [_t("Bohemian Rhapsody", "Queen")], "albums": SEARCH["albums"]}
    _mount(_page, _data(view={"kind": "artist", "id": "1"}, browse={"artist": page}))
    heads = _page.eval_on_selector_all(".hb-mus2-sech", "els => els.map(e => e.textContent)")
    assert heads == ["Populares", "Álbumes"]
    _page.click(".hb-mus2-acts .hb-mus2-pill")
    assert _calls(_page, "play_album")[-1]["kind"] == "artist"


# ── the transport ────────────────────────────────────────────────────────────────────────────────────────

def test_shuffle_repeat_and_mute_are_on_the_bar(_page):
    _mount(_page, _playing(view={"kind": "library", "id": ""}))
    btns = _page.query_selector_all(".hb-mus2-barc button")
    btns[0].click(); btns[4].click()
    _page.click(".hb-mus2-barprog .hb-mus2-cbtn")
    assert _calls(_page, "shuffle") == [{"on": True}]
    assert _calls(_page, "repeat") == [{"mode": "all"}], "off → the queue → the song → off"
    assert _calls(_page, "set_volume") == [{"mute": True}]
    _rerender(_page, _playing(view={"kind": "library", "id": ""},
                              modes={"shuffle": True, "repeat": "all", "supported": True}))
    lit = _page.eval_on_selector_all(".hb-mus2-barc .mode.on", "els => els.length")
    assert lit == 2, "a mode that is on is drawn on"


def test_a_player_without_modes_draws_them_inert(_page):
    _mount(_page, _playing(modes={"shuffle": False, "repeat": "off", "supported": False}))
    assert all(b.is_disabled() for b in _page.query_selector_all(".hb-mus2-barc .mode"))


def test_the_bars_progress_line_waits_for_the_clock_and_seeks_once(_page):
    np = {"playing": True, "device": "", "volume": 40, "title": "Song", "artist": "A", "album": "", "art": "",
          "progress_ms": 0, "duration_ms": 200000}
    _mount(_page, _data(connected=True, now_playing=np, mode="spotify", view={"kind": "library", "id": ""}))
    rail = _page.query_selector(".hb-mus2-barrail")
    assert rail.is_visible()
    _mount(_page, _playing(view={"kind": "library", "id": ""}))
    assert not _page.query_selector(".hb-mus2-barrail").is_visible(), "no clock yet: no line pinned at zero"
    _mount(_page, _data(connected=True, now_playing=np, mode="spotify", view={"kind": "library", "id": ""}))
    box = _page.query_selector(".hb-mus2-barrail").bounding_box()
    _page.mouse.move(box["x"] + 2, box["y"] + box["height"] / 2)
    _page.mouse.down()
    _page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] / 2)
    assert _calls(_page, "seek") == []
    _page.mouse.up()
    seeks = _calls(_page, "seek")
    assert len(seeks) == 1 and 90 <= seeks[0]["to"] <= 110, seeks


def test_a_song_the_card_shows_is_reported_once(_page):
    _mount(_page, _playing(yt=_yt(title="Unique Song 795")))
    _rerender(_page, _playing(yt=_yt(title="Unique Song 795", cmd_seq=2)))
    assert _calls(_page, "played") == [{"title": "Unique Song 795", "artist": "Queen", "art": ""}]


# ── dark mode, legibility first (V2-691) ─────────────────────────────────────────────────────────────────

def _contrast(page, sel_fg, sel_bg):
    return page.evaluate("""([a, b]) => {
      const rgb = s => s.match(/[\\d.]+/g).slice(0, 3).map(Number);
      const lum = c => { const [r, g, b] = c.map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
                         return .2126 * r + .7152 * g + .0722 * b; };
      const fg = lum(rgb(getComputedStyle(document.querySelector(a)).color));
      const bg = lum(rgb(getComputedStyle(document.querySelector(b)).backgroundColor));
      return (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05); }""", [sel_fg, sel_bg])


def test_on_the_dark_palette_the_text_on_a_panel_stays_legible(_page):
    _mount(_page, _data(playlists=LISTS, recent=[ROCK[0]]), palette=True)
    assert _page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--hb-bg').trim()") \
        .lower() == "#1f242b", "the default palette is the dark one"
    assert _contrast(_page, ".hb-mus2-sec .hb-mus2-trt", ".hb-mus2-sec") >= 7
    assert _contrast(_page, ".hb-mus2-sec .hb-mus2-tra", ".hb-mus2-sec") >= 4.5
    assert _contrast(_page, ".hb-mus2-sech", ".hb-mus2-sec") >= 7


# ── the effects say the REAL state (operator, with a screenshot: a paused song animating in the list) ────────

def _the_list_holding(paused):
    rock = {"id": "rock", "name": "Rock", "art": "", "tracks": [_t("Hotel California", "Eagles"),
                                                                _t("Wish You Were Here", "Pink Floyd")]}
    return _playing(yt=_yt(title="Wish You Were Here", artist="Pink Floyd", paused=paused), playlists=[rock],
                    view={"kind": "playlist", "id": "rock"})


def test_a_paused_song_is_marked_still_never_animated(_page):
    _mount(_page, _the_list_holding(paused=True))
    assert _page.query_selector(".hb-mus2-eq") is None, "no meter anywhere: nothing is sounding"
    assert _page.query_selector(".hb-mus2-areq") is None, "and no badge on the bar's cover"
    cur = _page.query_selector_all(".hb-mus2-tr.current")
    assert len(cur) == 1 and "playing" not in cur[0].get_attribute("class")
    assert cur[0].query_selector(".hb-mus2-trn svg") is not None, "a still marker says which one is current"


def test_a_sounding_song_animates_in_the_row_and_on_the_bar(_page):
    _mount(_page, _the_list_holding(paused=False))
    assert _page.query_selector(".hb-mus2-tr.current.playing .hb-mus2-eq") is not None
    assert _page.query_selector(".hb-mus2-bar .hb-mus2-areq .hb-mus2-eq") is not None


def test_hover_and_current_never_look_alike(_page):
    _mount(_page, _the_list_holding(paused=False))
    rows = _page.query_selector_all(".hb-mus2-tr")
    rows[0].hover()
    _page.wait_for_timeout(250)
    st = _page.evaluate("""() => [...document.querySelectorAll('.hb-mus2-tr')].map(r => {
        const c = getComputedStyle(r); return {bg: c.backgroundColor, edge: c.boxShadow,
          title: getComputedStyle(r.querySelector('.hb-mus2-trt')).color}; })""")
    hovered, current = st[0], st[1]
    assert hovered["bg"] not in ("rgba(0, 0, 0, 0)", "transparent"), "hover is a tone"
    assert current["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), "current is not a fill — it is the edge and the title"
    assert "inset" in current["edge"] and hovered["edge"] in ("none", "")
    assert current["title"] != hovered["title"]


# ── the progress row and the volume bar on the transport ──────────────────────────────────────────────────

def test_the_bar_shows_elapsed_and_total_and_a_click_seeks_once(_page):
    np = {"playing": True, "device": "", "volume": 40, "title": "Song", "artist": "A", "album": "", "art": "",
          "progress_ms": 60000, "duration_ms": 200000}
    _mount(_page, _data(connected=True, now_playing=np, mode="spotify", volume={"level": 40, "muted": False},
                        view={"kind": "library", "id": ""}))
    times = _page.eval_on_selector_all(".hb-mus2-bartime", "els => els.map(e => e.textContent)")
    assert times[0].startswith("1:0") and times[1] == "3:20"
    box = _page.query_selector(".hb-mus2-barrail").bounding_box()
    _page.mouse.click(box["x"] + box["width"] * 0.75, box["y"] + box["height"] / 2)
    seeks = _calls(_page, "seek")
    assert len(seeks) == 1 and 140 <= seeks[0]["to"] <= 160, seeks


def test_before_the_player_answers_the_bar_shows_no_progress_pinned_at_zero(_page):
    _mount(_page, _playing(view={"kind": "library", "id": ""}))
    assert not _page.query_selector(".hb-mus2-barrail").is_visible()
    assert _page.query_selector(".hb-mus2-vol").is_visible(), "the volume does not wait for the clock"


def test_the_volume_bar_shows_the_level_and_moves_it(_page):
    _mount(_page, _playing(volume={"level": 35, "muted": False}, view={"kind": "library", "id": ""}))
    assert _page.input_value(".hb-mus2-vol") == "35"
    _page.fill(".hb-mus2-vol", "80")
    assert _calls(_page, "set_volume") == [{"level": 80}]
    _rerender(_page, _playing(volume={"level": 50, "muted": False}, view={"kind": "library", "id": ""}))
    assert _page.input_value(".hb-mus2-vol") == "50", "a voice volume_up/down lands on the bar"
    _rerender(_page, _playing(volume={"level": 0, "muted": True}, view={"kind": "library", "id": ""}))
    assert _page.input_value(".hb-mus2-vol") == "0"


# ── ONE app, two kinds of screen (the responsive pass) ────────────────────────────────────────────────────
# The arrangement is read from the card's REAL box. A desktop card is mounted in the window chrome above; a phone
# card in the phone shell's own geometry (Deck.js: a 48 px head, the scroller padding its child 12/12/40, a 64 px
# dock), in a touch context with a device viewport, at the sizes the spec names.

_SHELL = """<meta name='viewport' content='width=device-width,initial-scale=1'>
<style>body{margin:0}.zm-card{position:absolute;inset:0;bottom:64px;display:flex;flex-direction:column}
.zm-head{height:48px;flex:0 0 auto}.zm-scroll{flex:1 1 auto;min-height:0;overflow:auto;display:flex;flex-direction:column}
.zm-scroll > *{padding:12px 12px 40px;margin-block:0;min-height:100%;box-sizing:border-box}</style>
<div class='zm-card'><div class='zm-head'></div><div class='zm-scroll'><div id='w'></div></div></div>"""


@pytest.fixture(scope="module")
def _phone(_page):
    browser = _page.context.browser
    made = []

    def at(w, h):
        ctx = browser.new_context(viewport={"width": w, "height": h}, has_touch=True, is_mobile=w < 700)
        made.append(ctx)
        page = ctx.new_page()
        page._hb_port = _page._hb_port
        return page
    yield at
    for c in made:
        c.close()


def _mount_phone(page, data):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/musica/")
    page.set_content(_SHELL)
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             openConnector: () => {}, running: true};
             window.__el = document.getElementById('w');
             mod.render(window.__el, data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/musica/widget.js", data])


def _layout(page):
    return page.get_attribute(".hb-mus2", "data-layout")


def test_the_arrangement_follows_the_cards_real_width(_page):
    for (w, h), want in (((1280, 900), "wide"), ((1000, 700), "compact"), ((720, 600), "compact"),
                         ((468, 540), "narrow")):
        _mount(_page, _playing(view={"kind": "library", "id": ""}), w=w, h=h)
        assert _layout(_page) == want, (w, h)
    _mount(_page, _playing(view={"kind": "library", "id": ""}), w=1280, h=900)
    assert _page.query_selector(".hb-mus2-side:not(.rail)") is not None, "wide: the sidebar, expanded"
    _mount(_page, _playing(view={"kind": "library", "id": ""}), w=1000, h=700)
    assert _page.query_selector(".hb-mus2-side.rail") is not None, "compact: the sidebar folds to a rail"
    for w in (1280, 1000, 468):
        _mount(_page, _playing(view={"kind": "library", "id": ""}), w=w, h=700)
        assert _page.query_selector(".hb-mus2-bar") is not None, "every desktop size keeps the full transport"
        assert _page.query_selector(".hb-mus2-mini, .hb-mus2-bnav") is None, "the phone's pieces stay on the phone"


def test_a_resize_that_crosses_a_threshold_redraws_without_touching_the_music(_page):
    _mount(_page, _playing(view={"kind": "now", "id": ""}), w=1280, h=900)
    frame = _page.evaluate("() => { window.__f = document.querySelector('.hb-mus2-frame'); return !!window.__f; }")
    assert frame
    _page.evaluate("() => { document.querySelector('.hb-win').style.width = '600px'; }")
    _page.wait_for_function("() => document.querySelector('.hb-mus2').dataset.layout === 'narrow'")
    assert _page.evaluate("() => document.querySelector('.hb-mus2-frame') === window.__f"), \
        "the player is the same element: the song never restarted"
    assert _calls(_page) == [] or all(c[0] in ("played", "enrich_art") for c in _calls(_page)), \
        "a resize asks the server for nothing — the face, the queue and the playback are where they were"
    assert _page.query_selector(".hb-mus2-now") is not None


def test_the_wide_song_shows_its_queue_beside_it_and_a_smaller_one_opens_it_as_a_layer(_page):
    q = {"items": [_t("Next One", "A"), _t("Next Two", "B")], "editable": True, "source": "youtube"}
    _mount(_page, _playing(queue=q, view={"kind": "now", "id": ""}), w=1280, h=900)
    assert _page.query_selector(".hb-mus2-qpanel") is not None, "wide: the queue sits beside the song"
    _mount(_page, _playing(queue=q, view={"kind": "queue", "id": ""}), w=1000, h=700)
    assert _page.query_selector(".hb-mus2-qlayer.drawer") is not None, "compact: a drawer over the song"
    assert _page.query_selector(".hb-mus2-now") is not None, "the song is still under it"
    _page.click(".hb-mus2-qhead .hb-mus2-ibtn")
    assert _calls(_page, "open_view") == [{"kind": "now"}]


def test_the_phone_gets_bottom_navigation_and_a_mini_player_that_opens_the_player(_phone):
    page = _phone(390, 844)
    _mount_phone(page, _playing(view={"kind": "library", "id": ""}))
    assert _layout(page) == "mobile"
    labels = page.eval_on_selector_all(".hb-mus2-bnavb span", "els => els.map(e => e.textContent)")
    assert labels == ["Inicio", "Buscar", "Tu música", "Sonando"]
    assert page.query_selector(".hb-mus2-side, .hb-mus2-bar, .hb-mus2-headfix") is None, \
        "no sidebar, no desktop bar, and no header of its own under the shell's"
    mini = page.query_selector(".hb-mus2-mini")
    assert mini is not None
    box, nav = mini.bounding_box(), page.query_selector(".hb-mus2-bnav").bounding_box()
    assert 56 <= box["height"] <= 72 and box["y"] + box["height"] <= nav["y"] + 1, "just above the navigation"
    assert mini.query_selector(".hb-mus2-vol, .mode") is None, "no volume, shuffle or repeat in the small surface"
    mini.click()
    assert _calls(page, "open_view") == [{"kind": "now"}]
    page.click(".hb-mus2-bnavb:nth-child(3)")
    assert _calls(page, "open_view")[-1] == {"kind": "collection"}


def test_the_expanded_phone_player_keeps_play_on_screen_at_every_phone_size(_phone):
    for w, h in ((320, 568), (390, 844), (430, 932), (844, 390)):
        page = _phone(w, h)
        _mount_phone(page, _playing(view={"kind": "now", "id": ""}))
        assert page.query_selector(".hb-mus2-mini") is None, "expanded: the mini-player would repeat it"
        btns = page.query_selector_all(".hb-mus2-now .hb-mus2-barc.big button")
        assert len(btns) == 5, "shuffle · previous · play · next · repeat"
        geo = page.evaluate("""() => { const r = document.querySelector('.hb-mus2-scroll').getBoundingClientRect();
            const p = document.querySelector('.hb-mus2-barc.big .main').getBoundingClientRect();
            const others = [...document.querySelectorAll('.hb-mus2-barc.big button:not(.main)')]
              .map(b => b.getBoundingClientRect().width);
            return {top: p.top - r.top, bottom: r.bottom - p.bottom, w: p.width, others: Math.max(...others),
                    hs: document.scrollingElement.scrollWidth > innerWidth}; }""")
        assert geo["top"] >= -1 and geo["bottom"] >= -1, f"play left the screen at {w}x{h}: {geo}"
        assert geo["w"] > geo["others"], "play is the dominant control"
        assert not geo["hs"], f"horizontal overflow at {w}x{h}"


def test_the_phones_queue_is_a_sheet_over_the_player_with_up_and_down_for_every_row(_phone):
    page = _phone(390, 844)
    q = {"items": [_t("Next One", "A"), _t("Next Two", "B"), _t("Next Three", "C")], "editable": True, "source": "youtube"}
    _mount_phone(page, _playing(queue=q, view={"kind": "queue", "id": ""}))
    assert page.query_selector(".hb-mus2-qlayer.sheet") is not None
    assert page.inner_text(".hb-mus2-qtitle") == "A continuación"
    assert page.query_selector(".hb-mus2-now") is not None, "the player is under the sheet, not replaced by it"
    rows = page.query_selector_all(".hb-mus2-qsheet .hb-mus2-tr[data-idx]")
    rows[1].query_selector(".hb-mus2-trmore").click()
    items = page.eval_on_selector_all(".hb-mus2-menu button", "els => els.map(e => e.textContent)")
    assert "Subir" in items and "Bajar" in items, "reordering needs no dragging"
    page.click(".hb-mus2-menu button:has-text('Subir')")
    assert _calls(page, "queue_move") == [{"item": "2", "to": "1"}]


def test_nothing_on_the_phone_is_smaller_than_a_finger(_phone):
    page = _phone(390, 844)
    for view in ("library", "collection", "now", "search"):
        _mount_phone(page, _playing(playlists=LISTS, recent=ROCK, view={"kind": view, "id": ""},
                                    browse={"search": {"query": "rock", "tracks": ROCK[:2]}}))
        small = page.evaluate("""() => [...document.querySelectorAll('.hb-mus2 button')].filter(b => {
            const r = b.getBoundingClientRect(); return r.width && (r.width < 40 || r.height < 40); })
            .map(b => (b.title || b.className) + ' ' + Math.round(b.getBoundingClientRect().width) + 'x'
                      + Math.round(b.getBoundingClientRect().height))""")
        assert small == [], f"{view}: {small}"
