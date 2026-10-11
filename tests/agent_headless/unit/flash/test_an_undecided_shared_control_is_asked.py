"""A shared control nobody settled is ASKED, never completed by the engine (V2-781, `tres-tarjetas…__us` t2/t4).

Two players open, both declaring `volume_down` and `pause`. «hey, turn the volume down a bit»: the turn asked «Which one
exactly?» and the text channel's verdict rung (`direct_action.resolve`) turned the music down anyway on a 0.78 verdict,
saying «Done.». «ok leave it. pause that for a sec»: the model asked «Which one — the music or the Dune trailer?» and the
rung paused the video on 0.67. The text channel's own `widget_data` path never asked at all: it passed `which_card` no
brief and no screen. Now the rung leaves a turn that asked, or a shared control the verdict did not settle
(`undecided`), the players' bar (`PLAYER_SURE`) holds on the `widget_data` path, and the probe SAYS its question.
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


def test_the_text_channel_asks_and_says_the_question():
    src = (ENGINE / "nucleo/flash/probe_decide.py").read_text(encoding="utf-8")
    assert "brief=_tbrief, ask_phrase=_player_control._ask_phrase())" in src
    assert 'action, spoken = "clarify", _cd["ask"]' in src
    mirrors = (ENGINE / "nucleo/flash/probe_mirrors.py").read_text(encoding="utf-8")
    assert '"answer_worker", "clarify"))' in mirrors, "a turn that ASKED is decided: no rung, no backstop completes it"
