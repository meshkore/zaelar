# V2-717 — the operator's redesign order for the music card, with a screenshot of it open over his desktop
# while a song was playing:
#
#   «fíjate que has puesto como un contenedor exterior en el que hay un título arriba del todo que pone
#    music y los botones del sistema operativo… y dentro has metido otra caja como si eso fuera el widget de
#    música. Y yo solo quiero UNA caja encima del escritorio.»
#   «me gustaría ver la canción en toda la pantalla del widget… la imagen de la música más grande, el nombre
#    de la canción, el nombre del artista, la duración, una barra de progreso para que yo la pueda mover.»
#   «como puedes ver, está un poco triste al verse tan vacía.»
#
# None of it is readable from the source. Whether a second frame is drawn, whether the song actually FILLS
# the card, whether a bar can be dragged and what the drag then asks of the player are all properties of a
# rendered document — and the clock the scrubber needs arrives from the YouTube embed as a postMessage that
# only exists in a browser. The fixture mounts the REAL card chrome (.hb-win > .hb-scroll > root, copied from
# frontend/app/widgets/desktop.js) because a harness whose DOM differs from the product measures a different
# product (the V2-608 lesson).
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_CARD_CSS = """
  .hb-win{position:fixed;left:20px;top:20px;display:flex;flex-direction:column;
          padding:30px 16px 16px;overflow:hidden;box-sizing:border-box;background:#fff}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _track(title, artist="", **extra):
    t = {"title": title, "artist": artist, "album": "", "art": "", "query": title, "uri": "", "videoId": ""}
    t.update(extra)
    return t


def _data(**over):
    d = {
        "connected": False, "can_connect": True, "own_client_id_set": False, "default_available": True,
        "redirect_uri": "http://127.0.0.1:43917/api/spotify/callback", "now_playing": None, "mode": "idle",
        "yt": {}, "local": {}, "playlists": [], "recent": [], "counts": {}, "top": [], "fav_current": False,
        "view": {"kind": "home", "id": ""},
    }
    d.update(over)
    return d


def _yt(vid="VID00000001", title="Tibetan Healing Sounds", artist="Meditación", paused=False, **over):
    y = {"videoId": vid, "title": title, "artist": artist, "paused": paused, "cmd_seq": 1, "art": "",
         "volume": 70}
    y.update(over)
    return y


def _spotify(progress_ms=0, duration_ms=200000, playing=True, **over):
    np = {"playing": playing, "device": "Salón", "volume": 40, "title": "Song", "artist": "A", "album": "Alb",
          "art": "", "progress_ms": progress_ms, "duration_ms": duration_ms}
    np.update(over)
    return np


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page._hb_url = f"http://127.0.0.1:{port}/widgets/musica/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/musica/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, card_w=468, card_h=540):
    page.goto(page._hb_origin)
    page.set_content(
        f"<style>{_CARD_CSS}</style>"
        f"<div class='hb-win' style='width:{card_w}px;height:{card_h}px'>"
        f"<div class='hb-scroll'><div id='w'></div></div></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod; window.__data = data;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve({ok: true}); },
                              running: true };
             window.__el = document.getElementById('w');
             mod.render(window.__el, data, window.__ctx);
           }""",
        [page._hb_url, data])


def _rerender(page, data):
    """Re-render into the SAME element — what an SSE update does, and the only way to measure that the hidden
    player survives one."""
    page.evaluate("(data) => { window.__data = data; window.__mod.render(window.__el, data, window.__ctx); }",
                  data)


def _calls(page, name):
    return [c[1] for c in page.evaluate("() => window.__calls") if c[0] == name]


# ── ONE box ───────────────────────────────────────────────────────────────────────────────────────────────

def test_the_widget_draws_no_second_box_inside_the_window(_page):
    """«dentro has metido otra caja como si eso fuera el widget de música». The card chrome IS the box."""
    _mount(_page, _data())
    box = _page.evaluate(
        """() => { const c = getComputedStyle(document.querySelector('.hb-mus2'));
                   return {border: c.borderTopWidth, radius: c.borderTopLeftRadius, bg: c.backgroundColor}; }""")
    assert box["border"] in ("0px", ""), "a border of our own is the second frame he saw"
    assert box["radius"] in ("0px", ""), "and so is a rounded corner inside a rounded window"
    assert box["bg"] in ("rgba(0, 0, 0, 0)", "transparent"), \
        "a background of our own paints a card on top of the card"


