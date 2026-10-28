"""A close that names a card closes THAT card — by its name or by its place on the canvas (V2-781, second round).

Measured in `tres-tarjetas-y-el-video-por-alusion` (ES+EN, 2026-10-10), with the trailer (`youtube`), the music
(`musica`) and the agenda open:

  · EN «Close the music actually.» → the model called nothing («Done.»); canvas verdict `close` 0.99, screen verdict
    `youtube:close` 0.54. The text channel ran the promise repair before the canvas gesture and the repair took the
    screen verdict's card: `youtube:close` emptied the player, the music kept playing, no card left.
  · EN «Actually close the top one too.» → `youtube:close` again, by card mass, over an unsure verdict.
  · ES «cierra la música, que ya está bien de fondo» → `play_music {stop}` → «Pausado.», twice.

These drive the real decisions (the shared `complete_canvas` and the turn's close backstop over a music call) with
the brief shape `jev.ask_many` hands over, and measure the neighbourhood: «close the
calendar», «close the video» (V2-753: the player's content, not a card name), «apaga la música» (= stop the audio),
«pausa la música y cierra la agenda» (two orders), a place on a canvas whose geometry is unknown (asked).
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import card_close as CC
from nucleo.flash import direct_action as DA

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
    """What is on the canvas — the instances the desktop reported, the normalised state, and its layout."""
    import server.voice_api as _va
    from memory import api as _memapi
    box = {"open": list(THREE), "layout": None}
    monkeypatch.setattr(_va, "open_instances", lambda: list(box["open"]))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(box["open"])})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: box["layout"] if k == "canvas_layout" else None)
    return box


def _layout(**tops) -> dict:
    return {"at": 1, "items": [{"id": w, "left": "40", "top": str(t)} for w, t in tops.items()]}


def _gesture(brief, text: str) -> list:
    tags = []
    DA.complete_canvas(brief, tag_emit=lambda a, x: tags.append((a, x.get("id"))), emit=lambda *a, **k: None,
                       operator_text=text)
    return tags


# ── the shared canvas gesture (the turn's `complete_canvas`) ────────────────────────────────────────────────

def test_close_the_music_closes_the_music_over_a_verdict_naming_the_video(screen):
    assert _gesture(_brief("youtube:close"), "Nice, free Thursday. Close the music actually.") == [("close", "musica")]


def test_cierra_la_musica_closes_the_music_over_a_verdict_naming_the_video(screen):
    assert _gesture(_brief("youtube:close"), "Vale, cierra la música, que ya está bien de fondo.") == [("close", "musica")]


def test_close_the_calendar_and_close_youtube_close_the_card_they_name(screen):
    assert _gesture(_brief("youtube:close"), "close the calendar") == [("close", "agenda")]
    assert _gesture(_brief("youtube:close", 0.95), "close youtube") == [("close", "youtube")]


def test_close_the_video_keeps_the_verdicts_card(screen):
    """«video» is what the player HOLDS, not what the card is called: no other card is named, the verdict stands."""
    assert _gesture(_brief("youtube:close", 0.95), "close the video") == [("close", "youtube")]


def test_the_top_one_is_the_card_at_the_top_of_the_layout(screen):
    screen["open"] = ["youtube", "agenda"]
    screen["layout"] = _layout(youtube=420, agenda=40)
    assert _gesture(_brief("youtube:close", 0.36, open_ids=screen["open"]), "Actually close the top one too.") \
        == [("close", "agenda")]
    screen["layout"] = _layout(youtube=40, agenda=420)
    assert _gesture(_brief("", open_ids=screen["open"]), "cierra la de arriba") == [("close", "youtube")]


def test_a_place_reads_only_as_a_place():
    for text in ("all right, close it", "that's right", "close the first one", "put it on top of the list", "close it"):
        assert CC.place_named(text) == "", text
    assert CC.place_named("Actually close the top one too.") == "top"
    assert CC.place_named("quita la de la derecha") == "right"


# ── a player's stop dressed as «close the music» (the turn's close backstop over a `play_music` call) ──────────

@pytest.mark.parametrize("text", [
    "Vale, gracias. Oye, cierra la música, que ya está bien de fondo.",
    "No, la música — ciérrala, no la pauso. Y el tráiler si lo habías pausado antes ya está bien, la música fuera del todo.",
    "close the music",
])
def test_a_stop_of_the_music_his_words_close_is_the_cards_close(screen, text):
    req = {"v": {"action": "stop", "query": ""}}
    assert CC.music_keeps_its_turn(req, text) is False and req["v"] is None, (text, req)


@pytest.mark.parametrize("text", [
    "apaga la música",                         # stops the audio: the documented broad-verb rule
    "turn off the music",
    "pausa la música y cierra la agenda",     # two cards, two orders
    "stop the music",
    "no cierres la música, solo páusala",     # a negated close
])
def test_a_stop_that_is_not_a_card_close_stays_a_stop(screen, text):
    req = {"v": {"action": "stop", "query": ""}}
    assert CC.music_keeps_its_turn(req, text) is True and req["v"]["action"] == "stop", (text, req)


def test_the_voice_close_backstop_is_not_held_by_the_stop_it_replaces(screen):
    req = {"v": {"action": "stop", "query": ""}}
    assert CC.music_keeps_its_turn(req, "cierra la música") is False and req["v"] is None
    req = {"v": {"action": "stop", "query": ""}}
    assert CC.music_keeps_its_turn(req, "apaga la música") is True and req["v"]["action"] == "stop"
    assert CC.music_keeps_its_turn({"v": None}, "cierra la música") is False
