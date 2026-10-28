"""A commission the CLOSED catalogue card can do is that card's call on BOTH channels (V2-252 parity, 2026-10-15).

Live bench, «send rowan a telegram with the new time» with the messages card closed: 4/7 — the three reds escalated
a two-field send to a worker. The voice channel had `card_commission.before_worker`; the text channel (the probe,
which the bench and a chat-only operator drive) had only the OPEN-card half. The decision is now one function,
`commission_call`; since refactor2710-01 the typed channel runs the voice turn, so `before_worker` serves both.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def test_the_voice_turn_asks_the_decision_before_a_worker():
    voice = (ROOT / "nucleo/flash/card_commission.py").read_text("utf-8")
    body = voice[voice.index("async def before_worker"):]
    assert "await commission_call(" in body[:body.index("\nasync def ", 10)], "the voice channel runs the same decision"