def test_the_bar_never_repeats_what_the_window_already_says(_page):
    """The window chrome above carries the mark, the name «Música» and the system buttons. A title under it
    was the same sentence twice — the complaint that opened the contacts batch, and the same one here."""
    _mount(_page, _data(playlists=[{"id": "p", "name": "Lista", "art": "", "tracks": []}]))
    bar = _page.query_selector(".hb-mus2-headfix")
    assert bar is not None
    text = " ".join(bar.inner_text().split())
    chip = " ".join(_page.inner_text(".hb-mus2-prov").split())
    assert text == chip, f"with nothing sounding the bar holds the source and nothing else, not {text!r}"
    # ONE row, not a stacked header: it has to stay near a single line of chrome.
    assert bar.bounding_box()["height"] <= 44, "the bar grew back into a header band"


# ── the song IS the screen ────────────────────────────────────────────────────────────────────────────────

def test_a_sounding_song_fills_the_card_instead_of_hiding_in_the_strip(_page):
    _mount(_page, _data(yt=_yt()))
    now = _page.query_selector(".hb-mus2-now")
    assert now is not None, "with something sounding, the card's middle IS the song"
    assert _page.inner_text(".hb-mus2-nowt") == "Tibetan Healing Sounds"
    assert _page.inner_text(".hb-mus2-nowa") == "Meditación"
    assert "youtube" in _page.inner_text(".hb-mus2-nowm").lower(), "and it says where the sound comes from"
    assert _page.query_selector(".hb-mus2-sech") is None, "«sin nada más»: no library sections underneath"


def test_the_cover_on_the_song_screen_dwarfs_the_one_in_the_transport_bar(_page):
    """«la imagen de la música más grande» — the whole point, and a pure geometry question."""
    _mount(_page, _data(yt=_yt()))
    big = _page.query_selector(".hb-mus2-nowart").bounding_box()
    small = _page.query_selector(".hb-mus2-bar .hb-mus2-art").bounding_box()
    assert big["width"] >= small["width"] * 3, f"{big['width']} vs {small['width']}"
    assert abs(big["width"] - big["height"]) <= 2, "a cover is square"


def test_the_transport_stays_at_the_foot_under_the_song(_page):
    """He asked for the duplication out loud: «la canción igualmente la manejo abajo»."""
    _mount(_page, _data(yt=_yt()))
    geo = _page.evaluate(
        """() => ({card: document.querySelector('.hb-win').getBoundingClientRect().bottom,
                   bar: document.querySelector('.hb-mus2-bar').getBoundingClientRect().bottom,
                   btns: document.querySelectorAll('.hb-mus2-barc button').length})""")
    assert geo["bar"] <= geo["card"] + 1 and geo["btns"] >= 5


def test_the_song_screen_needs_no_scrollbar_at_the_size_the_card_declares(_page):
    """«sin nada más» is also a layout claim: the whole ficha — cover, title, artist, facts and scrubber —
    has to fit in the card's own first footprint (manifest `size`: 468x540, frozen by V2-630 on first
    render). Sizing the cover by WIDTH alone put a scrollbar on the one screen that exists to be calm; it is
    sized against the height that is actually there, and shrinks with the card instead of pushing."""
    # The card is resizable, so the claim has to hold across the range he can drag it to — and the smallest
    # size is where a cover sized by width alone pushes the scrubber off the bottom.
    for w, h, min_art in ((360, 400, 88), (380, 420, 100), (468, 540, 200), (900, 800, 300)):
        _mount(_page, _data(yt=_yt()), card_w=w, card_h=h)
        _page.evaluate(
            """() => window.postMessage(JSON.stringify({event: "infoDelivery", id: "hb-musica",
                 channel: "widget", info: {currentTime: 61, duration: 214}}), "*")""")
        _page.wait_for_selector(".hb-mus2-seek", timeout=2000)
        geo = _page.evaluate(
            """() => { const s = document.querySelector('.hb-mus2-scroll').getBoundingClientRect();
                       const a = document.querySelector('.hb-mus2-nowart').getBoundingClientRect();
                       const k = document.querySelector('.hb-mus2-seek').getBoundingClientRect();
                       return {head: a.top - s.top, foot: s.bottom - k.bottom, art: a.width}; }""")
        # CONTAINMENT, not scrollHeight: a column that centres its content overflows at BOTH ends, and an
        # overflow a flex centre produces is CLIPPED, not scrollable — the cover's top and the scrubber's
        # bottom simply leave the band, silently, with `scrollHeight` none the wiser. Measured the hard way:
        # the first version of this case passed against a layout that was cutting the ficha in half.
        assert geo["head"] >= -1, f"the cover is cut off the top at {w}x{h} (by {-geo['head']:.0f}px)"
        assert geo["foot"] >= -1, f"the scrubber falls off the bottom at {w}x{h} (by {-geo['foot']:.0f}px)"
        assert geo["art"] >= min_art, f"the cover shrank to {geo['art']}px at {w}x{h} — it is the point of the screen"


