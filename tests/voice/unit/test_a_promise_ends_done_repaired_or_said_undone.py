"""V2-790 — a reply that commits to an act gets its second pass: the pass runs the call, declares `cannot_do`, or
judges nothing is owed, and a call a guard swallows is recorded as not done. Never only `⚠️ promesa sin acción`.

The class, as measured: with the decision model unavailable the promise repair's card came from nowhere, so «I'll
turn it up and unmute it» and four «I'm opening its videos tab» went by with nothing run; and a reply CLAIMING
«there, its videos tab is open» reached the operator while the op it re-emitted had been discarded by a guard.
These pin the repair (`nucleo/turn/promise_repair.py`, until F2) with the decision model silent. The late
«I have not done it» line is gone (V2-851 F1): the turn's one line is the mouth's verdict (node 2.1050).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.flash import act_repair
from nucleo.turn import promise_repair as pk


class _Client:
    """A FastClient whose `complete` answers with the tool calls it is given — the real signature."""
    calls: list = []
    answer: list = []

    def __init__(self, *a, **k):
        pass

    async def complete(self, messages, *, spec=None, max_tokens=None, tools=None, on_tool_call=None,
                       no_thinking=False):
        _Client.calls.append({"messages": messages, "tools": tools})
        for name, args in _Client.answer:
            on_tool_call(name, args)
        return ""


@pytest.fixture
def client(monkeypatch):
    from nucleo.flash import widget_read
    from nucleo.llm import fast_client
    monkeypatch.setattr(fast_client, "FastClient", _Client)
    monkeypatch.setattr(widget_read, "read", lambda wid: "")
    _Client.calls, _Client.answer = [], []
    return _Client


@pytest.fixture
def silent_jev(monkeypatch):
    """The decision model answers nothing (an outage): every brief reads as absent, every late question fails."""
    from nucleo import jev
    monkeypatch.setattr(jev, "peek", lambda handle: None)
    monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: None)


@pytest.fixture
def youtube_in_front(monkeypatch):
    from nucleo import canvas_focus
    from nucleo.flash import canvas_visibility
    monkeypatch.setattr(canvas_visibility, "open_ids", lambda: frozenset({"youtube"}))
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "youtube" if "youtube" in ids else "")


# ── the card, when no verdict names one ─────────────────────────────────────────────────────────────────

def test_a_call_a_guard_discarded_still_names_its_card():
    calls = [{"name": "widget_data", "args": {"widget_id": "youtube", "action": "channel_videos", "payload": {}}}]
    assert pk.unrun_model_card(calls, ran_ops=[]) == "youtube"
    assert pk.unrun_model_card(calls, ran_ops=[("youtube", "channel_videos")]) == "", "it ran: nothing is owed"
    assert pk.unrun_model_card([{"name": "web_search", "args": {}}], ran_ops=[]) == ""


def test_with_the_decision_model_silent_the_card_in_front_gets_the_pass(silent_jev, youtube_in_front):
    assert pk.verdict_missing(None)
    assert pk.card_for_the_repair(None) == "youtube"


def test_a_verdict_that_answered_keeps_the_models_path(monkeypatch, youtube_in_front):
    """CRIT-K2: with a verdict present (even an unsure one) the focus guess stays out — only the model's own call."""
    import threading
    from nucleo.turn import brief as tb
    ev = threading.Event(); ev.set()
    brief = {"event": ev, "turn_id": "t", "open_ids": ["youtube"],
             "result": {tb.REQUEST_KEY: {"choice": "comment", "confidence": 0.62}}}
    assert not pk.verdict_missing(brief)
    assert pk.card_for_the_repair(brief) == ""
    failed = {"event": ev, "turn_id": "t", "open_ids": [],
              "result": {tb.REQUEST_KEY: {"choice": "none", "confidence": 0.0, "error": "HTTPError: 403"}}}
    assert pk.verdict_missing(failed), "a brief whose every answer failed is no verdict at all"


# ── the pass's third answer ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("his, said, reason", [
    ("¿Puedes subirle el volumen?", "Te lo subo y le quito el silencio.", "no_action"),
    ("Can you check it's today's video?", "Opening its videos tab to check the date.", "missing_detail"),
])
def test_the_pass_may_declare_it_cannot(client, his, said, reason):
    """The pass DECLARES a reason — never its own text (pass 6, INIT #14)."""
    client.answer = [("cannot_do", {"reason": reason, "say": "texto libre que nunca se dice"})]
    out: dict = {}
    got = asyncio.run(act_repair.call_for_promise(his, said, "youtube", outcome=out))
    assert got is None and out == {"kind": pk.CANNOT, "reason": reason}
    assert [t["function"]["name"] for t in client.calls[-1]["tools"]] == ["widget_data", "cannot_do"]
    # …and a caller that cannot end the turn honestly is offered ONE tool, exactly as before
    asyncio.run(act_repair.call_for_promise(his, said, "youtube"))
    assert [t["function"]["name"] for t in client.calls[-1]["tools"]] == ["widget_data"]


