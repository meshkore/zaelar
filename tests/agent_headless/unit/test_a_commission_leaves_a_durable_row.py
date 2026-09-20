"""V2-728 — a commission the operator hands over leaves a DURABLE row, and the dispatcher is what writes it.

These drive the REAL `dispatch.run_listener` with a fake worker backend, because the module-level tests of
`nucleo/tasks.py` prove the translation and prove nothing about whether anybody calls it. That distinction has
a scar: 33 green tests once covered a mechanism that had been disconnected from `_finish`. What is fixed here
is the CALL and its ORDER — the row exists while the worker is still running, not only once it is over, which
is the whole point of a counter the operator can watch go up.
"""
from __future__ import annotations

import asyncio

import pytest

import bus
from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo import dispatch
from nucleo.workers.base import WorkerBackend, WorkerEvent, WorkerSpec
from tests.waiting import until


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture(autouse=True)
def _no_sessions_left_behind():
    """`dispatch._SESSIONS` is a MODULE GLOBAL, and these tests are the first here to leave live ones in it.

    Leaving one behind does not fail this file — it fails the NEXT one, silently and far away. Measured while
    writing these: a leftover «búscame piso» session made `dispatch`'s own
    `test_listener_consumes_escalate_requested` dedup its «busca un piso» against ours, so the escalation was
    absorbed instead of dispatched and that test sat in its polling loop for fifteen minutes before failing
    on an assertion that had nothing to do with the cause. Cleared on BOTH sides, because inheriting someone
    else's session is the same bug read from the other end.
    """
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


class _SlowBackend(WorkerBackend):
    """A worker that STAYS ALIVE until released, so the row can be inspected mid-flight."""
    name = "fake"

    def __init__(self, gate: asyncio.Event, *, ok: bool = True, summary: str = "5 pisos en Gràcia"):
        self._gate, self._ok, self._summary = gate, ok, summary
        self.seen_spec: WorkerSpec | None = None
        self._alive = False

    async def start(self, prompt: str, *, spec: WorkerSpec) -> None:
        self.seen_spec, self._alive = spec, True

    async def send(self, text: str) -> None:
        pass

    async def events(self):
        tid = self.seen_spec.task_id if self.seen_spec else ""
        yield WorkerEvent(task_id=tid, type="spawned", backend=self.name)
        await self._gate.wait()
        if self._ok:
            yield WorkerEvent(task_id=tid, type="result", backend=self.name,
                              data={"summary": self._summary, "ok": True})
        else:
            yield WorkerEvent(task_id=tid, type="error", backend=self.name,
                              data={"message": "boom", "fatal": True})
        self._alive = False
        yield WorkerEvent(task_id=tid, type="done", backend=self.name)

    async def stop(self, *, grace: float = 3.0) -> None:
        self._alive = False
        self._gate.set()

    @property
    def alive(self) -> bool:
        return self._alive

    def native_session_id(self) -> str:
        return ""


async def _commission(monkeypatch, request: str, *, ok: bool = True, release: bool = True,
                      inspect_live=None, context: dict | None = None):
    """Drive the real listener through one commission. Returns the rows seen live and after the close."""
    from nucleo.flash import escalate
    gate = asyncio.Event()
    holder: dict = {}
    monkeypatch.setattr(dispatch, "get_backend",
                        lambda spec: holder.setdefault("b", _SlowBackend(gate, ok=ok)))
    bus.reset()
    escalate.reset()
    stop = asyncio.Event()
    listener = asyncio.create_task(dispatch.run_listener(stop))
    await asyncio.sleep(0.05)
    escalate.escalate_to_slowbrain(request, context=dict(context or {}))
    # Against a CLOCK, never an iteration count (see `tests/waiting.py`): with the mechanism disarmed these
    # two waits took 114 s each and failed on an assertion about the RESULT, which says nothing about having
    # waited. Now a broken wiring costs seconds and the failure names what never happened.
    live = await until(lambda: ts.tasks_where(states=ts.LIVE_STATES, visible_only=False) or None,
                       "the dispatcher to write the durable row")
    if inspect_live:
        inspect_live()
    if release:
        gate.set()
        await until(lambda: ts.tasks_where(states=ts.DONE_STATES, visible_only=False) or None,
                    "the commission to be recorded as finished")
    stop.set()
    await asyncio.sleep(0.05)
    listener.cancel()
    return live, ts.tasks_where(states=ts.DONE_STATES, visible_only=False)


