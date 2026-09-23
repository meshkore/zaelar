# V2-742 — THE CARD HAD FIVE FACES AND THE VOICE COULD REACH NONE OF THEM.
#
# Measured live (session 891f2091, 2026-09-21, engine 3.33+c33c74ab). The operator got a catalogue of
# Apollo 11 videos on the dashboard, played one, and then asked to go back to choose another. Four
# times, four wordings — «vuelve al catálogo», «vuelve al catálogo de vídeos», «a la página de inicio,
# quiero volver a ver la lista para cambiarlo», «y yo te he dicho que vuelvas al catálogo». What the
# model fired:
#
#     «vuelve al catálogo»        → clear_search   ← «quita la banda de resultados del inicio»
#     «vuelve al catálogo de …»   → clear_search   ← the same, again
#     «a la página de inicio …»   → show_history   ← the history, not the catalogue
#     «… que vuelvas al catálogo» → nothing, while the reply said «Te llevo al inicio de la lista»
#
# It never routed badly. Of the widget's 48 declared actions NOT ONE meant «go back to the dashboard»,
# and the closest-sounding one DESTROYS the very list he was asking to return to. `selectTab` has been
# the card's one navigation surface since V2-632 and nothing outside the card could call it.
#
# Everything here RENDERS the real widget.js: tabs, the CSS-driven visibility, the auto-jump when a
# video arrives, and the order that must beat it are all client-side, and none of it is visible from
# source (V2-738's lesson — a test that asserts on the wrong seam cannot fail).
from __future__ import annotations

import json
import pathlib
import re
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002020401003b")


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


_RESULTS = [{"videoId": "AAAAAAAAAA%d" % i, "title": t, "channel": "C%d" % i, "url": ""}
            for i, t in enumerate(["Apolo 11 documental", "El alunizaje", "NASA restaurado"], 1)]


