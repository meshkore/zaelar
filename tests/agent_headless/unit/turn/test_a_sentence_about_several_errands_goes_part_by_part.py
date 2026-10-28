"""One sentence that names several of his errands goes part by part, and the reply says each (node 2.643).

three-tasks-at-once (EN, 2026-10-14 02:44, sandbox 023306-en): «ok nice. ping me when the game's ready to try, and
send the report when it's done. for the monitor used is fine, just make sure it's got hdmi at least». The model
called nothing; the promise repair asked the late catalogue for a card, got «mensajeria», and wrote «Requisitos del
monitor: al menos HDMI.» as a messaging draft. The monitor hunt never heard of HDMI and the reply was «Done.».

`nucleo/turn/split_by_errand.py` cuts the sentence on its own punctuation, gives each part to the errand its words
name, injects the statements into the LIVE ones, holds the card repair in both channels, and the reply names every
errand it did not already name.
"""
from __future__ import annotations

import asyncio
import types

import pytest

from nucleo import dispatch
from nucleo.dispatch import confirm as dc
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import split_by_errand as S

GAME = {"id": "6", "request": "Build a small platform game widget, Super Mario style: run and jump", "phase": "",
        "waiting_on": ""}
MONITOR = {"id": "3", "request": E.listing_errand({"query": "used monitor cheap", "condition": "usado"}),
           "phase": "", "waiting_on": ""}
REPORT = {"id": "4", "goal": "Prepare a report on electric cars for city driving", "title": "Report on electric cars"}
TITLES = {"6": "Build a Super Mario-style platformer game", "3": "Marketplace listings for used cheap monitor"}
HIS = ("ok nice. ping me when the game’s ready to try, and send the report when it’s done. for the monitor used is "
       "fine, just make sure it’s got hdmi at least")


@pytest.fixture
def injected(monkeypatch):
    out: list[tuple[str, str]] = []
    S.forget()
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(GAME), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=TITLES.get(tid, "")))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr("nucleo.flash.escalate.pending", lambda: [])
    monkeypatch.setattr("nucleo.workers.ended.recently_ended_sessions", lambda **k: [dict(REPORT)])
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, msg: out.append((which, msg)))
    yield out
    S.forget()


def test_each_part_reaches_its_own_errand(injected):
    ps = S.route(HIS)
    assert {p["errand"]["id"] for p in ps} == {"6", "4", "3"}, [(p["errand"]["id"], p["words"]) for p in ps]
    to = dict(injected)
    assert "hdmi" in to["3"] and "game" not in to["3"], to          # the monitor hears HDMI, and only its part
    assert "game" in to["6"] and "hdmi" not in to["6"], to
    assert "4" not in to, "a finished errand has no worker to hear it"
    assert S.route(HIS) == ps and len(injected) == 2, "the same words are routed once"


def test_a_bare_done_becomes_the_sentence_for_each(injected):
    S.route(HIS)
    line = S.each_said("Done.", HIS)
    assert line.startswith("On each one:"), line
    assert "monitor" in line and "passed on" in line and "already done" in line, line
    assert S.each_said("Done.", HIS) == "Done.", "said once per routing"


def test_what_the_reply_already_named_is_not_said_twice(injected):
    S.route(HIS)
    line = S.each_said("Sure, I'll ping you the moment the game is ready.", HIS)
    assert line.startswith("Sure, I'll ping you"), line
    assert "monitor" in line and "Super Mario" not in line, line


def test_a_question_part_is_answered_not_injected(injected):
    q = "the monitor is fine, keep it under 150. how's the game coming?"
    S.route(q)
    assert [w for w, _m in injected] == ["3"], injected
    assert "Super Mario" in S.each_line("", q)


def test_one_errand_named_is_not_this_door(injected):
    assert S.route("for the monitor make sure it's got hdmi") == [] and injected == []
    assert S.route("ok cool, thanks") == []


def test_the_text_channel_holds_the_card_repair(injected, monkeypatch):
    """The probe mirror of the voice backstops: with the sentence routed, no repaired card call is added."""
    from nucleo.flash import act_repair, card_commission, probe_mirrors, reply_promise

    async def _repair(*a, **k):
        return {"widget_id": "mensajeria", "action": "draft", "payload": {"text": "Requisitos del monitor: HDMI."}}

    async def _nothing(*a, **k):
        return None
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda *a, **k: "mensajeria")
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", _repair)
    monkeypatch.setattr(act_repair, "probe_call_for_promise", _repair)
    monkeypatch.setattr(reply_promise, "prefetch", _nothing)
    calls: list = []
    asyncio.run(probe_mirrors.mirror_the_voice_backstops(
        _akp=None, _cw=None, _hw=False, _router=None, _rt=None, _sp=None, _tbrief=None, action="chat", canvas_h=None,
        dialog=None, names=[], operator_text=HIS, sess=types.SimpleNamespace(window=[], last_action=None), spec=None,
        speech=None, spoken="Will do.", tags=[], text=HIS, tool_calls=calls))
    assert not any(c.get("args", {}).get("widget_id") == "mensajeria" for c in calls), calls
    assert ("3", injected[-1][1]) in injected and "hdmi" in dict(injected)["3"]


def test_the_voice_channel_routes_and_holds_the_backstop(injected):
    from voice.engine.llm.providers import promise_backstop
    escalated = []
    promise_backstop.run("On it.", did_act=False, op_text=HIS, prev_pending=[], emit=lambda *a, **k: None,
                         escalate=lambda *a, **k: escalated.append(a), similar_pending=lambda *a: False)
    assert not escalated and all(m != HIS for _w, m in injected), "his whole sentence went to one errand"
    assert sorted(w for w, _m in injected) == ["3", "6"], injected
    assert "hdmi" in dict(injected)["3"] and "game" not in dict(injected)["3"], injected
    assert S.holds_the_repair("On it.", HIS), "the voice card repair is held for a routed sentence"


def test_both_channels_say_each_errand():
    """The reply half's wiring: the text channel's owed words and the voice turn's close both say each errand."""
    import inspect
    from nucleo.flash import probe_after
    from voice.engine.llm.providers import turn_after
    assert "_sbe.each_said(spoken, text)" in inspect.getsource(probe_after.the_words_it_owes)
    assert "_sbe.each_line(spoken_text, _op_text)" in inspect.getsource(turn_after.close_the_turn)


def test_a_routing_is_said_only_in_its_own_turn(injected):
    """A routed turn that ended up as another action owes nothing to the NEXT turn's reply."""
    S.route(HIS)
    assert S.each_line("Sure.", "how's the weather?") == ""


def test_the_text_channel_replaces_a_bare_done(injected):
    from nucleo.flash import probe_after
    S.route(HIS)
    out = asyncio.run(probe_after.the_words_it_owes(
        _hw=True, _parts=None, _show_chose="", action="chat", images_req=None, return_extra_exec={},
        sess=types.SimpleNamespace(window=[]), spoken="Done.", tags=[], text=HIS, video_req=None, brief=None))
    assert out["spoken"].startswith("On each one:") and "monitor" in out["spoken"], out["spoken"]
