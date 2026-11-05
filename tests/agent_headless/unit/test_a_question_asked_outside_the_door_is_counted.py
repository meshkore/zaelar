"""V2-851 F2c — the door is the one reader of «which person / which channel / missing fact».

A turn that ends on our own question while the brief names a card whose acts leave the machine, and no call reached
any door, asked OUTSIDE the door: nothing retained, no durable question. It is counted as one `ask_outside_door`
event (never repaired — no second model pass), and the send's declaration tells the model the door asks.
"""
from __future__ import annotations

from tests.voice_turn_source import read as _vts_read

import ast
import json
from pathlib import Path

import pytest

from nucleo.request import ask_outside_door as aod
from nucleo.turn import verdicts

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def card(monkeypatch):
    def _set(wid):
        monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                            (wid, {"confidence": .9}) if key == "catalog_widget" else (fb, None))
    return _set


def _measure(reply, *, did_act=False, which=False):
    got = []
    ok = aod.measure(object(), reply, did_act=did_act, asked_which=which,
                     emit=lambda kind, label, text="", role="", extra=None: got.append((kind, extra)))
    return ok, got


def test_a_question_about_a_send_that_reached_no_door_is_counted(card):
    card("mensajeria")
    ok, got = _measure("¿A qué Raquel: Gómez o Martín?")
    assert ok and got[0][0] == aod.KIND and got[0][1]["widget"] == "mensajeria" and "send_to" in got[0][1]["leaves"]


def test_a_turn_that_reached_a_door_or_did_not_ask_is_not(card):
    card("mensajeria")
    assert _measure("¿A qué Raquel?", did_act=True) == (False, [])
    assert _measure("Se lo mando ahora.") == (False, [])
    assert _measure("Raquel Gómez o Raquel Martín.", which=True)[0], "the directory says it asked which person"


def test_a_card_whose_acts_never_leave_is_not_a_door_question(card):
    card("none")
    assert _measure("¿Qué quieres?") == (False, [])


def test_the_turn_end_measures_it_and_the_kind_has_a_family():
    src = _vts_read(ROOT / "nucleo/turn/pipeline_close.py")
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "measure" and getattr(n.func.value, "id", "") == "_aod"]
    assert calls and {k.arg for k in calls[0].keywords} >= {"did_act", "asked_which", "emit"}
    from voice import observer
    assert observer._CAT.get(aod.KIND) == "flash"


def test_the_send_declares_that_the_door_asks_which():
    spec = json.loads((ROOT / "widgets/mensajeria/manifest.json").read_text())["actions"]["send_to"]
    assert "PREGÚNTASELO" not in spec["usage"], "the declaration no longer tells the model to ask on its own"
    assert "la tarjeta le pregunta" in spec["usage"]