def test_when_the_song_ends_the_card_falls_back_to_the_library(_page):
    """A hero with nothing in it would be the emptiest screen of all."""
    _mount(_page, _data(view={"kind": "now", "id": ""},
                        recent=[_track("Algo", artist="Alguien")]))
    assert _page.query_selector(".hb-mus2-now") is None
    assert _page.query_selector(".hb-mus2-tr") is not None


# ── the scrubber ──────────────────────────────────────────────────────────────────────────────────────────

def test_no_scrubber_is_drawn_until_the_player_says_where_the_song_is(_page):
    """A bar pinned at zero that cannot be moved is worse than no bar — his own rule for this batch: what is
    not finished must look disabled, be absent, or be clear."""
    _mount(_page, _data(yt=_yt()))
    assert _page.query_selector(".hb-mus2-now") is not None
    assert _page.query_selector(".hb-mus2-seek") is None, "the embed has not sent a clock frame yet"


def test_the_scrubber_appears_the_moment_the_player_sends_its_clock(_page):
    """The free player answers through the SAME postMessage handshake that already delivers onReady/ENDED —
    no extra call, no polling of ours. It arrives a second or two AFTER the card is painted, so the card has
    to notice it rather than re-render the world."""
    _mount(_page, _data(yt=_yt()))
    _page.evaluate(
        """() => window.postMessage(JSON.stringify({event: "infoDelivery", id: "hb-musica",
             channel: "widget", info: {currentTime: 61, duration: 214}}), "*")""")
    _page.wait_for_selector(".hb-mus2-seek", timeout=2000)
    assert _page.inner_text(".hb-mus2-seek .hb-mus2-time.r") == "3:34", "the duration he asked to see"
    assert _page.inner_text(".hb-mus2-seek .hb-mus2-time:not(.r)").startswith("1:0")


def test_a_clock_from_somebody_elses_player_is_not_ours(_page):
    """The youtube WIDGET's player emits on this same window (the V2-366 cross-talk). A frame without our
    handshake id must not become this card's position."""
    _mount(_page, _data(yt=_yt()))
    _page.evaluate(
        """() => window.postMessage(JSON.stringify({event: "infoDelivery", id: "hb-youtube",
             channel: "widget", info: {currentTime: 61, duration: 214}}), "*")""")
    _page.wait_for_timeout(400)
    assert _page.query_selector(".hb-mus2-seek") is None


def test_dragging_the_rail_asks_for_ONE_seek_on_release(_page):
    """«una barra de progreso para que yo la pueda mover». Spotify is the source whose seek is a round trip,
    so it is the one where the ask is observable — and it must be one ask, not sixty on the way there."""
    _mount(_page, _data(connected=True, now_playing=_spotify(progress_ms=0, duration_ms=200000)))
    rail = _page.query_selector(".hb-mus2-rail")
    box = rail.bounding_box()
    _page.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
    _page.mouse.down()
    _page.mouse.move(box["x"] + box["width"] * 0.25, box["y"] + box["height"] / 2)
    _page.mouse.move(box["x"] + box["width"] * 0.50, box["y"] + box["height"] / 2)
    assert _calls(_page, "seek") == [], "nothing is asked of the player while the finger is still down"
    _page.mouse.up()
    seeks = _calls(_page, "seek")
    assert len(seeks) == 1, seeks
    assert 90 <= seeks[0]["to"] <= 110, seeks


def test_a_drag_in_progress_owns_the_paint(_page):
    """The tick repaints four times a second. Letting it repaint under the finger is the bar fighting him."""
    _mount(_page, _data(connected=True, now_playing=_spotify(progress_ms=0, duration_ms=200000)))
    box = _page.query_selector(".hb-mus2-rail").bounding_box()
    _page.mouse.move(box["x"] + 4, box["y"] + box["height"] / 2)
    _page.mouse.down()
    _page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] / 2)
    _page.wait_for_timeout(600)                      # two ticks go by with the finger down
    width = _page.evaluate("() => document.querySelector('.hb-mus2-fill').style.width")
    _page.mouse.up()
    assert 70 <= float(width.rstrip("%")) <= 90, f"the tick dragged the bar out from under him: {width}"


