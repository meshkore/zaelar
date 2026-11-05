"""A worker's act that leaves crosses its exit door before ANY question, and again on his yes (V2-852, CRIT-T2b).

Two holes of the same class. The «a person his words never named» question (`on_his_behalf.worker_question`) used to
skip `exit_gate.gate` entirely, and his yes then ran the retained act straight (`_exec_allow`): a worker that never
named its playbook sent once he said yes, past checkpoint 1. And the act's own refusal was only read by an inline
confirmation Flash no longer opens for a send, so a worker could be asked about a reply that answers nothing. Now
the door holds first — checkpoint 1, the act's own refusal (`widgets.contract.would_refuse`), his recipient — then
any question is asked, and the retained act crosses the door again before it runs. ES and EN.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from nucleo import his_words, untrusted


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api, worker_api_answer
    from widgets import server_api
    untrusted.reset()
    his_words.reset()
    sent = []

    async def _brain_action(wid, act, payload):
        sent.append((wid, act, dict(payload)))
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _brain_action)
    monkeypatch.setattr(worker_api, "classify_act", lambda *_a: worker_api.ALLOW)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    monkeypatch.setattr(worker_api_answer, "_says_yes", lambda *_a: True)
    rec = SimpleNamespace(task_id="xd", playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="",
                          surface="", sheet="", native_sid="", waiting_on="", ask="", ask_corr="", parked=False,
                          mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: rec)
    worker_api._ACTS.clear()
    yield SimpleNamespace(api=worker_api, rec=rec, sent=sent)
    worker_api._ACTS.clear()
    untrusted.reset()
    his_words.reset()


def _asked(d) -> bool:
    return any(e.get("state") == "pending" for e in d.api._ACTS.values())


def _act(d, action="send_to", payload=None):
    out = asyncio.run(d.api.worker_act(task_id="xd", token="t", action="widget_data", payload={
        "widget_id": "mensajeria", "action": action,
        "payload": payload if payload is not None else {"to": "+34600999888", "text": "¿tenéis cita?",
                                                        "platform": "whatsapp"}}))
    return json.loads(out.body)


# ── H4 · the «somebody he never named» question no longer skips the door ─────────────────────────────────────────

@pytest.mark.parametrize("said", ["busca un fontanero en Madrid y pide cita", "find a plumber in Madrid and book"])
def test_an_unnamed_recipient_is_still_held_by_checkpoint_one_before_the_question(door, said):
    his_words.note(said)
    door.rec.playbook_chosen = ""
    got = _act(door)
    assert got.get("ok") is False and "checkpoint 1" in str(got.get("error")), got
    assert door.sent == [] and not _asked(door)


def test_with_checkpoint_one_closed_the_unnamed_recipient_is_asked(door):
    his_words.note("find a plumber in Madrid and book")
    got = _act(door)
    assert got.get("status") == "pending" and door.sent == [], got


def test_his_yes_runs_the_retained_act_only_through_the_door_again(door, monkeypatch):
    """The yes answers the question, never the door: a retained act whose task lost checkpoint 1 is refused on the yes."""
    his_words.note("find a plumber in Madrid and book")
    got = _act(door)
    door.rec.playbook_chosen = ""
    assert asyncio.run(door.api.answer(got["corr_id"], "yes", resume=False))
    assert door.sent == [] and "checkpoint 1" in str(door.api._ACTS[got["corr_id"]]["result"].get("error"))


def test_his_yes_sends_when_the_door_lets_it(door):
    his_words.note("find a plumber in Madrid and book")
    got = _act(door)
    assert asyncio.run(door.api.answer(got["corr_id"], "yes", resume=False))
    assert [s[1] for s in door.sent] == ["send_to"]


def test_disarmed_the_question_skips_the_door_again(door, monkeypatch):
    """Disarm: the door crossed only when nothing is asked (the old order) → checkpoint 1 is bypassed by the question."""
    from nucleo.workers import exit_gate
    real = exit_gate.gate
    monkeypatch.setattr(exit_gate, "gate", lambda rec, p: exit_gate.Exit(p) if (rec.playbook_chosen == "") else real(rec, p))
    his_words.note("find a plumber in Madrid and book")
    door.rec.playbook_chosen = ""
    got = _act(door)
    assert got.get("status") == "pending", "the disarm did not take: the door still held"


# ── H5 · a call the act would refuse is never asked about ──────────────────────────────────────────────────────

@pytest.mark.parametrize("said", ["contesta a Raquel que la esperamos", "reply to Raquel that we're waiting"])
def test_a_reply_that_answers_nothing_is_refused_at_the_door_before_any_question(door, said):
    his_words.note(said)
    got = _act(door, "reply", {"text": "Te esperamos en casa."})
    assert got.get("ok") is False and "would be refused" in str(got.get("error")), got
    assert door.sent == [] and not _asked(door)


def test_disarmed_the_acts_refusal_is_asked_about(door, monkeypatch):
    from widgets import contract
    monkeypatch.setattr(contract, "would_refuse", lambda *_a: None)
    his_words.note("reply to Raquel that we're waiting")
    got = _act(door, "reply", {"text": "Te esperamos en casa."})
    assert got.get("status") == "pending" or got.get("ok"), "the disarm did not take"
