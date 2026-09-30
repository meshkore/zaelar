"""V2-776 L1 · An errand's END STATE is born where the commission is recorded, persisted on its row, and told to
the worker (node 3.104).

Pass 60 (2026-09-29): 4 Brain Workers, 0 `done_when` declared — the spec was the worker's optional afterthought,
its prompt exempted «a search, a report», and the escalation travelled without one. Now `tasks.opened` opens and
persists the spec the escalation brought; asks for it ONCE when it did not (a model call the size of the errand
namer); marks the errand UNVERIFIABLE when nothing readable comes back; and the worker hears it as its first
injected turn either way.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from nucleo import spec
from nucleo import tasks as T
from nucleo.workers.session import SessionRecord


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db()
    memdb.get_db()
    spec.reset()
    yield
    spec.reset()
    memdb.reset_db()


class _Session:
    def __init__(self):
        self.heard: list[str] = []

    async def inject(self, line: str):
        self.heard.append(line)


WALL = {"all": [{"desktop": "wallpaper", "expect": "changed", "baseline": {}}]}


def test_a_spec_the_escalation_brought_is_opened_persisted_and_told_to_the_worker(fresh):
    rec = SessionRecord(task_id="1", goal="find the wallpaper cosmic eye and set it as my background", done_when=dict(WALL))
    rec.session = _Session()

    async def go():
        T.opened(rec, {"src": "voice"})
        await asyncio.sleep(0.05)
    asyncio.run(go())
    live = [e for e in spec.open_specs() if e["task_id"] == rec.uid]
    assert live and live[0]["target"] == "desktop:wallpaper"
    spec.reset()                                          # a restart empties RAM…
    row = spec.of_task(rec.uid)
    assert row and row["done_when"] == WALL and row["status"] == "open", "…and the row still says what «done» means"
    assert rec.session.heard and rec.session.heard[0].startswith("OBJETIVO MEDIBLE"), rec.session.heard


def test_an_errand_without_a_spec_is_asked_for_it_once(fresh, monkeypatch):
    asked: list[str] = []

    async def _infer(goal, **_k):
        asked.append(goal)
        return dict(WALL)
    monkeypatch.setattr(spec, "infer", _infer)
    rec = SessionRecord(task_id="2", goal="find the wallpaper cosmic eye and set it as my background")
    rec.session = _Session()

    async def go():
        T.opened(rec, {"src": "voice"})
        await asyncio.sleep(0.1)
    asyncio.run(go())
    assert asked == [rec.goal]
    assert rec.done_when == WALL
    assert spec.of_task(rec.uid)["source"].endswith("+inferred")
    assert rec.session.heard and "OBJETIVO MEDIBLE" in rec.session.heard[0]


def test_an_errand_nothing_can_attest_is_unverifiable_never_done(fresh, monkeypatch):
    async def _none(goal, **_k):
        return None
    monkeypatch.setattr(spec, "infer", _none)
    rec = SessionRecord(task_id="3", goal="write me a one page summary of the bitcoin whitepaper")
    rec.session = _Session()

    async def go():
        T.opened(rec, {"src": "voice"})
        await asyncio.sleep(0.1)
    asyncio.run(go())
    assert getattr(rec, "spec_unverifiable", False) is True
    row = spec.of_task(rec.uid)
    assert row and row["unverifiable"] is True and row["status"] == "unverifiable"
    assert not rec.session.heard, "nothing to tell the worker: an unreadable condition affirms nothing"


def test_a_relay_does_not_ask_again(fresh, monkeypatch):
    calls: list[str] = []

    async def _infer(goal, **_k):
        calls.append(goal)
        return None
    monkeypatch.setattr(spec, "infer", _infer)
    rec = SessionRecord(task_id="4", goal="x", relay_gen=1)

    async def go():
        T.opened(rec, {"src": "goal_unmet", "relay_gen": 1})
        await asyncio.sleep(0.05)
    asyncio.run(go())
    assert calls == []


def test_the_models_answer_is_parsed_in_the_grammar_or_dropped():
    assert spec.parse("-") is None
    assert spec.parse("Sure! {\"all\": [{\"widget\": \"agenda\", \"collection\": \"meetings\", \"where\": {\"title~\": \"Rowan\"}}]}")["all"][0]["widget"] == "agenda"
    assert spec.parse("{\"steps\": [\"open the browser\"]}") is None, "a script of behaviour is not a spec"
