"""V2-790 — a reply that commits to an act ends in one of three states: it ran, a second pass ran it, or he hears
that it was not done. Never only `⚠️ promesa sin acción` on the timeline.

The class, as measured: with the decision model unavailable the promise repair's card came from nowhere, so «I'll
turn it up and unmute it» and four «I'm opening its videos tab» went by with nothing run and nothing said; and a
reply CLAIMING «there, its videos tab is open» reached the operator while the op it re-emitted had been discarded
by a guard. These pin the mechanism (`nucleo/turn/promise_kept.py`) and its wiring in BOTH channels, in Spanish and
English, with the decision model silent.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.flash import act_repair
from nucleo.turn import promise_kept as pk


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
    from nucleo.flash import turn_brief as tb
    ev = threading.Event(); ev.set()
    brief = {"event": ev, "turn_id": "t", "open_ids": ["youtube"],
             "result": {tb.REQUEST_KEY: {"choice": "comment", "confidence": 0.62}}}
    assert not pk.verdict_missing(brief)
    assert pk.card_for_the_repair(brief) == ""
    failed = {"event": ev, "turn_id": "t", "open_ids": [],
              "result": {tb.REQUEST_KEY: {"choice": "none", "confidence": 0.0, "error": "HTTPError: 403"}}}
    assert pk.verdict_missing(failed), "a brief whose every answer failed is no verdict at all"


# ── the pass's third answer ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("his, said, say", [
    ("¿Puedes subirle el volumen?", "Te lo subo y le quito el silencio.",
     "No puedo cambiar el volumen desde aquí: la tarjeta no tiene ese control."),
    ("Can you check it's today's video?", "Opening its videos tab to check the date.",
     "I can't sort its videos by date from the card, so I haven't checked it."),
])
def test_the_pass_may_say_it_cannot_and_the_turn_says_it(client, his, said, say):
    client.answer = [("cannot_do", {"say": say})]
    out: dict = {}
    got = asyncio.run(act_repair.call_for_promise(his, said, "youtube", outcome=out))
    assert got is None and out == {"kind": pk.CANNOT, "say": say}
    assert [t["function"]["name"] for t in client.calls[-1]["tools"]] == ["widget_data", "cannot_do"]
    assert pk.close(said, out, acted=False) == say
    # …and a caller that cannot end the turn honestly is offered ONE tool, exactly as before
    asyncio.run(act_repair.call_for_promise(his, said, "youtube"))
    assert [t["function"]["name"] for t in client.calls[-1]["tools"]] == ["widget_data"]


def test_a_pass_that_read_the_words_and_called_nothing_is_trusted(client):
    out: dict = {}
    assert asyncio.run(act_repair.call_for_promise("vale", "Vale, perfecto.", "youtube", outcome=out)) is None
    assert out["kind"] == pk.JUDGED
    assert pk.close("Te lo abro ahora mismo.", out, acted=False) == "", "the pass judged it — no wording reader over it"


@pytest.mark.parametrize("reply", ["…ya está: te dejo abierta su pestaña de vídeos.", "There you go — it's loaded."])
def test_a_claim_over_a_swallowed_call_is_never_left_as_done(reply):
    line = pk.close(reply, {"kind": pk.SWALLOWED}, acted=False)
    assert line and line not in reply
    assert pk.close(reply, {"kind": pk.SWALLOWED}, acted=True) == "", "something ran: nothing to add"


def test_no_card_and_an_owed_order_still_ends_honestly(monkeypatch):
    """refactor2710-03: the BRIEF says an act was owed (an order), never the words — the same three replies, read by
    the brief alone."""
    monkeypatch.setattr("nucleo.turn.reply.owes_an_act", lambda b: "order" if b == "ORDER" else "")
    for said in ("Lo hago ahora mismo: le quito el silencio.", "¿Cuál de los dos quieres que abra?", ""):
        assert pk.close(said, {}, acted=False, brief="ORDER"), said
        assert pk.close(said, {}, acted=False, brief=None) == "", "no order in the brief: nothing owed"


# ── the voice door, driven ──────────────────────────────────────────────────────────────────────────────

def _voice_turn(op_text: str, said: str, *, model_calls=(), apply=None):
    """Runs `post_stream_words.hold_the_model_to_its_words` on a turn that called nothing that ran."""
    from nucleo.flash import post_stream_words as psw
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
    out = asyncio.run(psw.hold_the_model_to_its_words(
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
    assert pk.close(said, t.data_done["promise"], acted=t.acted["widget"]) == ""


def test_voice_a_claim_after_a_discarded_op_is_not_delivered_as_done(client, silent_jev, monkeypatch):
    """T18 of the measured session: the model re-emitted `youtube:channel_videos`, a guard discarded it, the reply
    said «ya está». The pass asks the card the model named; its call is swallowed again; the turn says so."""
    from nucleo.flash import canvas_visibility
    from widgets import runtime
    monkeypatch.setattr(canvas_visibility, "open_ids", lambda: frozenset())
    monkeypatch.setattr(runtime, "get", lambda wid: {"actions": {"channel_videos": {"desc": "channel videos"}}})
    dropped = {"name": "widget_data", "args": {"widget_id": "youtube", "action": "channel_videos", "payload": {}}}
    client.answer = [("widget_data", dropped["args"])]
    said = "…ya está: te dejo abierta su pestaña de vídeos con los más recientes."
    t = _voice_turn("Quiero que lo hagas directamente.", said, model_calls=[dropped], apply="swallow")
    assert t.applied, "the card the model named was never asked"
    assert t.data_done["promise"]["kind"] == pk.SWALLOWED and not t.acted["widget"]
    line = pk.close(said, t.data_done["promise"], acted=t.acted["widget"])
    assert line, "a claim over nothing reached him unqualified"


# ── both channels end the turn through the same door ────────────────────────────────────────────────────

def test_the_voice_turn_end_says_it_after_the_backstop():
    from tests import voice_turn_source as _vts
    from pathlib import Path
    src = _vts.read(Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/turn_after.py")
    j = src.index("_promise_kept.say_after(spoken_text, data_done, send=send")
    call = src[j:src.index("\n\n", j) if "\n\n" in src[j:] else j + 900]
    # its `acted` argument RUNS the backstop first — which may still route the words to a worker
    assert "acted=(\n        _promise_backstop.run(spoken_text" in call, call


@pytest.mark.parametrize("routed", ["routed", "asked"])
def test_a_backstop_that_routed_or_asked_owes_no_line(routed, monkeypatch):
    monkeypatch.setattr("nucleo.turn.reply.owes_an_act", lambda b: "order")
    turn = ("ORDER", [], "x", None)
    assert pk.close("Me pongo con ello ahora mismo.", {}, acted=bool(routed), brief="ORDER") == ""
    said: list = []
    window = [{"role": "assistant", "content": "Lo hago ahora mismo."}]
    speech = SimpleNamespace(sanitize=lambda t, **k: t)
    pk.say_after("Lo hago ahora mismo.", {}, acted=routed, send=said.append, speech=speech, window=window, emit=None,
                 turn=turn)
    assert not said
    pk.say_after("Lo hago ahora mismo.", {}, acted="", send=said.append, speech=speech, window=window, emit=None,
                 turn=turn)
    assert said and window[-1]["content"].endswith(said[0].strip()), "the line is said AND kept in the window"