def test_a_pass_that_read_the_words_and_called_nothing_is_trusted(client):
    out: dict = {}
    assert asyncio.run(act_repair.call_for_promise("vale", "Vale, perfecto.", "youtube", outcome=out)) is None
    assert out["kind"] == pk.JUDGED


# ── the voice door, driven ──────────────────────────────────────────────────────────────────────────────

def _voice_turn(op_text: str, said: str, *, model_calls=(), apply=None):
    """Runs `post_stream_acts.complete_the_acts` on a turn that called nothing that ran."""
    from nucleo.flash import post_stream_acts as psw
    applied: list = []
    acted, data_done = {"widget": False}, {"v": False}
    escalate_req = {"v": None, "more": [], "surface": {}}

    def _apply(wid, action, payload, ref=""):
        applied.append((wid, action, payload))
        if apply is None:                                   # the FAST path of the real executor
            acted["widget"] = data_done["v"] = True
            data_done.setdefault("ops", []).append((wid, action))

    brain = SimpleNamespace(_window=[], _last_action=None, _turn_calls=list(model_calls), _last_spoken="")
    none = lambda: {"v": None}                              # noqa: E731
    events: list = []
    out = asyncio.run(psw.complete_the_acts(
        _apply_widget_data=_apply, _brief=None, _data_ops_hechas=[], _has_workers=False, _prompt_mod=None,
        _repeat_repair={"v": None}, _router=__import__("nucleo.flash.router", fromlist=["x"]),
        _show_guard_target=lambda *a, **k: None, _tag_emit=lambda *a, **k: None, _tool_fired=set(),
        _turn_op_tasks=[], acted=acted, brain=brain, canvas_h=None, clarify={"msg": None}, cron_seen={"v": True},
        data_done=data_done, emit=lambda *a, **k: events.append((a, k)), escalate_req=escalate_req,
        images_req=none(), listing_req=none(), music_req=none(), operator_text=op_text, read_req=none(),
        recall_req=none(), reopen_req=none(), reveal_req=none(), search_req=none(), send=lambda t: None,
        speak=lambda t: None, spec=None, speech=SimpleNamespace(sanitize=lambda t, **k: t), spoken=[said],
        text=op_text, worker_acted={"v": False}))
    return SimpleNamespace(applied=applied, acted=acted, data_done=data_done, events=events, out=out)


@pytest.mark.parametrize("his, said, call", [
    ("¿Puedes subirle el volumen o algo?", "Te lo subo y le quito el silencio, que arranca mudo.",
     ("youtube", "unmute", {})),
    ("Can you turn the video up?", "Turning it up and unmuting it now.", ("youtube", "unmute", {})),
])
def test_voice_a_promise_without_a_tool_gets_its_call_with_the_decision_model_silent(
        client, silent_jev, youtube_in_front, monkeypatch, his, said, call):
    from widgets import runtime
    monkeypatch.setattr(runtime, "get", lambda wid: {"actions": {"unmute": {"desc": "unmute"},
                                                                 "channel_videos": {"desc": "channel videos"}}})
    client.answer = [("widget_data", {"widget_id": call[0], "action": call[1], "payload": call[2]})]
    t = _voice_turn(his, said)
    assert t.applied == [call], "the promised call did not run"
    assert t.data_done["promise"]["kind"] == pk.CALL


def test_voice_a_claim_after_a_discarded_op_is_not_delivered_as_done(client, silent_jev, monkeypatch):
    """T18 of the measured session: the model re-emitted `youtube:channel_videos`, a guard discarded it, the reply
    said «ya está». The pass asks the card the model named; its call is swallowed again and is recorded as not done."""
    from nucleo.flash import canvas_visibility
    from widgets import runtime
    monkeypatch.setattr(canvas_visibility, "open_ids", lambda: frozenset())
    monkeypatch.setattr(runtime, "get", lambda wid: {"actions": {"channel_videos": {"desc": "channel videos"}}})
    dropped = {"name": "widget_data", "args": {"widget_id": "youtube", "action": "channel_videos", "payload": {}}}
    client.answer = [("widget_data", dropped["args"])]
    said = "…ya está: te dejo abierta su pestaña de vídeos con los más recientes."
    t = _voice_turn("Quiero que lo hagas directamente.", said, model_calls=[dropped], apply="swallow")
    assert t.applied, "the card the model named was never asked"
    assert t.data_done["promise"]["kind"] == pk.SWALLOWED and not t.acted["widget"], "a swallowed call is not done"
