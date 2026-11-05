"""V2-851 F2c — battery C6 «wrong channel»: the channel HE named reaches the send door, whatever the model's call says.

Measured: «send Lucía a WhatsApp» (she has Telegram and mail) — one language's call carried `channel: whatsapp` and the
door refused; the other's carried none, the door read «none» as «her preferred one», and a Telegram message left.
The brief carries one declared question (his channel among the declared platforms, or none); a sure reading puts it
in the call of any action with a `channel` slot, and the door decides as always. No word of his is matched here.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nucleo.acts import message_channel as mc
from nucleo.turn import brief, verdicts

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def his(monkeypatch):
    def _set(choice, conf=.9):
        monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None:
                            (choice, {"confidence": conf}) if key == mc.KEY else (fb, None))
    return _set


def test_a_sure_reading_puts_his_channel_into_a_call_that_lost_it(his):
    his("whatsapp")
    got = mc.his_channel("mensajeria", "send_to", {"contact": "Lucía", "text": "x"}, object())
    assert got["channel"] == "whatsapp"
    got = mc.his_channel("mensajeria", "send_to", {"contact": "Lucía", "text": "x", "platform": "telegram"}, object())
    assert got["channel"] == "whatsapp" and "platform" not in got


def test_none_a_doubt_or_no_channel_slot_leave_the_call_alone(his):
    pl = {"contact": "Lucía", "text": "x"}
    his("none")
    assert mc.his_channel("mensajeria", "send_to", pl, object()) is pl
    his(None)
    assert mc.his_channel("mensajeria", "send_to", pl, object()) is pl
    his("whatsapp")
    assert mc.his_channel("agenda", "add", {"title": "x"}, object()) == {"title": "x"}


def test_the_door_refuses_the_channel_she_does_not_have():
    from widgets.mensajeria.outbound import targets
    assert "whatsapp" in targets.PLATFORMS
    q = mc.question()
    assert set(q["criteria"]) == set(targets.PLATFORMS) | {mc.NONE}


def test_the_brief_asks_it_and_the_data_op_door_applies_it():
    assert mc.KEY in brief.keys()
    src = (ROOT / "nucleo/flash/tool_executor_widget_calls.py").read_text()
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "his_channel"]
    assert calls, "the widget data door puts his channel into the call"