def _data(**over):
    d = {"videoId": "", "title": "", "channel": "", "published": "", "volume": 70, "muted": True,
         "captions": False, "paused": True, "last_cmd": "", "cmd_seq": 0, "loading": False,
         "loading_query": "", "list": [], "player_error": "", "pos": -1, "adding": "", "list_filter": "",
         "list_name": "", "blocked_channels": [], "platforms": [], "platforms_at": 0,
         "connect_focus": None, "suggested": [], "suggested_at": 0, "suggested_channels": 0,
         "suggesting": False, "search_results": [], "search_query": "", "searched_at": 0,
         "channels": [], "history": [], "prefs": {}, "prefs_notes": [], "lists": [], "quality": 0,
         "platforms_stale": False, "accounts_enabled": False, "connector_shelf": []}
    d.update(over)
    return d


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close(); break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.route("**://i.ytimg.com/**",
                       lambda r: r.fulfill(status=200, content_type="image/gif", body=_GIF))
            page.route("**://www.youtube.com/**",
                       lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"))
            page._hb_url = f"http://127.0.0.1:{port}/widgets/youtube/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/youtube/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data):
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:660px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod; window.__ctx = {
               action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
               top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [page._hb_url, data])


def _remount(page, data):
    page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", data)


def _cls(page):
    return page.evaluate("() => document.querySelector('.hb-yt').className")


def _watching_with_a_catalogue_behind(page, seq=0, tab=""):
    """The exact state of his session: a video playing, and the results he chose it from still there."""
    over = {"videoId": "AAAAAAAAAA1", "title": "Apolo 11 documental", "paused": False,
            "search_results": _RESULTS, "search_query": "Apolo 11"}
    if seq:
        over["goto_tab"] = {"tab": tab, "seq": seq}
    return _data(**over)


# ── the order the card could not be given ────────────────────────────────────────────────────────

def test_a_video_arriving_still_takes_him_to_the_player(_page):
    """The behaviour V2-632 shipped on purpose, pinned FIRST: without it the test below proves nothing,
    because «the order wins» only means something if there is something to win against."""
    _mount(_page, _data(search_results=_RESULTS, search_query="Apolo 11"))
    assert "hb-yt-t-inicio" in _cls(_page)
    _remount(_page, _watching_with_a_catalogue_behind(_page))
    assert "hb-yt-t-player" in _cls(_page)


def test_a_video_LEAVING_takes_him_back_to_the_catalogue(_page):
    """V2-753 — the MIRROR of the jump above, which was never written.

    Live session 46dcfcb4 (2026-09-22): «Uf, me he equivocado. Páralo, y vuelve al inicio.» That is ONE
    order, and `close` only ever did the first half — it empties the player (`videoId = ""`) and the
    card stayed sitting on the now-blank Reproductor tab, because `_tab` is module-lived and only the
    ARRIVAL of a video ever moved it. What he saw is what he said, twice, in two different sessions:
    «y tampoco vuelves al inicio a ver el catálogo».
    """
    _mount(_page, _watching_with_a_catalogue_behind(_page))
    assert "hb-yt-t-player" in _cls(_page)
    _remount(_page, _data(search_results=_RESULTS, search_query="Apolo 11"))    # close: the video is gone
    assert "hb-yt-t-inicio" in _cls(_page), "the card stayed on an empty player"
    nums = _page.eval_on_selector_all(".hb-yt-rnum", "els => els.map(e => e.textContent)")
    assert nums == ["1", "2", "3"], "…and the catalogue he wanted back has to still be there"


def test_choosing_the_empty_player_by_HAND_still_stands(_page):
    """The bound on the line above: it fires on the TRANSITION, not on every render without a video.
    Clicking «Reproductor» on an emptied card is his choice and nothing may snap it back — the same
    rule the arrival jump obeys, and the reason both are gated on `st.key` rather than on `hasVid`."""
    _mount(_page, _watching_with_a_catalogue_behind(_page))
    _remount(_page, _data(search_results=_RESULTS, search_query="Apolo 11"))
    _page.click(".hb-yt-tab[data-tab=player]")
    assert "hb-yt-t-player" in _cls(_page)
    # A REBUILD, not just a re-render: `render` only rewrites the card when the key or `loading`
    # moves, so a cosmetic remount cannot reach the line under test — the first version of this
    # assertion used one and stayed GREEN with the bound removed, which accused the test, not the
    # code. Starting a search is the everyday rebuild that happens with no video loaded.
    _remount(_page, _data(search_results=_RESULTS, search_query="Apolo 11",
                          loading=True, loading_query="Boeing 747"))
    assert "hb-yt-t-player" in _cls(_page), "a rebuild fought his hands"


def test_SHOW_TAB_INICIO_takes_him_back_to_the_catalogue(_page):
    """«Vuelve al catálogo», answered. The whole defect in one assertion."""
    _mount(_page, _watching_with_a_catalogue_behind(_page))
    assert "hb-yt-t-player" in _cls(_page)
    _remount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="inicio"))
    assert "hb-yt-t-inicio" in _cls(_page)


def test_going_back_does_NOT_destroy_the_catalogue_it_goes_back_TO(_page):
    """`clear_search` is what the model reached for twice, and its own desc says it «quita la banda de
    resultados del inicio». Going back must leave every result he was choosing from exactly where it
    was — otherwise the order succeeds and the screen is empty, which is what he saw."""
    _mount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="inicio"))
    nums = _page.eval_on_selector_all(".hb-yt-rnum", "els => els.map(e => e.textContent)")
    assert nums == ["1", "2", "3"], f"the numbered band he was choosing from is gone: {nums}"
    assert "Apolo 11" in _page.locator(".hb-yt-schead").inner_text()


def test_the_order_BEATS_the_auto_jump_and_not_the_other_way_round(_page):
    """Order of the two lines in `render`. Read before the jump, the auto-navigation would silently
    undo every order he gives — a no-op that logs a success, the worst shape there is."""
    _mount(_page, _data(search_results=_RESULTS, search_query="Apolo 11"))
    # the video ARRIVES in the same render that carries the order: the jump and the order collide
    _remount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="inicio"))
    assert "hb-yt-t-inicio" in _cls(_page), "the auto-jump to the player overrode an explicit order"


