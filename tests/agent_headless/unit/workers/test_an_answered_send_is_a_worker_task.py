"""V2-851 F2e — an answered question about an act that LEAVES is an identified task; a view never ends a send.

Measured after F2d: the answer re-ran one Flash text turn «request — answer», and in 6 of 14 of those turns the model
said «sending it now» and called nothing — the row stayed running until a sweep failed it. And a turn whose model
first called a lens of the card (`show_view`) settled the request's row `done`, so the question it then asked could
not wait on it and was never counted.

Now (1) the answer starts ONE Brain Worker on the same row, with the `message` playbook, his request + his answer as
its brief and the send's echo as `done_when`; a plain pick among a door's declared candidates still re-runs the kept act
with no model. (2) A non-leaving act on a card that declares leaving acts writes the row's ending only when its turn
closes without our question about that card — and never when the turn's verdict identifies the leaving act.
"""
from __future__ import annotations

from tests.voice_turn_source import read as _vts_read

import ast
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo.circuit import asker
from nucleo.cli import worker_api
from nucleo.request import answered_task, ask_outside_door, ending, inline_ask, model

ROOT = Path(__file__).resolve().parents[4]
SAID = "Send Rachel a message saying I'll be ten minutes late"
Q = "There are two Rachels: Rachel Green and Rachel Stone. Which one?"
CANDS = ["Rachel Green", "Rachel Stone"]
MEASURED = {"trace": "t-1", "widget": "mensajeria", "leaves": ending.leaving_acts("mensajeria"), "which_person": True}
ASK = {"ok": False, "message": "Which Rachel?", "slot": "contact", "candidates": CANDS}
ACT = {"contact": "Rachel", "text": "ten minutes late"}


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    for d in (inline_ask._RECENT, inline_ask._TAKEN, inline_ask._RESUMING):
        d.clear()
    events, started, ran = [], [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, **(extra or {})}))
    from widgets.contactos import data as contacts
    monkeypatch.setattr(contacts, "people_named", lambda text, limit=4: [{"name": n} for n in CANDS])
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda request, *, context=None, task_id=0: started.append((request, context)) or 11)
    import nucleo.cli.turn as cli_turn

    async def _no_turn(*a, **kw):
        raise AssertionError("an answer never re-runs a model turn")
    monkeypatch.setattr(cli_turn, "run_turn", _no_turn)
    yield SimpleNamespace(events=events, started=started, ran=ran, monkeypatch=monkeypatch)
    model._TURN.set(None)
    for d in (inline_ask._RECENT, inline_ask._TAKEN, inline_ask._RESUMING):
        d.clear()
    memdb.reset_db()
    mememb.reset()


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed"), visible_only=False)


