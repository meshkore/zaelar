"""V2-776 M1 · every request that ACTS is a row of `tasks`, the inline ones included (nodes 2.194, 2.195).

Audit 2026-09-30: an inline turn — an agenda add, a picture search, a mail search — left nothing durable, so
after a restart or an hour of silence the agent could not say what it had just done (manual session 7850de3f).
Now the first op of a turn opens ONE row (`kind=inline`, his words as `goal`), later ops of the same turn reuse
it, and the row ends with the circuit's verdict.
"""
import asyncio
import contextvars

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit, request_row as rq, spec
from nucleo import tasks as T


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db(); spec.reset()
    yield
    spec.reset(); memdb.reset_db()


def _in_turn(fn):
    return contextvars.copy_context().run(fn)


def _inline_rows():
    return [r for r in ts.tasks_where(states=ts.LIVE_STATES + ts.DONE_STATES, limit=50) if r["kind"] == "inline"]


def test_the_first_op_opens_the_row_and_the_next_ops_reuse_it():
    def turn():
        rq.begin("book the dentist tomorrow at nine and tell Ethan")
        a = rq.opened("agenda", "add_meeting")
        b = rq.opened("mensajeria", "send_to")
        return a, b
    a, b = _in_turn(turn)
    assert a and a == b
    rows = _inline_rows()
    assert len(rows) == 1 and rows[0]["goal"] == "book the dentist tomorrow at nine and tell Ethan"
    assert rows[0]["state"] == "running" and rows[0]["surface"]


def test_a_turn_with_no_words_opens_nothing():
    assert _in_turn(lambda: (rq.begin(""), rq.opened("agenda", "add_meeting"))[1]) == ""
    assert _inline_rows() == []


def test_a_failed_op_is_not_undone_by_a_later_good_one():
    uid = _in_turn(lambda: (rq.begin("x"), rq.opened("agenda", "add_meeting"))[1])
    rq.settle(uid, "unmet", "no such meeting")
    rq.settle(uid, "met")
    row = ts.task_get(uid)
    assert row["state"] == "failed" and row["verdict"] == "unmet" and row["outcome"] == "no such meeting"


def test_the_door_settles_the_row_from_the_spec(monkeypatch):
    import widgets
    from nucleo.flash import data_ops

    async def dispatch(tag, body):
        return {"ok": True}
    monkeypatch.setattr(widgets, "dispatch_tag", dispatch)
    monkeypatch.setattr(spec, "open_for_action", lambda *a, **k: {"id": "s1", "done_when": {"x": 1}, "status": "open"})
    monkeypatch.setattr(spec, "attest", lambda e, **k: True)

    async def run():
        rq.begin("move the call to four")
        await data_ops.dispatch_and_report("agenda", "move_meeting", {"title": "call"}, text="move the call to four")
    asyncio.run(run())
    row = _inline_rows()[0]
    assert row["state"] == "done" and row["verdict"] == "met"


def test_a_refused_op_ends_its_row_unmet(monkeypatch):
    import widgets
    from nucleo.flash import data_ops

    async def dispatch(tag, body):
        return {"ok": False, "message": "No hay resultados de búsqueda ahora mismo."}
    monkeypatch.setattr(widgets, "dispatch_tag", dispatch)

    async def nothing(*a, **k):
        return None
    monkeypatch.setattr(data_ops, "report_failure", nothing)
    monkeypatch.setattr(data_ops, "corrected_retry", nothing)

    async def run():
        rq.begin("play the second one")
        await data_ops.dispatch_and_report("youtube", "play_result", {"item": 2}, text="play the second one")
    asyncio.run(run())
    row = _inline_rows()[0]
    assert row["state"] == "failed" and row["verdict"] == "unmet" and "resultados" in row["outcome"]


def test_an_unmet_spec_ends_its_row_when_the_circuit_settles_it(monkeypatch):
    from voice import brain_notes
    monkeypatch.setattr(brain_notes, "push", lambda *a, **k: None)
    uid = _in_turn(lambda: (rq.begin("delete the Cryptonite call"), rq.opened("agenda", "delete_meeting"))[1])
    e = spec.open({"widget": "agenda", "collection": "meetings", "where": {"title~": "Nope"}},
                  text="x", source="flash", widget="agenda", action="delete_meeting", now=1000.0)
    e["row"] = uid
    circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
    assert ts.task_get(uid)["verdict"] == "unmet"


def test_a_list_step_parents_the_rows_of_its_ops():
    def turn():
        tok = rq.under("lista:1#02")
        try:
            rq.begin("Create a calendar event tomorrow at nine")
            return rq.opened("agenda", "add_meeting")
        finally:
            rq._PARENT.reset(tok)
    uid = _in_turn(turn)
    assert ts.task_get(uid)["parent_id"] == "lista:1#02"


def test_the_board_shows_inline_rows_only_behind_the_switch():
    uid = _in_turn(lambda: (rq.begin("x"), rq.opened("agenda", "add_meeting"))[1])
    rq.settle(uid, "met")
    assert not any(r["id"] == uid for r in T.board("done"))
    assert any(r["id"] == uid for r in T.board("done", show_all=True))


def test_an_inline_row_is_pruned_after_two_days_and_a_worker_row_is_not():
    import time
    uid = _in_turn(lambda: (rq.begin("x"), rq.opened("agenda", "add_meeting"))[1])
    rq.settle(uid, "met")
    ts.task_put({"id": "w1", "goal": "find monitors", "kind": "web", "state": "done",
                 "finished_at": int(time.time())})
    assert ts.tasks_prune(30, now=time.time() + 3 * 86400) == 1
    assert ts.task_get(uid) is None and ts.task_get("w1") is not None


def test_the_picture_search_is_a_row_like_any_op(monkeypatch):
    from nucleo import browser_search
    from nucleo.flash import image_turn
    from widgets import server_api

    async def images(q, n):
        return {"items": [{"url": "https://x/f40.jpg", "title": "Ferrari F40"}], "source": "google"}

    async def brain_action(wid, action, payload):
        return {"ok": True, "n": 1}
    monkeypatch.setattr(browser_search, "images", images)
    monkeypatch.setattr(server_api, "brain_action", brain_action)
    monkeypatch.setattr(image_turn, "_evidence", lambda parte: None)

    async def run():
        rq.begin("show me a red ferrari f40")
        return await image_turn.execute("red ferrari f40")
    parte = asyncio.run(run())
    assert parte["ok"]
    row = _inline_rows()[0]
    assert row["goal"] == "show me a red ferrari f40" and row["verdict"] == "met" and "Ferrari" in row["outcome"]
