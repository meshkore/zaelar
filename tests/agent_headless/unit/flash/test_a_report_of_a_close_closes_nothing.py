"""An unnamed short close takes the only card only when the landed brief SURELY says close (demo, 2026-10-22).

The STT split «Yes, please. I did close the results a long time ago» and the turn began on «please. I I did
close.» — a report, not an order. The brief had landed UNSURE (canvas 0.52, request_type complaint), the model
called nothing, and the backstop closed his only open card because the sentence was short.
"""
from __future__ import annotations

import pathlib
import threading

from nucleo.flash import close_guards as _cg, turn_brief as _tb

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
OPEN = ["results::48ac70-3"]


def _brief(verb: str, conf: float):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {_tb.CANVAS_KEY: {"choice": verb, "confidence": conf}}}


def test_an_unsure_landed_verdict_closes_nothing():
    assert _cg.the_only_card("please. I I did close.", OPEN, brief=_brief("close", 0.52)) is None


def test_a_sure_close_still_takes_the_only_card():
    assert _cg.the_only_card("close it", OPEN, brief=_brief("close", 0.97)) == OPEN[0]


def test_a_brief_that_never_landed_keeps_the_engine_hearing_close_it():
    pending = {"event": threading.Event(), "turn_id": "t-1", "open_ids": [], "result": {}}
    assert _cg.the_only_card("close it", OPEN, brief=pending) == OPEN[0]
    assert _cg.the_only_card("close it", OPEN) == OPEN[0]


def test_the_length_and_single_card_bounds_still_hold():
    sure = _brief("close", 0.99)
    assert _cg.the_only_card("close it", OPEN + ["agenda"], brief=sure) is None
    assert _cg.the_only_card("please close that thing I opened this morning for me", OPEN, brief=sure) is None


def test_the_voice_turn_uses_it():
    src = (_ENGINE / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    assert "the_only_card(" in src and "is_short_order(text) and len(" not in src
