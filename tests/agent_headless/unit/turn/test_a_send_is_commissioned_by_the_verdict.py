"""A send the brief identified is its task, whatever the model did instead of calling the door (2026-11-06).

Measured live (five cases, 0/5): the model never called `send_to` — it escalated a complete send (a worker
rediscovered it in 192 s, one exit-code-2 step), promised «Sending it now» with no call, asked «what should it say?» in
prose with no durable question, and on the answer turn the verdict completed the model with `dismiss`. Every time the
brief had already identified the send (`screen_action = mensajeria:send_to` 0.97-0.98, `end_state = mensajeria:sent`
0.82-0.92, `wants_words = act`), and every time the model had the words and QUOTED them.

So the turn's close and its escalation read the verdict (`send_task_words.by_verdict`): the person is his word, the
text is what the model quoted of his words (`quoted_his`: punctuation and his words, never a verb), the task runs with
no worker when every slot is his, waits on the one slot it lacks (the question the mouth already said becomes the
row's), or keeps the worker ON the row when the escalation lacked the words. A bound answer to a send task's question
is the words the model quoted of it. ES and EN; disarmed (`identified` blind) the verdict commissions nothing.
"""
from __future__ import annotations

import ast
import threading
from pathlib import Path

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import inline_ask, model, send_task, send_task_words as stw

ROOT = Path(__file__).resolve().parents[4]
WID, ACT = "mensajeria", "send_to"
CASES = {
    "es": {"said": "mándale un correo a Andrew diciendo: prueba uno del envío lineal, ignóralo",
           "text": "prueba uno del envío lineal, ignóralo",
           "escalation": 'Send an email to Andrew (andrew@example.com) with exactly this body: "prueba uno del envío '
                         'lineal, ignóralo". Just send it, no reply expected.',
           "bare": "mándale un mensaje a Andrew", "prose_q": "¿Qué quieres que le diga, Richard?",
           "promise": 'Enviando ahora mismo «prueba uno del envío lineal, ignóralo» a Andrew.'},
    "en": {"said": "send Andrew an email saying: test two of the linear send, ignore it",
           "text": "test two of the linear send, ignore it",
           "escalation": 'Email Andrew the body "test two of the linear send, ignore it" and nothing else.',
           "bare": "send a message to Andrew", "prose_q": "What should it say, Richard?",
           "promise": 'Sending it now — same as before, just "test two of the linear send, ignore it" to Andrew.'},
}


def _brief(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [WID],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Andrew Gold", "email": "andrew@example.com"})
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    sent, events = [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True, "result": {"to": "Andrew Gold", "channel": "email"}}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a worker was started")))
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, **(extra or {})})
                        or real(kind, label, text=text, role=role, extra=extra))
    yield {"sent": sent, "events": events, "emit": lambda *a, **k: events.append({"kind": a[0], "label": a[1], **(k.get("extra") or {})})}
    model._TURN.set(None)
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model.begin(text, trace="t-1")
    his_words.note(text)


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


def _asks(world):
    return [e for e in world["events"] if e["kind"] == "ask"]


SEND = dict(screen_action=(f"{WID}:{ACT}", 0.98), end_state=(f"{WID}:sent", 0.84), request_type=("order", 0.9),
            wants_words=("act", 0.98))


