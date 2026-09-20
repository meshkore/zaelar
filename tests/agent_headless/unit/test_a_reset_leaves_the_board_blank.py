"""After a reset, the task board stays blank — even against the tombstone race.

Seen live by the operator (2026-08-31): he pressed Reset, and «Histórico» showed exactly one entry — the very
search his reset had cancelled, «⊘ … generic · ahora». The design was already right (V2-084: `reset_all`
wipes the finished work, processes start blank), and the wipe DID run. What survived it was the race:
`reset_all` kills the live workers FIRST and wipes after, but a kill is a signal — the dying worker's finish
path runs asynchronously and, milliseconds after the wipe, wrote the killed task's own tombstone onto the
fresh slate.

Reordering `reset_all` cannot fix that: the worker's death is not ours to sequence, and any window reopens it.

WHAT CHANGED WITH V2-728, and it is the point of this file. The ledger fenced the race with a STORED
TIMESTAMP — `clear()` wrote «wiped at T» into `sys_kv` and every writer compared against it — which is a rule
each writer has to remember, and a rule each writer has to remember is not a rule. The board is a table now,
so the question is asked directly: **does this task still exist?** A row the reset deleted is not a row to be
closed. `nucleo/tasks.closed()` returns on a missing row, and so nothing downstream of it runs either — no
artifact snapshot, no memory pill about a commission the operator just erased.

The tests below are the same four situations, asserted against the mechanism that replaced the fence.
"""
import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import tasks


class Rec:
    """The shape `nucleo/tasks` reads off a live worker session (duck-typed, as the seam is)."""

    def __init__(self, uid, *, status="done", goal="", kind="web", ok=True):
        self.uid, self.status, self.goal, self.kind, self.ok = uid, status, goal, kind, ok
        self.title, self.sheet, self.trace_id, self.waiting_on = goal, "", "", ""
        self.started, self.result_summary = time.time(), ""


@pytest.fixture(autouse=True)
def _own_db(tmp_path, monkeypatch):
    """The board lives in the DB — the OPERATOR's, unless pointed elsewhere (the 7.28 rule)."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _put(uid, state, *, mode="now", goal="", finished=None):
    ts.task_put({"id": uid, "title": goal, "goal": goal, "kind": "web", "mode": mode, "state": state,
                 "visible": True, "origin": "voz", "created_at": int(time.time()) - 300,
                 "started_at": int(time.time()) - 300,
                 "finished_at": int(finished or (time.time() if state in ts.DONE_STATES else 0))})


def test_the_killed_tasks_tombstone_does_not_survive_the_reset():
    """The exact live sequence: task runs → reset kills it and wipes → the tombstone lands AFTER the wipe."""
    _put("old", "done", goal="una tarea vieja cualquiera")
    _put("victim", "running", goal="Busca especialistas en aparato digestivo (digestólogos) en Soria")
    assert len(tasks.board("done")) == 1 and len(tasks.board("live")) == 1

    tasks.board_cleared()                                     # the reset
    rec = Rec("victim", status="cancelled", ok=False,         # the dying worker, milliseconds later
              goal="Busca especialistas en aparato digestivo (digestólogos) en Soria")
    tasks.closed(rec)

    assert tasks.board("done") == [], (
        "the task the reset killed wrote its own tombstone onto the fresh slate — «empezamos de cero» must "
        "hold against the record arriving late, because the worker's death is not ours to sequence")
    assert tasks.board("live") == []


def test_nothing_hangs_off_a_task_the_reset_erased(monkeypatch):
    """The fence is not cosmetic. `closed()` is also what snapshots the RESULT and writes the memory pill, so
    a fence that only skipped the state change would leave an orphan report and a MEMORY of a commission the
    operator had just wiped — worse than the tombstone, because neither shows on the board to be noticed."""
    from memory import api as memory
    written: list = []
    monkeypatch.setattr(memory, "write", lambda text, **kw: written.append(text))

    _put("victim", "running", goal="busca piso en Gràcia")
    ts.artifact_put("victim", "result", {"items": [{"title": "uno"}]})
    tasks.board_cleared()

    rec = Rec("victim", goal="busca piso en Gràcia")
    rec.sheet = "victim"
    tasks.closed(rec)

    assert ts.artifacts_of("victim") == {}, "the artifacts went with the row and must not come back"
    assert written == [], f"a wiped commission was written into memory anyway: {written}"


def test_and_a_task_that_DID_survive_still_gets_its_pill():
    """The counterweight to the assert above — without it, a `closed()` that wrote no pill at all would pass
    the fence test and silently remove the recall half of V2-728."""
    from memory import api as memory
    written: list = []
    real, memory.write = memory.write, lambda text, **kw: written.append(text)
    try:
        _put("kept", "running", goal="busca piso en Gràcia")
        tasks.closed(Rec("kept", goal="busca piso en Gràcia"))
    finally:
        memory.write = real
    assert written and written[0].startswith("[task:kept]"), written


def test_a_task_born_after_the_reset_is_recorded_normally():
    """The counterweight: the wipe erases an ERA, not the future. The next session's board works as always."""
    tasks.board_cleared()
    _put("fresh", "done", goal="la búsqueda nueva de después del reset")
    rows = tasks.board("done")
    assert len(rows) == 1 and rows[0]["goal"].startswith("la búsqueda nueva")


def test_a_standing_commitment_is_NOT_wiped_by_a_reset():
    """«Empezamos de cero» is about work in progress. A cron the operator asked for is not work in progress:
    wiping «avísame cada lunes» would be a reset deleting an instruction, which nobody asked it to do — and
    it would not even stick, since the scheduler's own rows would mirror it straight back."""
    _put("cron:7", "pending", mode="recurring", goal="mírame el precio cada lunes")
    _put("later", "pending", mode="scheduled", goal="la semana que viene, escribe a Ana")
    tasks.board_cleared()
    assert len(tasks.board("recurring")) == 1
    assert len(tasks.board("scheduled")) == 1


def test_a_restarts_interrupted_marks_survive_their_own_reset_era():
    """`rehydrate` records what a restart cut in half. After a reset those tasks belong to the wiped era just
    the same: the row is gone, so `interrupted` has nothing to patch — and it must not resurrect it either."""
    _put("inflight", "running", goal="lo que estaba en vuelo antes del reset")
    tasks.board_cleared()
    tasks.interrupted({"id": "inflight", "kind": "web", "goal": "lo que estaba en vuelo antes del reset"})
    # `interrupted` composes its own durable id from the raw worker id, so it cannot collide with the wiped
    # row; what matters is that the WIPED one did not come back to life.
    assert not any(r["id"] == "inflight" for r in tasks.board("done"))
