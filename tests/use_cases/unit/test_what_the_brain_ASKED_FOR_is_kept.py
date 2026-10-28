"""The harness threw away what the brain ASKED FOR on each turn (V2-398).

`POST /api/flash/say` returns, measured against the actual shape of the `return` from `nucleo/flash/probe.py`:

    {"reply": …, "action": "…", "tool_calls": [{"name": …, "args": …}], "executed": …, "trace": …}

and `run.py` kept **only `reply`**. Everything else was lost the instant it arrived.

The cost of that was seen in `play-music-and-build-playlist` (2026-08-27 15:23). The user asked for TWO things
in one sentence —«actually play it **and** save it to a playlist called Curro»— and zaelar replied «Volume
at 85 percent». The judge wrote the finding «increased the volume **instead of** saving the song»,
**deducing it from the response text**, because there was nothing else to inspect: `audit.tools_run` was
`{}` and `widget_ops` only contains the AGGREGATE for the entire round.

And that deduction is precisely what V2-394 showed cannot be done: «asked for A instead of B» and «asked for A and B,
and the widget silently rejected B» read the same in the transcript and have two different owners. The data that
distinguishes them was in the harness's hand, and it threw it away.
"""
from tests.use_cases.e2e.agent import judge as J


def _texto(x) -> str:
    return x if isinstance(x, str) else "\n".join(x)


def test_el_juez_ve_lo_que_pidio_el_cerebro_turno_a_turno():
    txt = _texto(J.mechanism_facts({"turn_actions": [
        {"turn": 0, "pedido": ["play_music"], "action": "play_music"},
        {"turn": 1, "pedido": ["set_volume"], "action": "set_volume"},
    ]}))
    assert "PIDIÓ EL CEREBRO" in txt
    assert "play_music" in txt and "set_volume" in txt


def test_un_turno_que_no_pidio_NADA_se_ve_como_tal():
    """«Asked for no tool at all» and «asked for one that failed» are two opposite facts."""
    txt = _texto(J.mechanism_facts({"turn_actions": [{"turn": 0, "pedido": [], "action": "chat"}]}))
    assert "PIDIÓ EL CEREBRO" in txt
    # The marker is ATTACHED to the turn. Searching for a standalone «(ninguna)» was not enough: another section
    # of the same report already prints it, so the guard passed in green with the marker removed from this line.
    assert "t0→(ninguna)" in txt


def test_lo_que_se_EJECUTO_se_dice_aparte_de_lo_que_se_pidio():
    """Asking is not doing: that is the entire boundary of V2-394."""
    txt = _texto(J.mechanism_facts({"turn_actions": [
        {"turn": 0, "pedido": ["widget_data"], "action": "widget_data", "ejecutado": "musica"}]}))
    assert "ejecutó" in txt and "musica" in txt


def test_sin_el_dato_el_juez_no_se_lo_inventa():
    txt = _texto(J.mechanism_facts({"results_sheet": {"n_named": 3}}))
    assert "PIDIÓ EL CEREBRO" not in txt


def test_an_order_the_action_map_ran_is_shown_as_acted_not_as_nothing():
    """video-exit-fullscreen-unnamed__es (2026-10-27): the map took the card out of full screen with no model, and
    the judge, shown «t0→(ninguna)», scored «claimed success without acting»."""
    txt = _texto(J.mechanism_facts({"turn_actions": [
        {"turn": 0, "pedido": [], "action": "canvas:unfullscreen", "mapa": True, "ejecutado": "canvas:unfullscreen"}]}))
    assert "t0→(mapa de acciones, sin modelo) [ejecutó canvas:unfullscreen]" in txt
    assert "t0→(ninguna)" not in txt
