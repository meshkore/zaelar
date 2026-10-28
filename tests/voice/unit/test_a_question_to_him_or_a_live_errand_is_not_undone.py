"""A turn that ends by asking HIM, or that reports on a worker already running on what he named, owes no «I haven't
done it» (node 2.923).

Live replay, 2026-10-28 (build 405c4627b): «check the chat» → «…20 chats with something pending… Which one do you
mean — SOMOS Invernadero, Luis, or the ones about the Dexter question?» + «I haven't done it — I couldn't carry it out
from here.»; «contonue with my desxter request» while the Dexter worker ran → «…the background check is still on the
Dexter question and hasn't reported back yet…» + the same line. The brief read both as orders and nothing ran in the
turn, so `owed` said the line was due; the two facts that say otherwise were not read: the reply's verdict is «asked»
when it ends with a question to him, and «started» when a live errand already carries his request.

The live errand is found by its ROW (V2-831 T-07): the turn's verdict over the pending rows (`resume_turn`, reached
from `before_backstops` when a tool-less turn owes an act) picks the live row, `resume` lists it without starting it
twice, and the turn has acted. The word reader it replaced (`an_errand_is_live_for`, a word of his turn inside the
session goal) returned False on the very typo the operator typed.

«The reply asks him» is the circuit's `asked` verdict (V2-831 T-08), never a «?»: the model DECLARES it with the
`[[ask]]` tag of the silent tag protocol (stripped from speech), the clarify door settles it when its question is the
line, and `honest_line` reads that verdict. The same question with no tag still says undone — punctuation is not read.

Disarm: with `ask` dropped from `TAG_RE`, the tag tests go red; with the clarify door's `settle_asked` removed, the
door test; with `before_backstops` not consulting the rows, the live-row tests.
"""
from __future__ import annotations

import pytest

from nucleo.turn import promise_kept as pk
from nucleo.turn import reply as R

ORDER = "a brief that reads an order"


@pytest.fixture(autouse=True)
def _order(monkeypatch):
    monkeypatch.setattr(R, "owes_an_act", lambda brief: "order" if brief == ORDER else "")
    monkeypatch.setattr(pk, "_state_holds", lambda open_ids=None: False)
    monkeypatch.setattr(pk, "words_were_the_act", lambda brief: False)
    monkeypatch.setattr(pk, "_not_kept_line", lambda: "I haven't done it.")
    monkeypatch.setattr(R, "_trace", lambda: "t2923")    # one turn per test (its `_ASKED` starts empty)
    monkeypatch.setattr(R, "_ASKED", {})


def _stream(reply: str) -> str:
    """The reply through the REAL tag parser and the REAL tag handler, as the voice turn streams it. Returns what
    would be spoken."""
    from types import SimpleNamespace
    from nucleo.flash import tool_executor_widget_calls as txc
    from voice.tag_protocol import strip_tags
    state = {"v": None, "more": []}
    kw = dict(_apply_widget_data=None, _brief=None, _is_meta_widget_question=None, _norm_nfkd=None,
              _on_tool_call=None, _request_delete_confirm=None, _show_guard_target=None, _show_target_instance=None,
              _shown_ids=set(), _spawn=None, acted={"widget": False}, aside={"v": False}, brain=SimpleNamespace(),
              canvas_h=None, cron_seen=set(), deduped=set(), emit=lambda *a, **k: None, escalate_req=state, text="")
    spoken, _rest = strip_tags(reply, lambda action, extra: txc._tag_emit(action, extra, **kw), True)
    return spoken


@pytest.mark.parametrize("reply", [
    "There are 20 chats with something pending. Which one do you mean — Luis, or the ones about Dexter? [[ask]]",
    "Hay 20 chats con algo pendiente. ¿Cuál quieres, el de Luis o el de la cena?[[ask]]",
    "Which one exactly? I have «comedor del niño» 2026-10-28 14:30 and 2026-10-29 14:30. [[ask]]",
])
def test_a_reply_that_declares_it_asks_him_owes_nothing(reply):
    spoken = _stream(reply)
    assert "[[" not in spoken and spoken.strip(), f"the tag is never spoken: {spoken!r}"
    assert R.asked()
    assert pk.honest_line(spoken, {}, acted=False, brief=ORDER) == ""


