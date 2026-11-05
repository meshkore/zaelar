"""V2-851 F1e — a door that answers an INLINE act with a consent ASK makes THAT row wait, through the one asker.

Before: «send a message to Raquel» with two Raquels refused inline, the turn said the question, and the row ended
`failed` — no durable question, no `ask_id`, no answer by screen. Now the row waits for his answer with the act it
retains on its `ask` artefact, the `ask` event is the worker's own, and the answer re-runs THAT act on THAT row with
the candidate the binding verdict chose — never a new row, never a model run.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo.circuit import asker
from nucleo.cli import worker_api, worker_api_bind as bind
from nucleo.request import inline_ask
from nucleo.turn import verdicts

ASK = {"ok": False, "say": "", "message": "Which Raquel: Raquel Gómez or Raquel Martín?", "slot": "contact",
       "candidates": ["Raquel Gómez", "Raquel Martín"]}
ACT = {"contact": "Raquel", "text": "llego tarde"}


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    events, ran = [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, **(extra or {})}))
    from nucleo.flash import data_ops

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        ran.append({"wid": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True}
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    now = int(time.time())
    ts.task_put({"id": "b0-i1", "goal": "send Raquel I'm late", "title": "Raquel", "kind": "inline",
                 "state": "running", "created_at": now, "started_at": now})
    yield SimpleNamespace(events=events, ran=ran)
    memdb.reset_db()
    mememb.reset()


def _held():
    return inline_ask.held("b0-i1", "mensajeria", "send_to", ACT, ASK)


def test_a_door_ask_makes_its_row_wait_with_the_retained_act(fresh):
    ask_id = _held()
    row = ts.task_get("b0-i1")
    assert ask_id and (row["state"], row["waiting_for"], row["ask_id"]) == ("waiting", "user_answer", ask_id)
    assert row["ask"] and row["session_id"], "the question is durable on the row, which carries its session"
    art = asker.artefact("b0-i1")
    assert art["inline"] and art["retained"] == {"widget": "mensajeria", "action": "send_to", "payload": ACT,
                                                 "slot": "contact", "candidates": ASK["candidates"]}
    asks = [e for e in fresh.events if e["kind"] == "ask"]
    assert len(asks) == 1 and (asks[0]["task_id"], asks[0]["ask_id"]) == ("b0-i1", ask_id)


def test_a_plain_refusal_asks_nothing(fresh):
    assert inline_ask.held("b0-i1", "mensajeria", "send_to", ACT, {"ok": False, "message": "no channel"}) == ""
    assert ts.task_get("b0-i1")["state"] == "running"
    assert inline_ask.verdict_of({"ok": False, "candidates": ["only one"], "slot": "contact"}) is None


def test_the_screen_option_reruns_the_act_on_the_same_row(fresh):
    ask_id = _held()
    assert asyncio.run(worker_api.answer_task("b0-i1", ask_id, "Raquel Martín")) is True
    assert fresh.ran == [{"wid": "mensajeria", "action": "send_to", "row": "b0-i1",
                          "payload": {"contact": "Raquel Martín", "text": "llego tarde"}}]
    assert ts.task_get("b0-i1")["state"] == "running" and len(ts.tasks_where(states=("running", "waiting"),
                                                                              visible_only=False)) == 1


def test_the_verdict_chooses_the_candidate_never_his_words(fresh, monkeypatch):
    ask_id = _held()
    asks = worker_api.open_asks()
    q = bind.question(asks)
    assert {f"{ask_id}#0", f"{ask_id}#1", bind.NONE} == set(q["criteria"]), "one choice per declared candidate"
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None: (f"{ask_id}#1", {"confidence": .9}))
    how, got = bind.bind(None, asks=asks)
    assert how == bind.ANSWER and got[0]["choice"] == 1
    asyncio.run(worker_api.answer(ask_id, "la segunda", choice=got[0]["choice"]))
    assert fresh.ran[0]["payload"]["contact"] == "Raquel Martín" and fresh.ran[0]["row"] == "b0-i1"


def test_a_bare_question_id_over_candidates_is_asked_which(fresh, monkeypatch):
    ask_id = _held()
    monkeypatch.setattr(verdicts, "read", lambda h, key, fb, min_confidence=None: (ask_id, {"confidence": .9}))
    assert bind.bind(None)[0] == bind.ASK_WHICH


def test_the_same_act_naming_a_candidate_is_his_answer_on_that_row(fresh):
    _held()
    assert inline_ask.claim("mensajeria", "send_to", {"contact": "Raquel Gómez", "text": "x"}) == ("b0-i1", False)
    assert ts.task_get("b0-i1")["state"] == "running" and not worker_api.open_asks()
    assert inline_ask.claim("mensajeria", "send_to", {"contact": "Raquel Gómez"}) == ("b0-i1", True), \
        "the act already ran on his answer: a second call is the same act, never a second send"
    assert inline_ask.claim("mensajeria", "send_to", {"contact": "Lucía"}) == ("", False)


def test_the_data_op_door_holds_its_row_instead_of_failing_it(tmp_path, monkeypatch):
    """The cable: a refused data-op whose result is a consent ASK leaves its inline row WAITING, never `failed`."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    import widgets
    from nucleo.flash import data_ops
    from nucleo.request import model as rq

    async def _tag(tag, data):
        return dict(ASK)
    monkeypatch.setattr(widgets, "dispatch_tag", _tag)
    rq.begin("send Raquel I'm late", trace="t-1")
    try:
        asyncio.run(data_ops.dispatch_and_report("mensajeria", "send_to", dict(ACT), text="send Raquel I'm late"))
        rows = ts.tasks_where(states=("waiting", "failed", "running", "done"), visible_only=False)
        assert [(r["state"], r["waiting_for"], bool(r["ask_id"])) for r in rows] == [("waiting", "user_answer", True)]
    finally:
        memdb.reset_db()
        mememb.reset()
