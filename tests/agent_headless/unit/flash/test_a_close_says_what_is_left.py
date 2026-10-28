"""A close says what closed and what is left; a shared control names its card (V2-781, `tres-tarjetas…` ES t5, EN t2-t7).

ES t5: the video closed and the reply spoke only of the music and of Thursday — he asked twice more whether it was gone.
EN t6/t7: «Done.» over two closes, so closing the wrong card went unseen. ES t2: «Vale.» over a volume change with two
players open. `card_receipt` completes the reply from what the turn RAN: the closed cards and what is still on screen,
the card a shared control ran on; a reply that already says it is left alone, a content-free one is replaced.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nucleo.flash import card_receipt as CR
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


def test_a_bare_done_over_a_close_says_what_closed_and_what_is_left(screen, english):
    out = CR.complete("Done.", [("musica", CR.CLOSE, "close")])
    assert out == "I've closed Music. Still on screen: YouTube and Calendar."


def test_a_reply_that_already_says_it_all_is_left_alone(screen, english):
    reply = "I've closed the music; the video and the calendar are still up."
    assert CR.complete(reply, [("musica", CR.CLOSE, "close")]) == reply


def test_a_shared_control_names_its_card(screen, spanish):
    assert CR.complete("Vale.", [("musica", CR.CONTROL, "volume_down")]) == "Hecho en Música."
    screen["open"] = ["musica", "agenda"]
    assert CR.complete("Vale.", [("musica", CR.CONTROL, "volume_down")]) == "Vale.", "one player: nothing to tell apart"

