"""A rule inside a list is a RULE, not a turn (V2-776 K2, 2026-09-29).

Demo pass 57, the INIT: Jev split the message into 26 rows and named five of them `rule` («From now on…»,
«Confirm my orders with a short line…»). The runner handed each to a model turn, the model answered «Done.»,
`set_style_directive` was never called and nothing was stored: no flag, no `state.rules`. The classification
was right and its consequence was missing. Now a `rule` row goes to the directive handler's own path — the
style and consent flags, then the sentences into memory with their scope — with no model call for that row.
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from nucleo import consent, style_policy as sp
from nucleo.batch import runner


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    sp._reset_for_tests(); consent._reset_for_tests()
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    yield
    memdb.reset_db(); mememb.reset(); sp._reset_for_tests(); consent._reset_for_tests()


STEPS = [
    {"id": "1", "title": "name", "say": "Your name is Johnny.", "kind": "identity"},
    {"id": "2", "title": "rules", "kind": "rule",
     "say": "From now on, when I ask you to organize something, do as much of the task as possible. "
             "Confirm my orders with a short line when you do something. Pregúntame siempre antes de tocar nada."},
    {"id": "3", "title": "memory", "say": "Remember: I live in Los Angeles.", "kind": "memory"},
]


def _run(calls):
    async def turn(text, **kw):
        calls.append(text)
        return {"ok": True, "reply": ["Done."]}

    async def ingest(text):
        await asyncio.sleep(0)

    async def notify(title, text):
        pass
    uid = runner.create("msg", STEPS, origin="chat")
    return uid, asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=notify, worker_wait_s=0.1))


def test_a_rule_row_is_stored_with_its_flags_and_never_reaches_the_model():
    calls = []
    uid, _ = _run(calls)
    assert calls == ["Your name is Johnny.", "Remember: I live in Los Angeles."], "the rule row took no model turn"
    rules = memapi.state().get("rules") or []
    assert any("organize something" in r for r in rules) and any("Confirm my orders" in r for r in rules)
    assert sp.confirm_short_actions() is True and consent.ask_at() == "sensitive", "the flags moved on the way"
    s = runner.summary(uid)
    assert len(s["done"]) == 3 and not s.get("failed")


def test_a_rule_row_that_names_a_card_gets_that_scope():
    calls = []
    steps = [{"id": "1", "title": "r", "kind": "rule", "say": "From now on, in the calendar, meetings are always 30 minutes."}]
    uid = runner.create("msg", steps, origin="chat")

    async def turn(text, **kw):
        raise AssertionError("no model turn for a rule row")

    async def ingest(text):
        await asyncio.sleep(0)

    async def notify(title, text):
        pass
    asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=notify, worker_wait_s=0.1))
    assert memapi.rules_for("widget:agenda") == ["From now on, in the calendar, meetings are always 30 minutes"]
