"""V2-851 F2d — a question Flash asks ITSELF about a door's act is as durable as the door's own.

Measured: «send a message to Raquel» with two Raquels; the model answered «which Raquel?» without calling the send
door, so nothing waited and no question had an id. Now the turn's row waits through the one asker with his REQUEST
retained, the candidates are the directory's, and his answer hands the row to ONE Brain Worker (F2e) on that same
row — once per answer, whoever triggers it.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo.circuit import asker
from nucleo.cli import worker_api
from nucleo.request import inline_ask, model, own_question

ROOT = Path(__file__).resolve().parents[4]
SAID = "Mándale un mensaje a Raquel diciéndole que llego tarde"
Q = "Hay dos Raquel: Raquel Gómez y Raquel Martín. ¿A cuál se lo mando?"
CANDS = ["Raquel Gómez", "Raquel Martín"]
MEASURED = {"trace": "t-1", "widget": "mensajeria", "leaves": ["reply", "send_to"], "which_person": True}


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    events, turns, started = [], [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, **(extra or {})}))
    from widgets.contactos import data as contacts
    monkeypatch.setattr(contacts, "people_named", lambda text, limit=4: [{"name": n} for n in CANDS])

    async def _turn(text, *, sid, execute):
        model.begin(text, trace="t-2")          # what the voice turn does first: its ops find the resumed row
        claimed = inline_ask.claim("mensajeria", "send_to", {"contact": CANDS[1], "text": "llego tarde"})
        turns.append({"text": text, "execute": execute, "claimed": claimed})
        return {"ok": True, "reply": ["Se lo mando."]}
    import nucleo.cli.turn as cli_turn
    monkeypatch.setattr(cli_turn, "run_turn", _turn)
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda request, *, context=None, task_id=0: started.append((request, context)) or 7)
    model.begin(SAID, trace="t-1")
    yield SimpleNamespace(events=events, turns=turns, started=started)
    model._TURN.set(None)
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    memdb.reset_db()
    mememb.reset()


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed"), visible_only=False)


def test_our_own_question_makes_the_turns_row_wait_with_his_request(fresh):
    ask_id = own_question.held(MEASURED, Q, SAID)
    rows = _rows()
    assert ask_id and len(rows) == 1
    row = rows[0]
    assert (row["state"], row["waiting_for"], row["ask_id"], row["ask"]) == ("waiting", "user_answer", ask_id, Q)
    assert row["session_id"], "the row carries the session that asked"
    ret = asker.artefact(row["id"])["retained"]
    assert ret == {"kind": "utterance", "text": SAID, "widget": "mensajeria", "actions": ["reply", "send_to"],
                   "slot": "", "candidates": CANDS}
    asks = [e for e in fresh.events if e["kind"] == "ask"]
    assert len(asks) == 1 and asks[0]["ask_id"] == ask_id and asks[0]["options"] == CANDS


def test_the_screen_answer_hands_the_same_row_to_one_worker_once(fresh):
    ask_id = own_question.held(MEASURED, Q, SAID)
    uid = _rows()[0]["id"]
    assert asyncio.run(worker_api.answer_task(uid, ask_id, CANDS[1])) is True
    assert fresh.turns == [], "no model turn is re-run for the answer"
    assert len(fresh.started) == 1, "one worker"
    request, ctx = fresh.started[0]
    assert request == f"{SAID} — {CANDS[1]}" and ctx["task_uid"] == uid and ctx["answers"] == ask_id
    assert len(_rows()) == 1 and _rows()[0]["state"] == "running"
    entry = dict(asker.artefact(uid), state="pending")
    asyncio.run(inline_ask.rerun(uid, entry, CANDS[1]))
    assert len(fresh.started) == 1, "a second trigger of the same answer starts nothing"


def test_the_answering_turns_own_call_is_the_same_answer(fresh):
    own_question.held(MEASURED, Q, SAID)
    uid = _rows()[0]["id"]
    model.begin("A Raquel Martín", trace="t-3")
    assert inline_ask.claim("mensajeria", "send_to", {"contact": CANDS[1]}) == (uid, False), \
        "the model calling the act with a declared candidate answers the waiting row"
    inline_ask.resuming(uid, asker.artefact(uid)["retained"])
    assert inline_ask.claim("mensajeria", "send_to", {"contact": CANDS[1]}) == (uid, True), \
        "while an answer resumes the request, the same act elsewhere is that answer — never a second send"
    assert inline_ask.claim("mensajeria", "send_to", {"contact": "Lucía"}) == ("", False)


def test_the_turn_end_makes_the_counted_question_durable():
    src = (ROOT / "voice/engine/llm/providers/turn_after.py").read_text()
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "held" and getattr(n.func.value, "id", "") == "_own_q"]
    assert calls, "the measured question reaches `own_question.held`"


def test_the_which_person_reading_falls_back_to_his_words():
    """The brief's judged text is not always ready at the turn's end: the directory then reads his own words."""
    src = (ROOT / "voice/engine/llm/providers/turn_after.py").read_text()
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "asked_which"]
    assert calls and "_op_text" in ast.unparse(calls[0].args[1])
