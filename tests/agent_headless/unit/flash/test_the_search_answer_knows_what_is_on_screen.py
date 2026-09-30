from tests import voice_turn_source as _vts
"""The web-search answer knows what this turn put on screen (demo pass 2026-09-28, M1).

«how's apple stock doing today, show me the chart» → the Markets chart of Apple opened, AND a web search ran; the
pass that composes the answer from the results could not see the chart and said «I'm not able to display a chart
here; I can only talk» — and the next two turns repeated that false limit.
"""
from nucleo import canvas_focus as cf
from nucleo.flash import search_turn as st


def test_the_cards_of_this_turn_reach_the_search_answer():
    cf._reset()
    cf.note("transcript", "", role="user")
    cf.note("widget", "show", extra={"id": "markets", "src": "flash"})
    cf.note("widget", "data:show", extra={"id": "markets", "src": "flash"})
    assert cf.this_turn_cards() == ["markets"]
    sys2 = st.compose_system("how's apple stock doing today, show me the chart", "AAPL price today",
                             {"results": [{"title": "x"}]}, "x", on_screen=cf.this_turn_cards())
    assert "EN PANTALLA" in sys2 and "markets" in sys2
    cf._reset()


def test_nothing_on_screen_adds_nothing():
    assert "EN PANTALLA" not in st.compose_system("q", "q", {"results": [{"title": "x"}]}, "x", on_screen=[])


def test_both_channels_pass_it():
    import inspect
    from nucleo.flash import probe
    from voice.engine.llm.providers import nucleo as prov
    assert "on_screen=_cf_s.this_turn_cards()" in _vts.turn_source()
    assert "on_screen=_cf_s.this_turn_cards()" in inspect.getsource(probe)
