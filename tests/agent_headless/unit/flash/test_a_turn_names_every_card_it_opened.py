"""A turn that opened several cards names each of them (V2-781, `tres-tarjetas-y-el-video-por-alusion` ES t0).

«Ponme el tráiler de Dune, y de fondo algo de música tranquila. Ah, y ábreme la agenda…» opened all three cards and the
reply said «Voy con el tráiler y la música.» — he had to ask for the agenda. A reply that names some of the turn's
cards gets the ones it skipped; one that names none of them («I'll get all three going») already speaks for all.
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


def test_a_reply_that_names_none_of_them_speaks_for_all(screen, english):
    acts = [("youtube", CR.SHOW, "play"), ("musica", CR.SHOW, "play"), ("agenda", CR.SHOW, "show_widget")]
    assert CR.complete("I'll get all three going.", acts) == "I'll get all three going."
