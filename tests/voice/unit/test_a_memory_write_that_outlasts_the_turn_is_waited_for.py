"""An order whose act is a memory write the distiller is still filing when the turn ends is not «not done»: its line
waits for the memory door, and is said as the turn's follow-up only if the door filed nothing (node 2.979).

Demo sandbox 2026-10-29, pass 6, INIT #01 «Your name is Johnny…» (brief: order, identity_change=rename 1.00): the
distiller took 4.3 s, the acts door waited its whole 4 s budget (`reply.after_acts`), the record was still in flight,
and the turn said «I haven't done it — I couldn't carry it out from here.» — then the assistant's name was written.
An outcome still in flight is not a fact. Runs through the real typed turn in the bank's isolation.

Disarm: without the wait on a pending door the early line comes back; without the late check a write-nothing order
loses its honest line.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.memory_agent import ingest as I
from nucleo.turn import reply as R
from tests.brain import harness

PHRASES = {"en": ("Your name is Johnny. When I say Johnny, I am talking to you.", "Got it, Johnny. What can I do?"),
           "es": ("A partir de ahora te llamas Johnny. Cuando diga Johnny, te hablo a ti.", "Hecho, soy Johnny. ¿Qué necesitas?")}
BRIEF = {"request_type": ["order", 0.89], "wants_words": ["act", 0.88], "escalate_or_inline": ["handle_inline", 1.0],
         "canvas": ["neither", 1.0], "identity_change": ["rename", 1.0]}


def _turn(lang: str, filed: dict, monkeypatch) -> tuple[str, list[str]]:
    phrase, say = PHRASES[lang]

    async def stream(self, messages, spec=None, tools=None, on_tool_call=None, metrics=None, **_kw):
        harness.RecordedModel.consulted = True
        yield say

    async def slow_distiller(text, *, role="operator"):
        await asyncio.sleep(0.6)                 # outlasts the acts' budget below
        return dict(filed)

    late: list[str] = []
    from nucleo.flash import follow_up_pass
    monkeypatch.setattr(harness.RecordedModel, "stream", stream)
    monkeypatch.setattr(I, "_ingest_utterance_locked", slow_distiller)
    monkeypatch.setattr(R.after_acts, "__defaults__", (0.2,))    # the acts' budget, shortened for the test
    monkeypatch.setattr(follow_up_pass, "deliver", late.append)
    case = {"id": f"mem-late-{lang}", "lang": lang, "phrase": phrase, "screen": {"open": []}, "brief": BRIEF}

    async def main():
        from nucleo.cli import turn as cli_turn
        res = await cli_turn.run_turn(phrase, sid=case["id"], ingest=False, execute=True, lists=False)
        for _ in range(40):                      # the engine's loop lives on; so does this one, until memory settles
            if R._MEMORY and not any(v[0] for v in R._MEMORY.values()):
                break
            await asyncio.sleep(0.05)
        await asyncio.sleep(0.3)                 # the late check's own poll
        cli_turn.reset(case["id"])
        return res

    with harness.Isolated(lang) as iso:
        iso.seed(case)
        res = asyncio.run(main())
    reply = res.get("reply")
    return (" ".join(reply) if isinstance(reply, list) else str(reply or "")), late


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(R, "_MEMORY", {})


@pytest.mark.parametrize("lang", ["en", "es"])
def test_a_rename_the_distiller_files_after_the_budget_owes_no_line(lang, monkeypatch):
    from i18n import langs
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    line = langs.current_language().promise_not_kept
    reply, late = _turn(lang, {"source": "llm", "atoms": 2}, monkeypatch)
    assert line not in reply, reply
    assert late == [], late


@pytest.mark.parametrize("lang", ["en", "es"])
def test_an_order_the_door_filed_nothing_for_still_hears_it_late(lang, monkeypatch):
    from i18n import langs
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    line = langs.current_language().promise_not_kept
    reply, late = _turn(lang, {"source": "discard-llm", "atoms": 0}, monkeypatch)
    assert line not in reply, reply
    assert late == [line], late