def test_the_brief_identifies_the_send_by_its_act_or_by_its_end_state():
    assert stw.identified(_brief(**SEND)) == (WID, ACT)
    assert stw.identified(_brief(screen_action=(f"{WID}:draft", 0.29), end_state=(f"{WID}:sent", 0.92))) == (WID, ACT)
    assert stw.identified(_brief(screen_action=(f"{WID}:show_view", 0.98))) == ("", "")
    assert stw.identified(_brief(end_state=("none", 0.9))) == ("", "")
    assert stw.identified(None) == ("", "")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_words_the_model_quoted_of_his_are_the_text(lang):
    c = CASES[lang]
    assert stw.quoted_his(c["said"], c["escalation"]) == c["text"]
    assert stw.quoted_his(c["said"], c["promise"]) == c["text"]
    assert stw.quoted_his(c["bare"], 'Sending "hello there" to Andrew now') == ""    # not his words
    assert stw.quoted_his(c["said"], "On it — emailing Andrew now.") == ""           # nothing quoted


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_escalation_that_quotes_his_words_runs_with_no_worker(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["said"])
    esc, acted = {"v": c["escalation"]}, {"v": None}
    uid, how = stw.by_verdict(_brief(**SEND), said=c["said"], model_text=esc["v"], escalate_req=esc,
                              worker_acted=acted, emit=world["emit"], on_missing="worker")
    assert uid and how == "run" and esc["send_task"]
    assert len(world["sent"]) == 1 and world["sent"][0]["payload"]["text"] == c["text"]
    assert send_task.artefact(uid)["slots"]["text"]["source"] == "his"
    assert _asks(world) == [] and len(_rows()) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_escalation_without_the_words_keeps_the_worker_on_the_rows_row(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["bare"])
    esc, acted = {"v": "Send Andrew a message; work out the wording from the conversation."}, {"v": None}
    uid, how = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=esc["v"], escalate_req=esc,
                              worker_acted=acted, emit=world["emit"], on_missing="worker")
    assert uid and how == "worker" and world["sent"] == [] and _asks(world) == []
    row = ts.task_get(uid)
    assert row["playbook"] == "message" and send_task.artefact(uid)["slots"]["recipient"]["source"] == "his"
    assert stw.brief_block(uid), "the worker's brief carries the row's slots"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_promise_with_no_call_is_the_task_and_a_prose_question_is_the_rows(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["said"])
    esc, acted = {"v": None}, {"v": None}
    uid, how = stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req=esc,
                              worker_acted=acted, emit=world["emit"])
    assert how == "run" and len(world["sent"]) == 1 and world["sent"][0]["payload"]["text"] == c["text"]
    # the prose question: the row waits on IT, said once
    _say(c["bare"])
    esc = {"v": None}
    uid2, how2 = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=c["prose_q"], escalate_req=esc,
                                worker_acted=acted, emit=world["emit"], asked_line=c["prose_q"])
    assert how2 == "asked" and uid2 != uid
    asks = _asks(world)
    assert len(asks) == 1 and asks[0]["text"] == c["prose_q"] and asks[0]["task_id"] == uid2
    assert ts.task_get(uid2)["state"] == "waiting" and len(world["sent"]) == 1


def test_a_turn_that_answered_a_task_or_already_retained_one_commissions_nothing(world):
    c = CASES["es"]
    _say(c["said"])
    assert stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req={"v": None},
                          worker_acted={"v": "answer"}, emit=world["emit"]) == ("", "")
    assert stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"],
                          escalate_req={"v": None, "send_task": True}, worker_acted={"v": None},
                          emit=world["emit"]) == ("", "")
    assert world["sent"] == [] and _rows() == []


def test_disarmed_a_blind_identification_commissions_nothing(world, monkeypatch):
    c = CASES["en"]
    _say(c["said"])
    monkeypatch.setattr(stw, "identified", lambda brief: ("", ""))
    assert stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req={"v": None},
                          worker_acted={"v": None}, emit=world["emit"]) == ("", "")
    assert world["sent"] == [] and _rows() == []


def _calls(path: str, attr: str) -> list:
    src = (ROOT / path).read_text(encoding="utf-8")
    return [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == attr]


def test_the_close_and_the_escalation_read_the_verdict_and_the_bound_answer_reads_the_quote():
    calls = _calls("nucleo/turn/pipeline_errands.py", "by_verdict")
    assert len(calls) == 2, "the escalation and the close each ask `by_verdict` once"
    kws = {kw.arg: ast.unparse(kw.value) for c in calls for kw in c.keywords}
    assert kws.get("on_missing") == "'worker'" and "ends_asking" in kws.get("asked_line", "")
    assert _calls("nucleo/flash/post_stream_settle.py", "quoted_his"), "the bound answer is the quoted text"
