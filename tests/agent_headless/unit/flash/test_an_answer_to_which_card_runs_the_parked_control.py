"""An answer to our own «which card?» runs the parked control on the card it names (V2-781, ES/EN rounds 2026-10-11).

«Bájale un poco, que está muy alto» (both players open) → «¿Cuál exactamente? Tengo Música, YouTube.» — right. Then
«El de la música, el vídeo déjalo» → the SAME question again (ES t2), and «The video, the trailer. Leave the music.» →
the same question again (EN t4). The ask now PARKS the control (`named_target.park`, from `card_decision`'s ask branch),
and the next turn's words that name one of the asked cards resume it: through the text channel's verdict rung
(`direct_action.resolve`) even when the model called nothing and the brief holds no verdict. One shot: whatever he says
next consumes the park.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo.flash import direct_action as DA
from nucleo.acts import named_target as NT

BOTH = ["youtube", "musica"]


def _brief(screen: str = "", conf: float = 0.5, open_ids=BOTH) -> dict:
    ev = threading.Event()
    ev.set()
    res = {"screen_action": {"choice": screen, "confidence": conf}} if screen else {}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": res}


@pytest.fixture(autouse=True)
def clean_park(monkeypatch):
    NT._PARKED.clear()
    from memory import api as _memapi
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(BOTH)})
    yield
    NT._PARKED.clear()


def test_the_ask_parks_the_control_with_the_cards_it_offered():
    from nucleo.flash import frontend as FE
    cd = FE.card_decision("musica", "volume_down", brief=_brief(), ask_phrase="Which one? {cands}")
    assert cd["ask"], cd
    assert NT.parked()["action"] == "volume_down" and set(NT.parked()["cards"]) == set(BOTH)


@pytest.mark.parametrize("text,card", [
    ("El de la música, el vídeo déjalo.", "musica"),
    ("The video, the trailer. Leave the music.", "youtube"),
    ("la de fondo, la música", "musica"),
])
def test_the_answer_runs_the_parked_control_on_the_named_card(text, card):
    NT.park("volume_down", BOTH)
    rung = DA.resolve(text, brief=_brief(), operator_text=text)       # no verdict at all in the brief
    assert rung and rung["widget"] == card and rung["action"] == "volume_down" and rung["payload"] == {}, rung
    assert rung["source"] == "parked-answer"
    assert not NT.parked(), "one shot: the park is consumed"


def test_an_answer_that_names_no_asked_card_runs_nothing_and_still_consumes_the_park():
    NT.park("volume_down", BOTH)
    assert NT.parked_answer("what do I have on Thursday?") == ("", "")
    assert not NT.parked()
    assert DA.resolve("what do I have on Thursday?", brief=_brief(), operator_text="what do I have on Thursday?") == {}


def test_a_stale_park_is_not_an_answer():
    NT.park("pause", BOTH)
    NT._PARKED["at"] = time.monotonic() - NT._PARK_TTL_S - 1
    assert NT.parked_answer("the video") == ("", "")


def test_the_excluded_card_never_takes_the_parked_control():
    NT.park("volume_down", BOTH)
    assert NT.parked_answer("No, en YouTube no: bájale a la música, el vídeo no lo toques.") == ("musica", "volume_down")
