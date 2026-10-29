"""A reply that PROMISES a send while nothing was sent gets «nothing has gone out», read by one closed question over OUR
reply — never by a word table (node 2.981).

Demo sandbox 2026-10-29 (passes 5-6, C2/C3): «…I'll message Rowan and set it up», «…and I'll send him the note». Jev read
`errand_class = none` (correct: he never asked to message anyone), so the R11 line (`unsent_line`, which needs a sure
`sends_for_him`) stayed quiet, and the model's own words promised a message nobody sent. The class: words the turn
SAID promise a consequence no door delivered.

The mechanism (`promise_kept.reply_promised_a_send`): on a turn that owes an ORDER, can send (a messaging connector is
on, or a card on screen declares an `external.send` act) and sent nothing, ONE closed Jev question (`brief.PROMISE_*`,
declared as data) is asked over the finished reply in the background; «promises_a_send», sure → the session-language
`send_not_done` line, as the turn's follow-up. A reply that only ASKS whether to send is not a promise.

`BENCH` is the criterion's bank: ES+EN, the C2/C3 shapes (yes), a plain calendar promise (no) and a question (no). Here
the decision model is recorded (its answer per reply) and the test proves the plumbing through the real typed turn;
`ZAELAR_JEV_LIVE=1` asks the real Jev instead and measures the criterion itself.

Disarm: no gate → asked on a turn that cannot send; no answer read → the line never comes; the line said on «no».
"""
from __future__ import annotations

import asyncio
import os

import pytest

from nucleo import jev
from nucleo.flash import follow_up_pass
from nucleo.turn import brief as tb
from tests.brain import harness

LIVE = os.getenv("ZAELAR_JEV_LIVE") == "1"
BENCH = [   # (lang, reply, the criterion's answer)
    ("en", "Your last meeting ends at four, so four to four forty-five is free — I'll message Rowan and set it up.", "promises_a_send"),
    ("en", "Putting it in your calendar as Catch up with Rowan, and I'll send him the note.", "promises_a_send"),
    ("es", "Mañana de cuatro a cinco menos cuarto está libre; te lo reservo y le mando un mensaje a Rowan.", "promises_a_send"),
    ("es", "Lo apunto en tu calendario y le aviso a Rowan de la hora nueva.", "promises_a_send"),
    ("en", "I'll put it on your calendar for four tomorrow.", "no"),
    ("es", "Te lo pongo en el calendario mañana a las cuatro.", "no"),
    ("en", "Four to four forty-five is free. Want me to message him?", "no"),
    ("es", "De cuatro a cinco menos cuarto está libre. ¿Quieres que le escriba?", "no"),
]
ORDER = {"request_type": ["order", 0.9], "escalate_or_inline": ["handle_inline", 1.0], "canvas": ["neither", 1.0],
         "errand_class": ["none", 0.96], "screen_action": ["agenda:find_free", 0.6]}


def _turn(lang: str, reply: str, monkeypatch, *, brief=ORDER, open_cards=("agenda",)) -> tuple[list, list]:
    asked, said = [], []

    async def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None, **_kw):
        harness.RecordedModel.consulted = True
        yield reply
        if on_tool_call:                          # the act that DID run (C2: the free slot was found)
            on_tool_call("widget_data", {"widget_id": "agenda", "action": "find_free",
                                         "payload": {"minutes": 45, "date": "tomorrow"}})
    monkeypatch.setattr(harness.RecordedModel, "stream", stream)
    real = jev.choose_many_sync
    answer = {r: a for _l, r, a in BENCH}

    def ask(state, questions, **kw):
        asked.append((state, list(questions)))
        if LIVE:
            return real(state, questions, **kw)
        return {tb.PROMISE_KEY: {"choice": answer.get(state, "no"), "confidence": 0.95}}
    monkeypatch.setattr(follow_up_pass, "deliver", said.append)
    case = {"id": f"promise-{lang}", "lang": lang, "phrase": "find me a free 45 minutes tomorrow to talk with rowan",
            "screen": {"open": list(open_cards)}, "brief": brief}

    async def main():
        from nucleo.cli import turn as cli_turn
        from nucleo.turn import promise_kept
        from tests.waiting import until
        await cli_turn.run_turn(case["phrase"], sid=case["id"], ingest=False, execute=True, lists=False)
        await until(lambda: not promise_kept._LATE, "the background question to answer", timeout_s=5.0)
        cli_turn.reset(case["id"])

    import nucleo.memory_agent as _mem

    async def _no_ingest(*_a, **_k):
        return {}
    monkeypatch.setattr(_mem, "ingest_utterance", _no_ingest)
    with harness.Isolated(lang) as iso:
        iso.seed(case)
        iso._set(jev, "choose_many_sync", ask)    # through the harness's own patch: `seed` installs its own Jev stand-in
        asyncio.run(main())
    return [a for a in asked if tb.PROMISE_KEY in a[1]], said


@pytest.mark.parametrize("lang,reply,expect", BENCH)
def test_the_reply_is_asked_once_and_a_promise_hears_nothing_went_out(lang, reply, expect, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from i18n import langs
    line = langs.current_language().send_not_done
    asked, said = _turn(lang, reply, monkeypatch)
    assert [a[0] for a in asked] == [reply], "ONE question, over OUR reply"
    assert said == ([line] if expect == "promises_a_send" else []), said


@pytest.mark.parametrize("why,kw", [
    ("nothing on screen can send and no connector is on", {"open_cards": ()}),
    ("the turn owes no order", {"brief": {**ORDER, "request_type": ["comment", 0.9]}}),
])
def test_a_turn_that_could_not_send_or_owes_no_order_asks_nothing(why, kw, monkeypatch):
    asked, said = _turn("en", BENCH[0][1], monkeypatch, **kw)
    assert asked == [] and said == [], why
