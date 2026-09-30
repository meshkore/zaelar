"""A list step that asked him something is run once more at the end, before the list reports (node 2.193).

Manual session 7850de3f (2026-09-30): the INIT's step 1 («Your name is Johnny…») asked «what's your name?» and
step 2 of the same list said «My name is Richard». The list closed on «25 of 26 done. I need you to clarify: …
what is it?», which read as unfinished, and an hour later the agent was still «working on it». By the end of
the list, the later steps have answered it: the re-run runs in a fresh session and asks only what is missing.
"""
import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.batch import runner

STEPS = [
    {"id": "1", "title": "name", "say": "Your name is Johnny.", "kind": "identity"},
    {"id": "2", "title": "me", "say": "Remember: my name is Richard.", "kind": "memory"},
]


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")

    async def _asks(task, reply):
        return reply.endswith("?")
    monkeypatch.setattr(runner, "reply_needs_him", _asks)
    yield
    memdb.reset_db(); mememb.reset()


def _run(answers):
    calls, told, ingested = [], [], []

    async def turn(text, **kw):
        calls.append((text, kw.get("session_id") or kw.get("sid") or ""))
        return {"ok": True, "reply": [answers(text, len(calls))]}

    async def ingest(text):
        ingested.append(text)

    async def notify(title, text):
        told.append(text)
    uid = runner.create("msg", STEPS, origin="chat")
    asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=notify, worker_wait_s=0.1))
    return uid, calls, told, ingested


def test_the_question_a_later_step_answered_is_not_left_to_him():
    def answers(text, n):
        return "Got it, I'm Johnny. What's your name?" if n == 1 else "Noted, Richard."
    uid, calls, told, ingested = _run(answers)
    assert [c[0] for c in calls] == ["Your name is Johnny.", "Remember: my name is Richard.", "Your name is Johnny."]
    s = runner.summary(uid)
    assert len(s["done"]) == 2 and not s["needs_you"], s
    assert ingested.count("Your name is Johnny.") == 1, "the re-run does not store the same words twice"


def test_a_question_nothing_answered_still_reaches_him_once():
    uid, calls, told, _ = _run(lambda text, n: "Which calendar should I use?" if "Johnny" in text else "Noted.")
    assert [c[0] for c in calls].count("Your name is Johnny.") == 2, "asked again ONCE, never in a loop"
    assert len(runner.summary(uid)["needs_you"]) == 1 and told and "Which calendar" in told[0]