@pytest.mark.parametrize("reply", [
    "Which one do you mean — Luis, or the ones about Dexter?",
    "¿Cuál quieres, el de Luis o el de la cena?",
])
def test_the_same_question_without_the_declaration_is_not_read_from_punctuation(reply):
    assert not R.asked()
    assert pk.honest_line(_stream(reply), {}, acted=False, brief=ORDER) == "I haven't done it."


def test_the_clarify_doors_question_settles_asked():
    """The door already knows it asks: when its question becomes the turn's line, the verdict is `asked`."""
    import asyncio
    from types import SimpleNamespace
    from nucleo.flash import post_stream_settle
    said = []
    asyncio.run(post_stream_settle.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=None,
        _dialog=SimpleNamespace(sanitize_reply=lambda s: s), _filler_audio=SimpleNamespace(played_recently=lambda: False),
        _langs=None, _prev_pending=[], _r=None, _resolve_confirm=lambda yes: None,
        _router=SimpleNamespace(looks_like_stop_work=lambda t: False, operator_words=lambda o, t: o),
        _shown_ids=set(), acted={"widget": False}, aside={"v": False},
        brain=SimpleNamespace(_window=[], _last_spoken=""), clarify={"msg": "¿Cuál de las dos, la de las 14:30?"},
        confirm_state={"handled": True}, data_done={"v": None}, emit=lambda *a, **k: None,
        escalate_req={"v": None, "more": [], "surface": {}}, had_pending_confirm=False, llm_metrics={},
        music_req={"v": None}, operator_text="borra la cita", search_req={"v": None}, send=said.append,
        speech=SimpleNamespace(sanitize=lambda s, drop_metadata=True: s), spoken_text="Hecho.",
        style_fired={"v": False}, text="borra la cita", worker_acted={"v": None}))
    assert said and "14:30" in said[0]
    assert R.asked()
    assert pk.honest_line(said[0], {}, acted=False, brief=ORDER) == ""


def test_a_claim_that_asks_nothing_is_still_said_undone():
    assert pk.honest_line(_stream("Done, I've cleared your chats."), {}, acted=False, brief=ORDER) \
        == "I haven't done it."


def _report_turn(monkeypatch, operator_text: str, *, rows: list, pick) -> bool:
    """A tool-less turn that owes an act, as the voice turn runs it: the rows first, then the turn end's `acted`."""
    import asyncio
    from nucleo import jev, pending_work
    from nucleo.flash import resume_turn
    resume_turn.reset()
    acted, req = {"widget": False}, {"v": None, "more": []}
    monkeypatch.setattr(pending_work, "rows", lambda now=None: list(rows))
    monkeypatch.setattr(jev, "select_many",
                        lambda rs, criteria, key=None, label=None: [{"candidate": r} for r in rs if r["id"] == pick])
    try:
        asyncio.run(resume_turn.before_backstops(True, req, spoken_text="", operator_text=operator_text, brief=ORDER,
                                                 last_reply="", apply_widget_data=None, emit=None, acted=acted))
    finally:
        resume_turn.reset()
    return bool(acted["widget"])


DEXTER_LIVE = {"id": "boot-9f15b8-1", "source": "task", "state": "running", "kind": "web", "at": 1.0,
               "title": "Verify where Dexter: Resurrection S2 streams in Spain", "brief": "", "outcome": "", "sheet": ""}
HOTEL_LIVE = {"id": "boot-77aa-2", "source": "task", "state": "waiting", "kind": "web", "at": 2.0,
              "title": "Hotel cerca de la Plaza Mayor de Salamanca", "brief": "", "outcome": "", "sheet": ""}


@pytest.mark.parametrize("words,pick", [
    ("contonue with my desxter request", DEXTER_LIVE["id"]),             # the live typo
    ("¿cómo va lo del hotel?", HOTEL_LIVE["id"]),                       # another language, another errand
])
def test_a_status_report_on_a_live_errand_found_by_its_row_owes_nothing(words, pick, monkeypatch):
    acted = _report_turn(monkeypatch, words, rows=[DEXTER_LIVE, HOTEL_LIVE], pick=pick)
    assert acted
    reply = "The background check is still on it and hasn't reported back yet."
    assert pk.honest_line(reply, {}, acted=acted, brief=ORDER) == ""


def test_a_turn_whose_verdict_picks_no_live_row_is_still_said_undone(monkeypatch):
    acted = _report_turn(monkeypatch, "book me a dentist", rows=[DEXTER_LIVE, HOTEL_LIVE], pick=None)
    assert not acted
    assert pk.honest_line("On it.", {}, acted=acted, brief=ORDER) == "I haven't done it."
