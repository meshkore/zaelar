"""Node 2.460 — the queue's `move` reads a SLOT («first», «el primero», «al final», `position`) and «the one playing»,
and a refusal names the half that is missing — the video or the slot — in the session's language.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f): «El que está sonando ahora, ese ponlo el primero»
→ `move {position: "first", item: "1"}` refused with «Dime a qué posición (1-N) lo muevo» (the slot was the half he
HAD said); the same-turn repair's `{item: <playing title>, to: "first"}` lost again on `int("first")`. EN round, same
day: `{position: 2, item: "2"}` — `position` is the key the model reaches for in both languages.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from widgets.youtube import data as yt
from widgets.youtube import move_refs as mv

from ._video_queue_scene import queue, titles  # noqa: F401 — `queue` is a fixture

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
#: The ES round's queue at turn 5: the fourth video was playing.
ES_QUEUE = ["Diego Maradona 👑 Prime Argentina Skills, Goals, Dribbling & Tricks",
            "Opus - Live Is Life | Maradona Calentamiento 1989", "Los Goles Inolvidables de Diego Maradona",
            "Maradona - Anubiis x Hades 66 x  (Video Oficial)"]


@pytest.mark.parametrize("payload", [
    {"item": "the one playing", "position": "first"},        # the model's spelling of the slot, and the row's name
    {"item": "el que está sonando", "to": "el primero"},
    {"item": "4", "to": "al principio de la cola"},
    {"item": "sonando", "to": "top"},
])
def test_the_playing_video_goes_first_however_the_slot_is_spelled(queue, payload):
    queue(ES_QUEUE, pos=3)
    r = yt.apply_action("move", payload)
    assert r["ok"], r
    assert titles()[0] == ES_QUEUE[3]
    assert yt._load()["pos"] == 0                       # it keeps playing, now from the first slot


def test_an_end_an_ordinal_and_a_clamped_digit_are_slots(queue):
    queue(ES_QUEUE, pos=3)
    assert yt.apply_action("move", {"item": "1", "to": "al final"})["ok"]
    assert titles()[-1] == ES_QUEUE[0]
    assert yt.apply_action("move", {"item": "1", "to": "3rd"})["position"] == 3
    assert yt.apply_action("move", {"item": "1", "to": 99})["position"] == 4   # beyond the queue is its end


@pytest.mark.parametrize("payload, code", [
    ({"to": 1}, "missing_item"),                        # the VIDEO is missing: ask for it, not for the slot
    ({"item": "2"}, "missing_position"),
    ({"item": "2", "to": "la luna"}, "bad_position"),
    ({"item": "1", "to": 1}, "already_there"),          # nothing would change: refused, so the repair reads his words
    ({"item": "2", "before": "3"}, "already_there"),
])
def test_a_refusal_names_the_missing_half(queue, payload, code):
    queue(ES_QUEUE, pos=3)
    r = yt.apply_action("move", payload)
    assert r["ok"] is False and r["error"] == code, r
    assert r["say"] == f"widgets.youtube.move_{code}"
    assert titles() == ES_QUEUE


def test_every_refusal_speaks_in_both_product_languages():
    es = json.loads((_ENGINE / "i18n/bundles/es.json").read_text(encoding="utf-8"))
    en = json.loads((_ENGINE / "i18n/bundles/en.json").read_text(encoding="utf-8"))
    for code in mv._REFUSALS:
        key = f"widgets.youtube.move_{code}"
        assert es.get(key) and en.get(key), key
        assert es[key] != en[key]


def test_before_and_after_still_resolve_the_other_row(queue):
    queue(ES_QUEUE, pos=3)
    assert yt.apply_action("move", {"item": "3", "before": "2"})["ok"]
    assert titles()[1:3] == [ES_QUEUE[2], ES_QUEUE[1]]
    assert yt.apply_action("move", {"item": "1", "after": "the one playing"})["ok"]
    assert titles()[-1] == ES_QUEUE[0]
