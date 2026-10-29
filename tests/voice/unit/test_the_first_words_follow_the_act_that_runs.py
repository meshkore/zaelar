"""The words said first describe the act that RUNS: under a sure ANSWER verdict the model's words are held until its
calls are known, and dropped when the verdict replaced the call they narrated (node 2.977).

Demo sandbox 2026-10-29, pass 4, C2 («find me a free 45 minutes tomorrow afternoon to talk with rowan»): the brief was
SURE of `agenda:find_free` (0.87) before the first token; the model said «I'm putting Rowan down for 4:00 to 4:45» and
called `add_meeting`; the call arrived at the stream's end and the verdict replaced it (`acts.card.vetoes`, a question
wins over a write) — but the words had streamed already, and the op's answer could only come as a correction, aside
(R5b): «I haven't actually booked it yet…».

The mechanism (`nucleo/flash/follow_up_pass.holds/release`, one seam in the voice turn's stream loop): held only when
the sure `screen_action` ANSWERS (`output.answer` — its words compose from the op's data, so the model's first words are
speculative); released at the stream's end, or dropped when the model's call on that card did not run as it made it.
Dropped words never reach `spoken`, so the op's answer pass runs inline and IS the first words. Nothing reads words.

Runs through the real typed turn (`nucleo.cli.turn.run_turn`, the voice turn itself) in the bank's isolation, with a
scripted model. Disarm: holding nothing, or releasing without the swap check, turns the swap cases red.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.brain import harness

AGENDA = [{"title": "Product meeting", "day": "+1", "start": "11:00", "end": "12:00"},
          {"title": "Meshcore architecture", "day": "+1", "start": "15:00", "end": "16:00"}]
CASES = {
    "en": ("find me a free 45 minutes tomorrow afternoon to talk with rowan, after my last meeting",
           "Got it — I'm putting Rowan down for 4:00 to 4:45 and setting that aside in your calendar.",
           "Four to four forty-five tomorrow is free, right after your last meeting.",
           "Let me look at tomorrow afternoon."),
    "es": ("búscame 45 minutos libres mañana por la tarde para hablar con rowan, después de mi última reunión",
           "Hecho, te apunto a Rowan de 4:00 a 4:45 y lo reservo en tu calendario.",
           "Mañana de cuatro a cinco menos cuarto lo tienes libre, justo después de tu última reunión.",
           "Déjame mirar mañana por la tarde."),
}
_ADD = ("widget_data", {"widget_id": "agenda", "action": "add_meeting",
                        "payload": {"title": "Rowan", "date": "tomorrow", "startTime": "16:00", "endTime": "16:45"}})
_FIND = ("widget_data", {"widget_id": "agenda", "action": "find_free", "payload": {"minutes": 45, "date": "tomorrow"}})


def _turn(lang: str, script: list, brief: dict, monkeypatch) -> str:
    """One typed turn through the voice turn, the model answering from `script`: one `(say, calls)` per model call, in
    the order the turn makes them (the turn's stream, a repair pass, the op's answer pass)."""
    async def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None, **_kw):
        harness.RecordedModel.consulted = True
        say, calls = script.pop(0) if script else ("", [])
        if say:
            yield say
        for name, args in calls:
            if on_tool_call:
                on_tool_call(name, dict(args))
    async def complete(self, messages, spec=None, *a, on_tool_call=None, **_kw):     # a second pass that calls
        say, calls = script.pop(0) if script else ("", [])
        for name, args in calls:
            if on_tool_call:
                on_tool_call(name, dict(args))
        return say
    monkeypatch.setattr(harness.RecordedModel, "stream", stream)
    monkeypatch.setattr(harness.RecordedModel, "complete", complete)
    case = {"id": f"r16-{lang}", "lang": lang, "phrase": CASES[lang][0], "screen": {"open": ["agenda"]},
            "memory": {"agenda": AGENDA}, "brief": brief}
    with harness.Isolated(lang) as iso:
        iso.seed(case)
        from nucleo.cli import turn as cli_turn
        from nucleo.turn import brief as tb
        monkeypatch.setattr(tb, "ask_for_turn", lambda *a, **k: harness.brief_handle(case))
        import nucleo.memory_agent as _mem

        async def _no_ingest(*_a, **_k):
            return {}
        monkeypatch.setattr(_mem, "ingest_utterance", _no_ingest)     # memory is not what is measured here
        from voice import observer
        n0 = len(observer._events)
        try:
            res = asyncio.run(cli_turn.run_turn(case["phrase"], sid=case["id"], ingest=False, execute=True))
        finally:
            cli_turn.reset(case["id"])
        _turn.events = [dict(e) for e in observer._events[n0:]]
    reply = res.get("reply")
    return " ".join(reply) if isinstance(reply, list) else str(reply or "")


ANSWER = {"screen_action": ["agenda:find_free", 0.87], "request_type": ["order", 0.83], "canvas": ["neither", 1.0]}


@pytest.mark.parametrize("lang", ["en", "es"])
def test_words_that_narrated_a_replaced_call_are_not_said_and_the_ops_answer_is(lang, monkeypatch):
    _phrase, narration, answer, _look = CASES[lang]
    reply = _turn(lang, [(narration, [_ADD]), ("", [_FIND]), (answer, [])], ANSWER, monkeypatch)
    assert narration not in reply, f"the words narrated the replaced add_meeting: {reply!r}"
    assert answer in reply, f"the op's answer is the first words: {reply!r}"


@pytest.mark.parametrize("lang", ["en", "es"])
def test_an_answer_verdict_with_no_swap_says_the_held_words_first(lang, monkeypatch):
    """R5b unchanged: the words were said before the op's pass, which only confirms or corrects them."""
    from nucleo.flash import follow_up_pass
    seen = []
    real = follow_up_pass.detach
    monkeypatch.setattr(follow_up_pass, "detach", lambda sys2, ut, said, *a, **k: seen.append(said) or real(sys2, ut, said, *a, **k))
    _phrase, _narration, answer, look = CASES[lang]
    reply = _turn(lang, [(look, [_FIND]), (answer, [])], ANSWER, monkeypatch)
    assert reply.startswith(look), reply
    assert seen and seen[0].strip() == look, f"the op's pass saw the words already said: {seen!r}"


@pytest.mark.parametrize("target,held", [("agenda:find_free", "agenda"), ("youtube:show_tab", ""),
                                         ("agenda:move_meeting", ""), ("none", "")])
def test_only_a_sure_answer_verdict_holds(target, held):
    from nucleo.flash import follow_up_pass
    sure = harness.brief_handle({"id": "x", "phrase": "x", "screen": {"open": []},
                                 "brief": {"screen_action": [target, 0.9]}})
    unsure = harness.brief_handle({"id": "x", "phrase": "x", "screen": {"open": []},
                                   "brief": {"screen_action": [target, 0.6]}})
    assert follow_up_pass.holds(sure) == held
    assert follow_up_pass.holds(unsure) == "" and follow_up_pass.holds(None) == ""
