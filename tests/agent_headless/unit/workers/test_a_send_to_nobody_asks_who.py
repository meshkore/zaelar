"""V2-851 F5b — a send that names nobody is a missing FACT: the door asks who, and the row waits (battery C2 en).

Measured: the model called `send_to` with no contact at all; the card refused with a plain error, offered no question,
and the row ended `failed`. Consent doctrine (V2-712): a missing fact → ask for the FACT. The messaging door now answers
a missing recipient with `needs` + `slot` (ASK_FACT), so the inline door's asker makes the row wait on «who?» and his
answer fills `contact` on the retained act.

Disarm: drop `needs`/`slot` from the no-recipient refusal in `widgets/mensajeria/outbound/targets.py` → red.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo import consent
from nucleo.circuit import asker
from nucleo.request import inline_ask
from widgets.mensajeria.outbound import targets

ACT = {"text": "I'll be ten minutes late"}


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: None)
    now = int(time.time())
    ts.task_put({"id": "b0-i9", "goal": "send a message", "title": "message", "kind": "inline",
                 "state": "running", "created_at": now, "started_at": now})
    yield
    memdb.reset_db()
    mememb.reset()


@pytest.mark.parametrize("payload", [ACT, {**ACT, "contact": "  "}, {**ACT, "channel": "email"}])
def test_a_send_to_nobody_is_an_ask_for_the_fact(payload):
    res = targets.resolve_target(payload)
    assert res["ok"] is False and res["say"] == "widgets.mensajeria.refusal_who_to"
    assert inline_ask.verdict_of(res) == {"verdict": consent.ASK_FACT, "slot": "contact", "candidates": []}


def test_the_row_waits_on_who_and_his_answer_fills_the_contact(fresh):
    res = targets.resolve_target(ACT)
    ask_id = inline_ask.held("b0-i9", "mensajeria", "send_to", ACT, res)
    row = ts.task_get("b0-i9")
    assert ask_id and (row["state"], row["waiting_for"]) == ("waiting", "user_answer")
    retained = asker.artefact("b0-i9")["retained"]
    assert retained["slot"] == "contact" and retained["payload"] == ACT
    assert inline_ask.bound(retained, "Lucy", None)["contact"] == "Lucy"


def test_a_workers_send_to_nobody_meets_the_doors_question_not_a_consent_one(monkeypatch):
    """C2 es (screen answer): the worker's `send_to` named nobody, and the on-his-behalf gate asked «do you want the
    process to send_to?» — a consent question about an act with no recipient. The card declares the missing fact
    (`needs_of`), so the gate lets the door refuse and ask for it; a named stranger still asks his consent."""
    from types import SimpleNamespace

    from nucleo import his_words, on_his_behalf
    monkeypatch.setattr(his_words, "since", lambda *_a, **_k: [])
    rec = SimpleNamespace(task_id="1", started=time.time())
    call = {"widget_id": "mensajeria", "action": "send_to", "payload": dict(ACT)}
    assert on_his_behalf.worker_question(rec, "widget_data", call) == ""
    stranger = {**call, "payload": {**ACT, "contact": "Zebedee Quux"}}
    assert on_his_behalf.worker_question(rec, "widget_data", stranger) != ""
