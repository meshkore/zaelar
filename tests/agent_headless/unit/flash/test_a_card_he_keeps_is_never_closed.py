"""A card his sentence tells to STAY is never closed (V2-781, `tres-tarjetas-y-el-video-por-alusion__us` t7, 2026-10-11).

The trailer on `youtube` and the agenda open, «ok cool. now get rid of the video too, just keep the calendar up»: the
verdict read `youtube:close` 1.00, and the CALENDAR closed — the only card the sentence named by name was the one it
said to keep, so `card_close.verdict_unless_named` let the name win. `naming.split_kept` takes the keep / leave / deja
/ mantén / don't-close / except clauses out of the words every close reader reads, and a kept card is dropped from
every close site's targets (the verdict gesture, `also_named`, `with_also_named`, the `close_widget` tool).
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


@pytest.mark.parametrize("text, kept, close_words_keep", [
    ("ok cool. now get rid of the video too, just keep the calendar up", "the calendar", "the video"),
    ("Quita eso y deja la música. Y ya de paso, ¿qué tengo el jueves?", "la música", "eso"),
    ("No, el vídeo, la música déjala.", "la música", "el vídeo"),
    ("close everything except the calendar", "the calendar", "close everything"),
    ("close the music but don't close the video", "the video", "close the music"),
])
def test_a_clause_that_keeps_a_card_is_split_out_of_the_close_words(text, kept, close_words_keep):
    from widgets import naming
    close_words, kept_words = naming.split_kept(text)
    assert kept in kept_words and kept not in close_words
    assert close_words_keep in close_words


@pytest.mark.parametrize("text", ["close the calendar and the messages", "cierra la música, que ya está bien de fondo",
                                  "deja de poner música y cierra la agenda", "don't leave the music on, close it"])
def test_an_order_with_no_keep_clause_keeps_all_its_words(text):
    from widgets import naming
    assert naming.split_kept(text) == (text, "")


def test_keep_the_calendar_up_closes_the_video_not_the_calendar(screen):
    screen["open"] = ["agenda", "youtube"]
    b = _brief("youtube:close", 1.0, open_ids=["agenda", "youtube"])
    assert _gesture(b, "ok cool. now get rid of the video too, just keep the calendar up") == [("close", "youtube")]


def test_a_verdict_on_the_kept_card_never_closes_it(screen):
    screen["open"] = ["agenda", "youtube"]
    b = _brief("agenda:close", 0.6, open_ids=["agenda", "youtube"])
    assert ("close", "agenda") not in _gesture(b, "get rid of the video too, just keep the calendar up")


def test_close_one_and_keep_the_other_closes_only_the_one(screen):
    b = _brief("youtube:close", 0.6)
    assert _gesture(b, "close the calendar and keep the video") == [("close", "agenda")]


def test_the_other_close_sites_drop_the_kept_card(screen):
    from widgets import instances
    from voice.engine.llm.providers import widget_intent
    from nucleo.flash import show_target
    text = "close the music, keep the calendar up"
    assert instances.also_named(text, THREE) == ["musica"]
    assert instances.kept_named(text, THREE) == ["agenda"]
    assert widget_intent.with_also_named(["agenda"], text) == ["musica"]
    tags = []
    show_target.close_dispatch({"widget_id": "musica"}, lambda a, x: tags.append(x["id"]), lambda *a, **k: None,
                               text=text)
    assert tags == ["musica"]
