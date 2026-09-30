"""V2-776 M3 · the circuit's verdict closes every row, and a «done» over an unmet end state is corrected out loud
(nodes 2.198, 3.113).
"""
import asyncio
import contextvars

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit, request_row as rq, spec
from nucleo import tasks as T
from nucleo.batch import runner

GONE = {"widget": "agenda", "collection": "meetings", "where": {"title~": "Nope"}}


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db(); spec.reset()
    yield
    spec.reset(); memdb.reset_db()


def test_a_worker_row_carries_the_circuits_verdict():
    from nucleo.workers.session import SessionRecord
    rec = SessionRecord(task_id="t1", goal="find monitors")
    rec.uid = "u-t1"
    ts.task_put({"id": "u-t1", "goal": "find monitors", "kind": "web", "state": "running"})
    rec.status, rec.ok, rec.verdict, rec.result_summary = "done", True, "unverifiable", "three monitors"
    T.closed(rec)
    assert ts.task_get("u-t1")["verdict"] == "unverifiable"


def test_an_unmet_op_is_corrected_out_loud_as_soon_as_the_verdict_exists(monkeypatch):
    from nucleo.workers import spoken_delivery
    from voice import brain_notes, proactive
    notes, said = [], []
    monkeypatch.setattr(brain_notes, "push", lambda *a, **k: notes.append(a))

    async def line(goal, summary, **k):
        return "Sorry — that video didn't start."

    async def notify(title, text, **k):
        said.append(text)
        return True
    monkeypatch.setattr(spoken_delivery, "line", line)
    monkeypatch.setattr(proactive, "notify", notify)

    async def run():
        rq.begin("play the second one")
        uid = rq.opened("youtube", "play_result")
        e = spec.open(GONE, text="x", source="flash", widget="youtube", action="play_result", now=1000.0)
        e["row"], e["turn"] = uid, rq.current()
        circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
        await asyncio.sleep(0.05)
        return uid
    uid = asyncio.run(run())
    assert said == ["Sorry — that video didn't start."] and notes == [], "said now, not left for the next turn"
    assert ts.task_get(uid)["verdict"] == "unmet"


def test_with_no_loop_to_speak_on_the_correction_goes_to_the_next_turn(monkeypatch):
    from voice import brain_notes
    notes = []
    monkeypatch.setattr(brain_notes, "push", lambda *a, **k: notes.append(a))

    def run():
        rq.begin("pause it")
        e = spec.open(GONE, text="x", source="flash", widget="youtube", action="pause", now=1000.0)
        e["turn"] = rq.current()
        circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    contextvars.copy_context().run(run)
    assert len(notes) == 1


def test_a_list_step_whose_op_was_unmet_is_a_failed_step(monkeypatch):
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")

    async def turn(text, **kw):
        rq.begin(text)
        uid = rq.opened("agenda", "add_meeting")
        rq.settle(uid, "unmet", "the calendar refused the date")
        return {"ok": True, "reply": ["Done."], "executed": "widget_data"}

    async def ingest(text):
        return None

    async def notify(title, text):
        pass
    uid = runner.create("msg", [{"id": "1", "title": "event", "say": "Create the event.", "kind": "agenda"}],
                        origin="chat")
    s = asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=notify, worker_wait_s=0.1))
    [step] = s["failed"]
    assert step["verdict"] == "unmet" and "refused the date" in step["outcome"]
