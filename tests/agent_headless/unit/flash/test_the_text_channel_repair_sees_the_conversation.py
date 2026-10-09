"""The text channel's promise repair sees the conversation, like the voice one (V2-781 pair 3, 2026-10-10).

«Can you set a reminder for me on premiere day?» → «I'll set that up for you», no call. The repair ran with the
operator's turn alone: no date anywhere, so its call was `set_reminder {title: "premiere"}` on nothing. Measured
offline with the round's own words: WITH the window it calls `add_meeting {date: 2026-10-30}`; without, it does not.
The voice rail (`card_commission`) already handed it the window; the probe did not.
"""
from __future__ import annotations

import asyncio


def test_the_probe_hands_the_window_to_the_repair():
    src = open("nucleo/flash/probe_mirrors.py", encoding="utf-8").read()
    i = src.index("call_for_promise_or_order(operator_text, spoken")
    assert "window=getattr(sess, \"window\", None)" in src[i:i + 600]


def test_probe_call_for_promise_passes_it_on(monkeypatch):
    from nucleo import jev
    from nucleo.flash import act_repair as A, build_decision as B, turn_brief as T
    seen = {}
    monkeypatch.setattr(T, "ask_for_turn", lambda *a, **k: object())
    monkeypatch.setattr(jev, "_is_ready", lambda h: True)
    monkeypatch.setattr(B, "named_card", lambda h: "agenda")

    async def _cfp(op, reply, wid, spec=None, *, window=None):
        seen["window"] = window
        return None
    monkeypatch.setattr(A, "call_for_promise", _cfp)
    win = [{"role": "assistant", "content": "It premieres on October 30."}]
    asyncio.run(A.probe_call_for_promise("set a reminder on premiere day", "I'll set that up", window=win))
    assert seen["window"] == win
