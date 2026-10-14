"""A status answer beside a refinement the turn SENT names the refined errand too (node 2.644).

three-tasks-at-once (EN, 2026-10-14 02:44, sandbox 023306-en): «those are too small, need at least 27 inches. hows
the game coming?» — the model sent the 27" floor to the monitor's worker (`send_to_worker`) and said nothing; the
status line owed to the question answered the game alone («Here's where everything stands: Build a Super
Mario-style … — under way, nothing new yet.»), so the refinement that DID land was never acknowledged. The status
line now carries the errands the turn's own sends reached (`split_by_errand.status_with_refined`), in both channels.
"""
from __future__ import annotations

import asyncio
import threading
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.turn import errands_of_a_turn as E
from nucleo.turn import split_by_errand as S

GAME = {"id": "6", "request": "Build a small platform game widget, Super Mario style: run and jump", "phase": "",
        "waiting_on": ""}
MONITOR = {"id": "3", "request": E.listing_errand({"query": "used monitor cheap"}), "phase": "", "waiting_on": ""}
TITLES = {"6": "Build a Super Mario-style platformer game", "3": "Marketplace listings for used cheap monitor"}
HIS = "those are too small, need at least 27 inches. hows the game coming?"


def _brief():
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {"wants_words": {"choice": "tell", "confidence": 0.99, "probs": {"tell": 0.99}},
                                    "request_type": {"choice": "question", "confidence": 0.99,
                                                     "probs": {"question": 0.99}}},
            "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.fixture(autouse=True)
def _three_tasks(monkeypatch):
    S.forget()
    monkeypatch.setattr("i18n.langs.current_code", lambda: "en")
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(GAME), dict(MONITOR)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(
        label="", title=TITLES.get(tid, ""), goal=""))
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda which: ["3"] if "monitor" in str(which) else [])
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr("nucleo.flash.escalate.pending", lambda: [])
    monkeypatch.setattr("nucleo.workers.ended.recently_ended_sessions", lambda **k: [])
    yield
    S.forget()


def test_the_status_names_the_refined_errand_too():
    line = S.status_with_refined(HIS, _brief(), ["Marketplace listings for used cheap monitor"])
    assert "Super Mario" in line, line                                   # the question is answered
    assert "passed that on to «Marketplace listings for used cheap monitor»" in line, line


def test_a_refined_errand_the_status_already_names_is_not_said_twice():
    line = S.status_with_refined("how's the game and the monitor coming?", _brief(),
                                 ["Marketplace listings for used cheap monitor"])
    assert "passed that on" not in line, line


def test_the_text_channel_says_both():
    from nucleo.flash import probe_after
    out = asyncio.run(probe_after.the_words_it_owes(
        _hw=True, _parts=None, _show_chose="", action="send_to_worker", images_req=None,
        return_extra_exec={"executed": "inject", "sent": 1, "to": ["Marketplace listings for used cheap monitor"]},
        sess=types.SimpleNamespace(window=[]), spoken="", tags=[], text=HIS, video_req=None, brief=_brief()))
    said = out["spoken"]
    assert "Super Mario" in said and "used cheap monitor" in said, said


def test_the_voice_channel_reads_the_sends_of_its_turn():
    S.note_sent("the monitor search")
    line = S.status_with_refined(HIS, _brief())
    assert "Super Mario" in line and "«Marketplace listings for used cheap monitor»" in line, line
    assert "passed that on" not in S.status_with_refined(HIS, _brief()), "a send is said once"


def test_the_voice_executor_notes_its_sends(monkeypatch):
    from nucleo.flash import tool_executor_calls as T
    monkeypatch.setattr(dispatch, "inject_soon", lambda which, msg: None)
    T._t_send_to_worker(args={"which": "the monitor search", "message": "at least 27 inches"},
                        emit=lambda *a, **k: None, worker_acted={"v": None})
    assert "«Marketplace listings for used cheap monitor»" in S.status_with_refined(HIS, _brief())


def test_the_voice_status_line_is_the_one_that_names_the_sends():
    """The wiring of the voice half: a mute turn that sent to a worker owes the status WITH the sends."""
    import inspect
    from nucleo.flash import post_stream_settle
    src = inspect.getsource(post_stream_settle.settle_what_is_pending)
    assert "_sbe.status_with_refined(operator_text, _brief)" in src and "_eot.status_owed(" not in src