def test_the_SAME_face_can_be_asked_for_twice_in_a_row(_page):
    """He says «no, al inicio» when the card already thinks it is there. A consumed FLAG cannot fire
    again; a sequence can. Measured need: he repeated himself four times in that session."""
    _mount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="inicio"))
    _page.click(".hb-yt-tab[data-tab=player]")
    assert "hb-yt-t-player" in _cls(_page)
    _remount(_page, _watching_with_a_catalogue_behind(_page, seq=2, tab="inicio"))
    assert "hb-yt-t-inicio" in _cls(_page)


def test_an_order_ALREADY_OBEYED_does_not_fight_his_hands(_page):
    """The other half of the sequence: a re-render with the SAME seq must not drag him back to a tab
    he has since left by clicking. A card that keeps undoing your clicks is unusable."""
    _mount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="inicio"))
    _page.click(".hb-yt-tab[data-tab=cola]")
    _remount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="inicio"))
    assert "hb-yt-t-cola" in _cls(_page), "the card re-obeyed an order it had already obeyed"


def test_every_declared_face_is_reachable(_page):
    """Not just the dashboard: «enséñame la cola», «mis listas», «las suscripciones» are the same
    gesture, and shipping only the one that was reported would leave the next four to be reported."""
    for i, tab in enumerate(("cola", "listas", "subs", "player", "inicio"), start=1):
        _mount(_page, _watching_with_a_catalogue_behind(_page, seq=i, tab=tab))
        assert f"hb-yt-t-{tab}" in _cls(_page), tab


def test_a_face_that_does_not_exist_changes_nothing(_page):
    """Fail-soft on the CARD as well as in `data.py`: an id neither side knows leaves the view alone
    rather than blanking it."""
    _mount(_page, _watching_with_a_catalogue_behind(_page, seq=1, tab="no-existe"))
    assert "hb-yt-t-player" in _cls(_page)


# ── the declaration, which is what the voice actually reads ─────────────────────────────────────

def _manifest() -> dict:
    return json.loads((_ENGINE / "widgets/youtube/manifest.json").read_text(encoding="utf-8"))


def test_the_navigation_is_DECLARED_or_the_voice_cannot_see_it():
    """A capability the manifest does not declare does not exist for the turn: the brief enumerates
    `screen_action` from exactly this table (V2-726 A4), so an undeclared face is unreachable however
    well the card renders it."""
    spec = (_manifest().get("actions") or {}).get("show_tab")
    assert spec, "the card's faces are not declared: the voice cannot name one"
    assert spec.get("view") is True, "navigating a card is a VIEW: a bare show order may run it"
    assert not spec.get("confirm"), "changing tab must not ask permission"


def test_the_declaration_carries_the_WORDS_HE_USED():
    """The desc is what the classifier reads. «vuelve al catálogo» and «página de inicio» are his own
    words from the session, and without them in the declaration the enumeration cannot be chosen."""
    desc = ((_manifest()["actions"]["show_tab"]).get("desc") or "").lower()
    for said in ("catálogo", "inicio"):
        assert said in desc, f"the declaration never says «{said}», which is how he asked for it"


def test_the_two_lists_of_faces_CANNOT_DRIFT():
    """`data.py` validates against its `_TABS`; `widget.js` applies against its own. A face on one
    side only is an order that returns ok and does nothing — the silent failure this widget just
    spent a session producing."""
    from widgets.youtube import data as ydata
    js = (_ENGINE / "widgets/youtube/widget.js").read_text(encoding="utf-8")
    m = re.search(r"const _TABS = \[(.*?)\];", js, re.S)
    assert m, "widget.js no longer declares _TABS"
    in_js = [t.strip().strip('"\'') for t in m.group(1).split(",") if t.strip()]
    assert sorted(in_js) == sorted(ydata._TABS), f"js={in_js} py={list(ydata._TABS)}"


