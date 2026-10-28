"""Node 2.452 — an empty turn under the `youtube:move` verdict runs the move it can fill, in both channels.

Video-queue use case, regression sweep of 2026-10-11 (engine 3.36+2a5bd83c): «the third one before the second» (EN) —
verdict `youtube:move` 1.00, no call, «Done — Most Creative is now ahead of Los Goles» over an untouched queue; «cambia
el orden: el de skills ponlo antes que el de creative» (ES) — verdict split, a Brain Worker for ~100 s to swap two rows.
The green runs the day before were luck (the model happened to call `move {item: 2, to: 2}`).
"""
from __future__ import annotations

import pathlib

from nucleo.flash import direct_action as _da
from nucleo.flash import turn_brief as _tb
from widgets.youtube import data as yt

from ._video_queue_scene import EN_CLAIM, EN_QUEUE, EN_SAID, brief, queue, titles  # noqa: F401

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def test_the_verdict_completes_an_empty_reorder_turn_end_to_end(queue, monkeypatch):
    queue(EN_QUEUE, pos=1)
    monkeypatch.setattr(_tb, "owner_still_open", lambda _b, _o: True)
    b = brief({_tb.TARGET_KEY: ("youtube:move", 1.0), _tb.REQUEST_KEY: ("order", 1.0)})
    rung = _da.resolve(EN_SAID, brief=b, operator_text=EN_SAID, model_words=EN_CLAIM)
    assert rung and rung["action"] == "move" and rung["payload"] == {"item": "3", "before": "2"}, rung
    assert rung["source"] == "said-order"
    assert yt.apply_action(rung["action"], rung["payload"])["ok"]
    assert titles()[1:3] == [EN_QUEUE[2], EN_QUEUE[1]]


def test_the_voice_turn_hands_the_models_words_to_the_rung():
    voice = (_ENGINE / "nucleo/flash/post_stream_acts.py").read_text(encoding="utf-8")
    assert "model_words=spoken_text" in voice
