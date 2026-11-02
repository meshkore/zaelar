"""The tester sees its own screen (2026-10-27).

The person a use case plays sits in front of the screen; the driver that plays them never saw it. Told «Ya está»
after the card really left full screen, the Spanish tester improvised «sigue igual» in two rounds running
(video-exit-fullscreen-unnamed__es), the agent then «fixed» a screen that was already right, and the judge scored
the product for the tester's guess. The round already knows the desktop (`canvas_now`, `card_seed.after_turn`):
it now tells the driver, once per change, as an aside the persona does not read out.
"""
from __future__ import annotations

from types import SimpleNamespace

from tests.use_cases.e2e.agent import driver as D
from tests.use_cases.e2e.agent.run import _screen_line


def _driver(locale="es"):
    d = D.Driver.__new__(D.Driver)
    d.scenario = SimpleNamespace(locale=locale)
    d.history = [{"role": "system", "content": "persona"}]
    return d


def test_the_line_names_the_open_card_and_which_one_is_at_full_screen():
    assert _screen_line(["youtube"], {"youtube"}, "es") == "abierto en la pantalla: youtube (a pantalla completa)"
    assert "nada está a pantalla completa" in _screen_line(["youtube"], set(), "es")
    assert _screen_line([], set(), "us") == "nothing is open on the screen"


def test_the_driver_is_told_once_per_change_and_never_reads_it_out():
    d = _driver()
    d.sees(_screen_line(["youtube"], {"youtube"}, "es"))
    d.sees(_screen_line(["youtube"], {"youtube"}, "es"))      # unchanged: not repeated
    d.sees(_screen_line(["youtube"], set(), "es"))
    notes = [m["content"] for m in d.history if "pantalla" in m["content"] and m["content"] != "persona"]
    assert len(notes) == 2, notes
    assert "a pantalla completa)" in notes[0] and "nada está a pantalla completa" in notes[1]
    assert all("no lo leas en voz alta" in n for n in notes)


def test_the_screen_rides_with_what_zaelar_just_said():
    """A trailing system aside was ignored by the drive model; the screen goes in the same message."""
    d = _driver()
    d.hears("Vale, hecho.")
    d.sees(_screen_line(["youtube"], set(), "es"))
    assert d.history[-1]["role"] == "user"
    assert d.history[-1]["content"].startswith("Vale, hecho.") and "nada está a pantalla completa" in d.history[-1]["content"]


def _seen(card: str, db: dict) -> str:
    """Put `db` in the card's store, then read it the way the round does: the engine's reading → the tester's line."""
    from nucleo.flash import widget_read
    from tests.use_cases.e2e.agent.run import _what_it_shows
    from widgets import store
    store.save(card, db)
    return _what_it_shows(card, widget_read.read(card))


def test_the_screen_says_what_each_open_card_shows():
    """V2-834 T15 (`watch-a-video-not-listen-to-it__us`, 2026-11-02): told only «open on the screen: youtube — nothing is
    at full screen», the US tester read a bare YouTube TAB and complained five turns running over a trailer playing in
    the card. Each open card now says what it shows — the engine's own reading of it (S1 audit H8)."""
    playing = {"videoId": "x", "title": "Dune: Part Three | Final Trailer", "channel": "Warner", "paused": False}
    got = _seen("youtube", playing)
    assert "Dune: Part Three | Final Trailer" in got and "reproduciéndose" in got, got
    assert "en pausa" in _seen("youtube", dict(playing, paused=True))
    line = _screen_line(["youtube"], set(), "us", {"youtube": "«Dune: Part Three | Final Trailer», playing"})
    assert line == "open on the screen: youtube («Dune: Part Three | Final Trailer», playing) — nothing is at full screen"
    assert _screen_line(["youtube"], {"youtube"}, "es") == "abierto en la pantalla: youtube (a pantalla completa)"


def test_a_viewer_says_which_of_its_items_is_in_front():
    """V2-834 T18 (`show-real-photo-of-a-new-car__es`): photo 4 was in the viewer, the screen said only the search title,
    and the tester kept asking for «la número 4». The brain had only the list too: the picture in front is in the digest."""
    items = [{"title": f"Ferrari Amalfi {k}", "site": "ferrari.com", "url": f"https://x/{k}.jpg"} for k in range(1, 9)]
    got = _seen("imagenes", {"title": "Ferrari Amalfi", "items": items, "i": 3})
    assert "nº 4 de 8" in got and "Ferrari Amalfi 4" in got, got
    assert "nº" not in _seen("imagenes", {"title": "Ferrari Amalfi", "items": items[:1], "i": 0}), "one item: no position"


def test_a_loaded_player_shows_its_volume():
    """V2-834 T28 — watch-a-video-not-listen-to-it__us: the volume was set to 30 and the tester, never shown it, said
    «still the same volume» for six turns; the brain's own reading had no volume either."""
    d = {"videoId": "x", "title": "Dune", "channel": "Warner", "paused": False, "volume": 30, "muted": False}
    assert "volumen 30 %" in _seen("youtube", d)
    assert "silenciado" in _seen("youtube", dict(d, muted=True))
    assert "volumen" not in _seen("youtube", {"videoId": "", "volume": 70, "search_query": "q",
                                               "search_results": [{"title": "a"}]})


def test_a_written_document_shows_its_text():
    """V2-834 T29 — docs-single-recipe-not-a-list__es: the card held the whole recipe; the tester, shown its title only,
    said «solo pone el título» four turns running and the judge scored the writes that had already landed."""
    d = {"title": "Carbonara", "body": "# RECETA\n\n## Ingredientes\n- 400 g de espagueti\n- guanciale"}
    got = _seen("documento", d)
    assert "Carbonara" in got and "400 g de espagueti" in got, got


def test_the_tester_line_is_the_engines_reading_not_a_table_of_its_own():
    """S1 audit H8: five commits taught the harness five card fields of its own. Its screen line is the engine's reading
    — one source, so a card that learns to say something new is seen by the brain and the tester together."""
    import inspect
    from tests.use_cases.e2e.agent import run
    src = inspect.getsource(run._what_it_shows)
    assert "widget_reading" in src and not any(k in src for k in ('"volume"', '"now_playing"', '"search_results"', '"body"'))


def test_the_reading_is_served_as_the_brain_reads_it():
    """The round asks the engine over HTTP; the route answers `widget_read.read`, the brain's own text, nothing else."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nucleo.flash import widget_read
    from widgets import server_api, store
    store.save("youtube", {"videoId": "x", "title": "Dune", "channel": "Warner", "paused": True, "volume": 40})
    app = FastAPI()
    app.include_router(server_api.router)
    got = TestClient(app).get("/widgets/youtube/reading").json()["reading"]
    assert got == widget_read.read("youtube") and "volumen 40 %" in got, got


def test_a_long_reading_keeps_what_the_card_shows():
    """The search band's digest opens with ~300 characters of instructions for the model; clipped at 400, the titles
    fell off and the US tester saw a blank card (video-search-lands-in-player__us, after T37). The line is never cut."""
    band = {"videoId": "", "title": "", "paused": True, "list": [], "search_query": "paella recipes",
            "search_results": [{"title": f"Paella video {k}"} for k in range(1, 7)]}
    got = _seen("youtube", band)
    assert all(f"Paella video {k}" in got for k in range(1, 7)), got