def test_the_row_exists_WHILE_the_worker_is_still_running(fresh_db, monkeypatch):
    """Not at the end. The operator watches the counter go up the moment he hands the errand over."""
    live, _ = asyncio.run(_commission(monkeypatch, "búscame piso de alquiler en Gràcia"))
    assert live, "the dispatcher did not write the durable row when it opened the session"
    assert len(live) == 1
    row = live[0]
    assert "Gràcia" in row["goal"]
    assert row["state"] in ("pending", "running")
    assert row["visible"] is True
    assert not row["finished_at"]


def test_the_same_commission_closes_the_SAME_row(fresh_db, monkeypatch):
    """One row, opened then closed — never one row live and a second one in the history."""
    live, done = asyncio.run(_commission(monkeypatch, "búscame piso de alquiler en Gràcia"))
    assert len(done) == 1
    assert done[0]["id"] == live[0]["id"]
    assert done[0]["state"] == "done"
    assert done[0]["finished_at"] and done[0]["finished_at"] > 0
    assert ts.tasks_where(states=ts.LIVE_STATES, visible_only=False) == []


def test_the_outcome_of_a_failed_worker_is_not_a_success(fresh_db, monkeypatch):
    _, done = asyncio.run(_commission(monkeypatch, "búscame piso en Gràcia", ok=False))
    assert len(done) == 1 and done[0]["state"] == "failed"


def test_the_durable_id_is_not_the_session_id(fresh_db, monkeypatch):
    """A row keyed on `escalate._seq` would collide with the previous run's — the V2-259 defect."""
    live, _ = asyncio.run(_commission(monkeypatch, "búscame piso en Gràcia", release=False))
    assert live and live[0]["id"] not in ("1", "0", "")
    assert "-" in live[0]["id"]


def test_a_finished_commission_is_findable_by_what_it_was_ABOUT(fresh_db, monkeypatch):
    """The end-to-end reason the table exists: «lo del piso que te dije» has to reach it afterwards."""
    _, done = asyncio.run(_commission(monkeypatch, "búscame piso de alquiler en el barrio de Gràcia"))
    hits = ts.task_search("lo del piso que te dije")
    assert [h["id"] for h in hits] == [done[0]["id"]]


def test_an_internal_escalation_stays_out_of_the_operators_list(fresh_db, monkeypatch):
    """`kind=memory` is the engine talking to itself; it is audited, never counted."""
    asyncio.run(_commission(monkeypatch, "consolida la memoria de esta semana",
                            context={"kind": "memory"}))
    assert ts.tasks_where(states=ts.DONE_STATES) == []                       # his list: empty
    assert len(ts.tasks_where(states=ts.DONE_STATES, visible_only=False)) == 1   # the trail: kept


def test_the_NAME_reaches_the_row_when_it_is_composed(fresh_db, monkeypatch):
    """V2-530 composes the name asynchronously, seconds after the sheet opened, and the row has to follow it.

    This is a WIRING test and it earned its place: disconnecting `tasks.retitled` from the dispatcher left the
    whole file green, because every other test here only ever checked the goal. The title is half of what
    `task_search` matches on, so a row stuck on the provisional clip is a task he cannot ask for by name.
    """
    from nucleo import errand_title as et
    monkeypatch.setattr(et, "enabled", lambda: True)

    async def _compose(goal, **kw):
        return "hora con el dentista"
    monkeypatch.setattr(et, "compose", _compose)

    async def _go():
        live, done = await _commission(monkeypatch, "oye llama y mírame lo del dentista para la semana que viene")
        # The naming is fire-and-forget (V2-530), so give it its turn — bounded by the clock like the rest.
        return await until(lambda: (lambda r: r if r and r["title"] == "hora con el dentista" else None)(
                               ts.task_get(live[0]["id"])),
                           "the composed name to reach the durable row", timeout_s=5)

    row = asyncio.run(_go())
    assert row["title"] == "hora con el dentista", "the composed name never reached the durable row"
    assert [h["id"] for h in ts.task_search("dentista")] == [row["id"]]
