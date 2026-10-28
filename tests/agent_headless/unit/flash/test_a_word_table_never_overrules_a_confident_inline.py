"""A word table never turns an empty promise into a worker over a confident `handle_inline` (V2-802 T-07, CRIT-K1).

Live run: «Ayer te pedí hacer una reserva en un restaurante. Te di mi nombre completo y mi teléfono. ¿Todo eso ya
debería estar en tu memoria permanente?» — brief `question` (unsure) · `tell` · `handle_inline` 1.00. The model said
«Eso es lo que estoy comprobando ahora mismo…» and called nothing; the post-stream promise branch met «reserva» in
`looks_like_escalate_task` and a web worker went looking for restaurants. V2-753 had put «only a confident
handle_inline stops the escalation» in `promise_backstop`; this branch lacked it.

The variant here is another language and another domain on purpose: a hotel, in English.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import types

import pytest

from nucleo.flash import escalation_guard as EG
from nucleo.flash import turn_brief as tb

SAID = "Last week I asked you to book a hotel in Lisbon and gave you my passport number. Do you still remember all that?"
REPLY = "That's exactly what I'm checking right now, give me a second."


def _brief(escalate: str, conf: float) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {
        tb.ESCALATE_KEY: {"choice": escalate, "confidence": conf},
        tb.REQUEST_KEY: {"choice": "question", "confidence": 0.45},     # unsure, as in the live run
        tb.WORDS_KEY: {"choice": "tell", "confidence": 0.9}}}


@pytest.fixture(autouse=True)
def _no_repair(monkeypatch):
    """The act repair is another lane (it asks a model); this file is about the word-table branch alone."""
    from nucleo.flash import act_repair
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", lambda *a, **k: None)


def test_the_premise_the_word_table_does_match():
    from nucleo.flash import router
    assert router.looks_like_escalate_task(SAID), "the variant must reach the word table, or this file tests nothing"
    assert router.promises_action(REPLY)


def test_a_confident_inline_refuses_the_word_table_and_anything_else_keeps_it():
    from nucleo.flash import router
    assert EG.word_tables(router, _brief("handle_inline", 1.0), SAID) == "refused"
    assert EG.word_tables(router, _brief("handle_inline", 0.3), SAID) == "go"     # unsure: today's path
    assert EG.word_tables(router, _brief("escalate", 0.95), SAID) == "go"
    assert EG.word_tables(router, None, SAID) == "go"                             # no brief: today's path
    assert EG.word_tables(router, None, "thanks, that's all") == ""               # no match: the lookback may try


def test_the_voice_lane_asks_the_same_door_before_any_word_table():
    from nucleo.flash import post_stream_lanes as lanes
    src = inspect.getsource(lanes.run_the_light_lanes)
    assert '(_wt := _eg.word_tables(_router, _brief, _op_text, emit=emit)) == ""' in src   # the lookback too
    assert 'elif (_wt == "go" or _win_goal' in src
    assert src.index("_eg.word_tables(") < src.index('elif (_wt == "go"')


def _voice_lane(monkeypatch, brief) -> tuple[dict, list]:
    """The voice lane itself, run with the turn's state stubbed; the root conftest isolates every store."""
    from nucleo.flash import post_stream as P, post_stream_lanes as L, router

    async def _untouched(no_tool, *a, **k):
        return no_tool
    monkeypatch.setattr(P._resume_turn, "before_backstops", _untouched)
    events: list = []
    escalate_req = {"v": None}
    kw = {n: None for n in inspect.signature(L.run_the_light_lanes).parameters}
    kw.update(_brief=brief, _op_text=SAID, operator_text=SAID, text=SAID, spoken_text=REPLY, spoken=REPLY,
              _no_tool=True, _router=router, emit=lambda *a, **k: events.append(a), escalate_req=escalate_req,
              music_req={"v": None}, acted={}, data_done={"v": False}, clarify={}, _tool_fired=set(),
              _shown_ids=set(), brain=types.SimpleNamespace(_window=[], _last_spoken=""), _named_by_verdict="",
              _identify=lambda t: "", _identify_system=lambda t: None, with_also_named=lambda ids, t: ids,
              **{k: {"v": None} for k in ("read_req", "recall_req", "reopen_req", "reveal_req", "search_req",
                                          "listing_req", "images_req")})
    asyncio.run(L.run_the_light_lanes(**kw))
    return escalate_req, events


def test_the_voice_lane_does_not_escalate_a_question_the_verdict_kept_inline(monkeypatch):
    req, events = _voice_lane(monkeypatch, _brief("handle_inline", 1.0))
    assert req["v"] is None, req
    assert any("ANULADA por el veredicto" in str(e[1]) for e in events), events


def test_the_voice_lane_still_escalates_when_the_verdict_is_unsure(monkeypatch):
    req, _ = _voice_lane(monkeypatch, _brief("handle_inline", 0.3))
    assert req["v"] == SAID