# ── a seek asked by VOICE ─────────────────────────────────────────────────────────────────────────────────

def test_a_spoken_seek_moves_the_player_that_actually_holds_the_song(_page):
    """The server has no playhead for a file playing in this page, so it leaves a numbered command and the
    card applies it — and applying it must NOT restart the song (`seq` is what means «play this again»)."""
    loc = {"src": "/api/library/audio/x.mp3", "title": "X", "artist": "", "art": "", "paused": True, "seq": 3}
    _mount(_page, _data(local=loc, view={"kind": "library", "id": ""}))
    _rerender(_page, _data(local={**loc, "seek": {"n": 1, "to": 42}}, view={"kind": "library", "id": ""}))
    state = _page.evaluate(
        """() => { const a = document.querySelector('audio'); return {t: a.currentTime, src: a.src}; }""")
    assert round(state["t"]) == 42
    assert state["src"].endswith("/api/library/audio/x.mp3"), "the same element, never a reload"


def test_a_later_pause_does_not_replay_the_last_seek(_page):
    """The counter is the seek's own on purpose: riding on `cmd_seq` would make the song jump backwards
    every time a pause or a volume command bumped the shared sequence."""
    loc = {"src": "/api/library/audio/x.mp3", "title": "X", "artist": "", "art": "", "paused": True, "seq": 3}
    _mount(_page, _data(local=loc, view={"kind": "library", "id": ""}))
    _rerender(_page, _data(local={**loc, "seek": {"n": 1, "to": 42}}, view={"kind": "library", "id": ""}))
    _page.evaluate("() => { document.querySelector('audio').currentTime = 75; }")
    _rerender(_page, _data(local={**loc, "seq": 3, "seek": {"n": 1, "to": 42}, "paused": True},
                           view={"kind": "library", "id": ""}))
    assert round(_page.evaluate("() => document.querySelector('audio').currentTime")) == 75


# ── the bar's two derived controls ────────────────────────────────────────────────────────────────────────

def test_the_switch_is_drawn_only_when_there_is_somewhere_to_switch_to(_page):
    """Derived, like the contacts rail: a switch with one side is not a switch, it is a label."""
    _mount(_page, _data(recent=[_track("Algo")]))
    assert _page.query_selector(".hb-mus2-seg") is None, "nothing sounds: «Sonando» would lead nowhere"
    _mount(_page, _data(yt=_yt(), recent=[_track("Algo")]))
    tabs = _page.query_selector_all(".hb-mus2-segb")
    assert len(tabs) == 2 and "on" in tabs[0].get_attribute("class")
    tabs[1].click()
    assert _calls(_page, "open_view") == [{"kind": "library"}]


def test_the_source_chip_is_the_door_to_the_sources_screen(_page):
    """The Spotify block used to sit in the middle of the library, first thing the eye met on a card nobody
    had asked anything yet."""
    _mount(_page, _data())
    assert _page.query_selector(".hb-mus2-adv") is None, "the connect flow is not the library's content"
    _page.query_selector(".hb-mus2-prov").click()
    assert _calls(_page, "open_view") == [{"kind": "connect"}]
    _mount(_page, _data(view={"kind": "connect", "id": ""}))
    assert _page.query_selector(".hb-mus2-adv") is not None, "and it IS the sources screen's content"
    assert _page.query_selector(".hb-mus2-back") is not None


def test_an_empty_library_has_something_to_say_and_something_to_press(_page):
    """«como puedes ver, está un poco triste al verse tan vacía». Every chip here is real: it plays."""
    _mount(_page, _data())
    assert _page.query_selector(".hb-mus2-hero") is not None
    chips = _page.query_selector_all(".hb-mus2-chip")
    assert len(chips) >= 3
    label = chips[1].inner_text().strip()
    chips[1].click()
    assert _calls(_page, "play") == [{"query": label}], "a chip that does not play is a drawing"
    assert _page.query_selector(".hb-mus2-new") is not None, "and the way to start a list stays in reach"


def test_a_library_with_something_in_it_is_still_the_library(_page):
    """The hero must not over-fire: one playlist and the shelves are back."""
    _mount(_page, _data(playlists=[{"id": "p", "name": "Disco", "art": "", "tracks": [_track("A")]}]))
    assert _page.query_selector(".hb-mus2-hero") is None
    assert _page.query_selector(".hb-mus2-pl") is not None
