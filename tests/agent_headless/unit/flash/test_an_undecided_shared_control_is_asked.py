"""A shared control nobody settled is ASKED, never completed by the engine (V2-781, `tres-tarjetas…__us` t2/t4).

Two players open, both declaring `volume_down` and `pause`. «hey, turn the volume down a bit»: the turn asked «Which one
exactly?» and the text channel's verdict rung (`direct_action.resolve`) turned the music down anyway on a 0.78 verdict,
saying «Done.». «ok leave it. pause that for a sec»: the model asked «Which one — the music or the Dune trailer?» and the
rung paused the video on 0.67. The text channel's own `widget_data` path never asked at all: it passed `which_card` no
brief and no screen. Now the rung leaves a turn that asked, or a shared control the verdict did not settle
(`undecided`), the players' bar (`PLAYER_SURE`) holds on the `widget_data` path.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nucleo.flash import direct_action as DA

ENGINE = Path(__file__).resolve().parents[4]
THREE = ["youtube", "musica", "agenda"]


def _brief(screen: str = "", screen_conf: float = 0.54, canvas: str = "close", canvas_conf: float = 0.99,
           open_ids=THREE) -> dict:
    ev = threading.Event()
    ev.set()
    res = {}
    if screen:
        res["screen_action"] = {"choice": screen, "confidence": screen_conf}
    if canvas:
        res["canvas"] = {"choice": canvas, "confidence": canvas_conf}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": res}


@pytest.fixture
def screen(monkeypatch):
    import server.voice_api as _va
    from memory import api as _memapi
    box = {"open": list(THREE)}
    monkeypatch.setattr(_va, "open_instances", lambda: list(box["open"]))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(box["open"])})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: None)
    from nucleo import canvas_focus
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "")
    return box


@pytest.fixture
def english(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")


@pytest.fixture
def spanish(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")


def _gesture(brief, text: str) -> list:
    tags = []
    DA.complete_canvas(brief, tag_emit=lambda a, x: tags.append((a, x.get("id"))), emit=lambda *a, **k: None,
                       operator_text=text)
    return tags


def test_two_players_need_a_sure_verdict_on_the_widget_data_path(screen):
    from nucleo.flash import frontend as FE
    assert FE.which_card("musica", "volume_down", brief=_brief("musica:volume_down", 0.78, canvas=""))[0] == "ask"
    assert FE.which_card("musica", "volume_down", brief=_brief("musica:volume_down", 0.92, canvas=""))[0] == "keep"


def test_the_screen_stands_in_for_a_brief_without_its_open_set(screen):
    from nucleo.flash import frontend as FE
    assert FE.which_card("youtube", "pause", brief=None)[0] == "ask"


def test_the_rung_never_completes_a_turn_that_asked(screen):
    screen["open"] = ["youtube"]                       # one player: nothing shared, only the question holds the rung
    b = _brief("youtube:pause", 0.67, canvas="neither", canvas_conf=0.85, open_ids=["youtube"])
    assert DA.resolve("ok leave it. pause that for a sec", brief=b, operator_text="ok leave it. pause that for a sec",
                      model_words="Which one — the music or the Dune trailer?") == {}


def test_the_rung_never_settles_a_shared_control_on_an_unsure_verdict(screen):
    b = _brief("musica:volume_down", 0.78, canvas="neither", canvas_conf=1.0)
    assert DA.resolve("hey, turn the volume down a bit", brief=b, operator_text="hey, turn the volume down a bit") == {}


def test_a_named_card_or_a_sure_verdict_still_completes(screen):
    b = _brief("musica:volume_down", 0.78, canvas="neither", canvas_conf=1.0)
    assert DA.resolve("turn the music down a bit", brief=b, operator_text="turn the music down a bit")["widget"] == "musica"
    sure = _brief("musica:volume_down", 0.95, canvas="neither", canvas_conf=1.0)
    assert DA.resolve("turn it down", brief=sure, operator_text="turn it down")["widget"] == "musica"


def test_a_question_the_verdict_is_sure_enough_to_answer_does_not_hold_the_order(screen):
    """2026-10-15, the operator's threshold («en un 70% continuamos»). Live bench E3: «…should I go ahead?» over an
    order read at 1.00 and `mensajeria:forward` at 0.77 — nothing was sent in 2 runs of 7. A question holds the rung
    only while the verdict is under `consent.intent_act_at`; the 0.67 case above still asks."""
    from nucleo.flash import undecided
    screen["open"] = ["mensajeria"]
    sure = _brief("mensajeria:forward", 0.77, canvas="neither", canvas_conf=1.0, open_ids=["mensajeria"])
    sure["result"]["request_type"] = {"choice": "order", "confidence": 1.0}
    asked = "Here's what I'd send Quinn — should I go ahead?"
    assert undecided.why(sure, "mensajeria", "forward", operator_text="send the invoice to quinn", model_words=asked) == ""
    unsure = _brief("mensajeria:forward", 0.62, canvas="neither", canvas_conf=1.0, open_ids=["mensajeria"])
    unsure["result"]["request_type"] = {"choice": "order", "confidence": 1.0}
    assert undecided.why(unsure, "mensajeria", "forward", operator_text="send the invoice to quinn",
                         model_words=asked) == "asked"
    remark = _brief("mensajeria:forward", 0.9, canvas="neither", canvas_conf=1.0, open_ids=["mensajeria"])
    remark["result"]["request_type"] = {"choice": "question", "confidence": 0.95}
    assert undecided.why(remark, "mensajeria", "forward", operator_text="did quinn get it?", model_words=asked) == "asked"


def test_a_sure_order_repairs_over_a_question(screen):
    """Live bench E3 (2026-10-15): «…what should the message say exactly?» over order 1.00 and `forward` 0.75 — the
    promise repair stood down on any question, and nothing was sent. The question holds the repair
    only under the operator's bar (`undecided.a_question_holds`)."""
    from nucleo.flash import undecided
    screen["open"] = ["mensajeria"]
    asked = "I can send Quinn an email, but before I do — what should the message say exactly?"
    sure = _brief("mensajeria:forward", 0.75, canvas="neither", canvas_conf=1.0, open_ids=["mensajeria"])
    sure["result"]["request_type"] = {"choice": "order", "confidence": 1.0}
    unsure = _brief("mensajeria:forward", 0.55, canvas="neither", canvas_conf=1.0, open_ids=["mensajeria"])
    unsure["result"]["request_type"] = {"choice": "order", "confidence": 1.0}
    assert undecided.a_question_holds(sure, asked) is False
    assert undecided.a_question_holds(unsure, asked) is True
    assert undecided.a_question_holds(None, asked) is True
    assert undecided.a_question_holds(sure, "Sending it now.") is False
    import inspect
    from nucleo.turn import split_by_errand
    assert "_und.a_question_holds(brief, spoken)" in inspect.getsource(split_by_errand.holds_the_repair)
    assert "holds_the_repair(spoken_text, _op_text, _brief)" in (ENGINE / "nucleo/flash/post_stream_acts.py").read_text()