def test_the_payload_is_an_ENUMERATION_and_the_rung_will_not_stuff_a_sentence_into_it():
    """V2-741's rung fills one declared key from the operator's words. `tab` is a CHOICE, so a
    sentence is not one of its values — caught while declaring this action, and guarded there."""
    from nucleo.flash import direct_action as da
    assert da.fillable_key("youtube", "show_tab") == ""
    assert da.fillable_key("youtube", "search") == "query", "the guard went too wide"


# ── the server half, which the render tests structurally cannot see ─────────────────────────────

def test_an_unknown_face_is_REFUSED_and_names_the_real_ones(tmp_path, monkeypatch):
    """A silent `ok` for a tab nobody has is how «it says it will and it doesn't» starts. Refusing
    with the list is also what lets the reply be honest about it instead of inventing a success."""
    from widgets.youtube import data as ydata
    r = ydata.apply_action("show_tab", {"tab": "lateral"})
    assert r.get("ok") is False and r.get("error") == "unknown_tab"
    assert sorted(r.get("tabs") or []) == sorted(ydata._TABS), "the refusal must name what DOES exist"


def test_a_DECLARED_ALIAS_of_a_face_is_the_face(tmp_path, monkeypatch):
    """V2-754 — live session 3afe34a8: the model wrote `tab: "home"` for «vuelve al inicio del widget de
    vídeo» and this refused it: a correct order, a correct action, thrown away over vocabulary. The
    faces' aliases are declared in the manifest next to the ids (`inicio (home, dashboard, …)`), so
    the model reads the same words the widget accepts — and «dashboard», the word the first version
    of the test above used as its UNKNOWN example, is now one of them on purpose."""
    from widgets.youtube import data as ydata
    for word in ("home", "Dashboard", "catálogo", "reproductor", "queue"):
        r = ydata.apply_action("show_tab", {"tab": word})
        assert r.get("ok") is True and r.get("tab") in ydata._TABS, (word, r)
    assert ydata.apply_action("show_tab", {"tab": "home"}).get("tab") == "inicio"


def test_the_stored_order_CARRIES_A_SEQUENCE_that_grows():
    """He asked four times in one session. A flag the card has consumed cannot fire again, so the
    second «no, al inicio» would land on a card that already believes it obeyed."""
    from widgets.youtube import data as ydata
    first = ydata.apply_action("show_tab", {"tab": "cola"})
    assert first.get("ok") is True
    s1 = (ydata.view_data().get("goto_tab") or {}).get("seq")
    ydata.apply_action("show_tab", {"tab": "cola"})
    s2 = (ydata.view_data().get("goto_tab") or {}).get("seq")
    assert isinstance(s1, int) and s2 == s1 + 1, f"the sequence did not advance: {s1} → {s2}"


def test_the_order_REACHES_the_card_through_the_snapshot_it_renders():
    """`view_data` is what the widget is handed. An action that writes somewhere the card never reads
    is the silent no-op this whole batch is about."""
    from widgets.youtube import data as ydata
    ydata.apply_action("show_tab", {"tab": "listas"})
    got = ydata.view_data().get("goto_tab")
    assert isinstance(got, dict) and got.get("tab") == "listas", got


def test_going_back_LEAVES_THE_RESULTS_ALONE_server_side_too():
    """`clear_search` empties `search_results`; this must not. The card test proves the band still
    renders — this proves there is still a band to render."""
    from widgets.youtube import data as ydata
    ydata.apply_action("search", {"query": "Apolo 11", "n": 3})
    before = list((ydata.view_data().get("search_results") or []))
    ydata.apply_action("show_tab", {"tab": "inicio"})
    after = list((ydata.view_data().get("search_results") or []))
    assert after == before, "navigating back to the catalogue changed the catalogue"