def _door_row(fresh):
    from nucleo.flash import data_ops

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        fresh.ran.append({"wid": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True}
    fresh.monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    now = int(time.time())
    ts.task_put({"id": "b0-i1", "goal": SAID, "title": "Rachel", "kind": "inline", "state": "running",
                 "created_at": now, "started_at": now})
    return inline_ask.held("b0-i1", "mensajeria", "send_to", ACT, ASK)


def test_an_answered_question_about_a_send_is_one_worker_on_the_same_row(fresh):
    model.begin(SAID, trace="t-1")
    ask_id = ask_outside_door.held(MEASURED, Q, SAID)
    uid = _rows()[0]["id"]
    assert asyncio.run(worker_api.answer(ask_id, "the first one", choice=0)) is True
    assert len(fresh.started) == 1, "one worker, through the one errand portal"
    request, ctx = fresh.started[0]
    assert request == f"{SAID} — {CANDS[0]}"
    assert (ctx["task_uid"], ctx["answers"], ctx["playbook"], ctx["chosen"]) == (uid, ask_id, "message", f"{ask_id}#0")
    clauses = ctx["done_when"]["any"]
    assert clauses and all(c["widget"] == "mensajeria" and c["collection"] == "sent" for c in clauses)
    assert all(CANDS[0] in c["where"].values() for c in clauses), "the end state is the echo of a send to her"
    row = ts.task_get(uid)
    assert len(_rows()) == 1 and (row["state"], row["playbook"]) == ("running", "message")
    asyncio.run(inline_ask.rerun(uid, dict(asker.artefact(uid), state="pending"), "x", 0))
    assert len(fresh.started) == 1, "one answer starts at most one worker"
    from nucleo import his_words
    assert CANDS[0] in his_words.since(0), "the candidate he picked is his naming of her, for the send door"


def test_an_inline_row_a_worker_carries_survives_the_orphan_sweep_after_a_restart(fresh):
    from nucleo.circuit import ledger
    now = int(time.time())
    ts.task_put({"id": "0000aa-i1", "goal": SAID, "title": "x", "kind": "generic", "state": "running",
                 "created_at": now - 600, "started_at": now - 600})
    ledger.reconciled({"0000aa-i1"}, now=now)
    assert ts.task_get("0000aa-i1")["state"] == "running", "a previous boot's inline id a live worker carries"
    ledger.reconciled(set(), now=now)
    assert ts.task_get("0000aa-i1")["state"] == "failed", "nobody carries it: interrupted, as before"


def test_a_free_answer_about_a_send_goes_to_the_worker_with_no_guessed_end_state(fresh):
    ask_id = _door_row(fresh)
    asyncio.run(worker_api.answer(ask_id, "the one from work"))
    assert fresh.ran == [], "a free answer is not bound into the kept act"
    (request, ctx), = fresh.started
    assert request == f"{SAID} — the one from work" and ctx["task_uid"] == "b0-i1"
    assert "done_when" not in ctx and "chosen" not in ctx, "nobody chosen: the errand's birth asks its end state once"


def test_a_plain_pick_reruns_the_kept_act_with_no_model(fresh):
    ask_id = _door_row(fresh)
    asyncio.run(worker_api.answer(ask_id, "Rachel Stone", choice=1))
    assert fresh.started == [] and fresh.ran[0]["payload"]["contact"] == "Rachel Stone"
    assert answered_task.deterministic({"retained": {"kind": "utterance", "candidates": CANDS}}, 0) is False


def _view(fresh):
    import widgets
    from nucleo.flash import data_ops

    async def _tag(tag, data):
        return {"ok": True}
    fresh.monkeypatch.setattr(widgets, "dispatch_tag", _tag)
    model.begin(SAID, trace="t-1")
    asyncio.run(data_ops.dispatch_and_report("mensajeria", "show_view", {"platform": "telegram"}, text=SAID))
    (row,) = _rows()
    return row["id"]


def test_a_view_of_the_card_does_not_end_a_request_about_a_send(fresh):
    uid = _view(fresh)
    assert ts.task_get(uid)["state"] == "running" and ending.only_held(), "the view counts as no act on the send"
    assert ask_outside_door.held(MEASURED, Q, SAID), "our question about the send makes THAT row wait"
    ending.close_turn()
    assert ts.task_get(uid)["state"] == "waiting" and len(_rows()) == 1


def test_a_view_ends_its_own_request_when_the_turn_closes_without_a_question(fresh):
    uid = _view(fresh)
    assert ending.close_turn() == 1 and ts.task_get(uid)["state"] == "done"


def test_a_send_in_the_same_turn_writes_the_end_and_the_held_view_does_not(fresh):
    uid = _view(fresh)
    assert ending.hold("mensajeria", "send_to", uid) == ""
    assert ending.close_turn() == 0 and ts.task_get(uid)["state"] == "running", "the send's echo writes the end"


def test_a_verdict_naming_the_send_never_lets_a_view_end_the_row(fresh):
    fresh.monkeypatch.setattr(ending, "verdict_names_leaving", lambda brief, wid: True)
    uid = _view(fresh)
    ending.close_turn()
    assert ts.task_get(uid)["state"] == "running", "the row's end is the send's echo"


def test_a_leaving_act_or_a_write_of_its_own_writes_its_ending_as_always(fresh):
    model.begin(SAID, trace="t-1")
    assert ending.hold("mensajeria", "send_to", "r1") == "" and not ending.only_held()
    assert ending.hold("agenda", "cancel_meeting", "r1") == "", "a write of its own is its own request's end"
    assert ending.hold("agenda", "find_free", "r1") == "", "an act that answers is its own request's end"
    assert ending.hold("mensajeria", "draft", "r1") == ending.TURN, "a draft only prepares the send"
    assert ending.hold("agenda", "not_a_declared_act", "r1") == "", "an act nobody declared is never held"
    assert ending.hold("agenda_x_unknown", "show", "r1") == ""


def test_the_turn_end_reads_the_held_ops_and_closes_the_turn():
    src = _vts_read(ROOT / "nucleo/turn/pipeline_close.py")
    names = {getattr(n.func, "attr", "") for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)}
    assert {"only_held", "close_turn"} <= names


def test_an_answered_task_skips_the_dedup_by_identity():
    src = (ROOT / "nucleo/dispatch/listener.py").read_text()
    assert 'ctx.get("answers")' in src and "if _bound else _d.dedup_scan(" in src
