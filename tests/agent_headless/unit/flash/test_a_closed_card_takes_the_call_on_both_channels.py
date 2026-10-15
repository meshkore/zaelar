"""A commission the CLOSED catalogue card can do is that card's call on BOTH channels (V2-252 parity, 2026-10-15).

Live bench, «send rowan a telegram with the new time» with the messages card closed: 4/7 — the three reds escalated
a two-field send to a worker. The voice channel had `card_commission.before_worker`; the text channel (the probe,
which the bench and a chat-only operator drive) had only the OPEN-card half. The decision is now one function,
`commission_call`, and each channel carries it out its own way.
"""
import asyncio
from pathlib import Path

from nucleo.flash import card_commission as cc

ROOT = Path(__file__).resolve().parents[4]


def test_a_call_is_recorded_as_the_turns_repaired_widget_data(monkeypatch):
    async def _call(*_a, **_k):
        return {"kind": "call", "widget_id": "mensajeria", "action": "send_to",
                "payload": {"contact": "Rowan", "text": "see you at 4:30", "channel": "telegram"}}
    monkeypatch.setattr(cc, "commission_call", _call)
    calls = []
    assert asyncio.run(cc.probe_instead_of_a_worker(calls, "send rowan a telegram", brief=None,
                                                    operator_text="send rowan a telegram", spec=None))
    assert calls == [{"name": "widget_data", "args": {"widget_id": "mensajeria", "action": "send_to",
                      "payload": {"contact": "Rowan", "text": "see you at 4:30", "channel": "telegram"},
                      "_repair": True}}]


def test_a_read_or_nothing_keeps_the_errand(monkeypatch):
    for got in ({"kind": "read", "widget_id": "agenda", "question": "q"}, None):
        async def _got(*_a, _g=got, **_k):
            return _g
        monkeypatch.setattr(cc, "commission_call", _got)
        calls = []
        assert not asyncio.run(cc.probe_instead_of_a_worker(calls, "x", brief=None, operator_text="x", spec=None))
        assert calls == []


def test_both_channels_ask_the_same_decision():
    probe = (ROOT / "nucleo/flash/probe.py").read_text("utf-8")
    assert ".probe_escalation(" in probe, "the text channel's escalation passes through the card first"
    voice = (ROOT / "nucleo/flash/card_commission.py").read_text("utf-8")
    esc = voice[voice.index("async def probe_escalation"):voice.index("async def before_worker")]
    assert "await probe_instead_of_a_worker(" in esc, "…including the closed catalogue card"
    body = voice[voice.index("async def before_worker"):]
    assert "await commission_call(" in body[:body.index("\nasync def ", 10)], "the voice channel runs the same decision"
