"""Tests for nucleo/tasks.py (V2-728) — the SessionRecord ↔ durable task row seam.

The two vocabularies do not match, and the differences carry meaning. These hold the translation in place.
"""
import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import tasks as T
from nucleo.workers.session import SessionRecord


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _rec(task_id="1", goal="búscame piso en Gràcia", **kw):
    return SessionRecord(task_id=task_id, goal=goal, **kw)


# ── the durable id ───────────────────────────────────────────────────────────────────────────────────────
def test_the_durable_id_is_not_the_session_counter():
    """`escalate._seq` restarts at 0 every process; a row that outlives the process cannot be keyed on it."""
    assert T.task_uid(1) != "1"
    assert T.task_uid(1).endswith("-1")


def test_two_runs_do_not_collide_on_the_same_counter_value(monkeypatch):
    first = T.task_uid(1)
    monkeypatch.setattr(T, "_boot_id", lambda: "ffffff")     # a different process
    assert T.task_uid(1) != first


# ── the state vocabulary ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("status,expected", [
    ("queued", "pending"), ("running", "running"), ("done", "done"),
    ("error", "failed"), ("cancelled", "cancelled"),
])
def test_every_worker_status_has_a_task_state(status, expected):
    assert T.state_of(_rec(status=status)) == expected


def test_a_relayed_session_is_still_running():
    """`relevada` is NOT an ending: the same commission carries on with a fresh worker, and painting it
    «done» for the seconds in between puts a task the operator is still waiting for in the finished list."""
    assert T.state_of(_rec(status="relevada")) == "running"


def test_waiting_on_the_operator_beats_running():
    """The runtime calls it `running`; the operator needs to see that it is parked on HIS answer."""
    assert T.state_of(_rec(status="running", waiting_on="user", ask="¿para cuántos?")) == "waiting"


def test_waiting_does_not_survive_a_terminal_status():
    assert T.state_of(_rec(status="done", waiting_on="user")) == "done"


# ── the admission gate ───────────────────────────────────────────────────────────────────────────────────
def test_a_spoken_commission_counts():
    assert T.is_visible(kind="web", origin="voz") is True
    assert T.is_visible(kind="generic", origin="susurro") is True


def test_the_engine_talking_to_itself_does_not():
    assert T.is_visible(kind="memory") is False
    assert T.is_visible(kind="dev") is False
    assert T.is_visible(kind="web", src="goal_unmet") is False
    assert T.is_visible(kind="web", src="context_handoff") is False


def test_the_gate_never_calls_a_model(monkeypatch):
    """Deterministic by contract: a list whose contents depend on a classifier is one nobody can predict."""
    import nucleo.jev as jev
    calls = []
    for name in ("choose_many_sync", "select_many", "ask_many"):
        if hasattr(jev, name):
            monkeypatch.setattr(jev, name, lambda *a, **k: calls.append(name))
    T.is_visible(kind="web", origin="voz")
    T.is_visible(kind="memory")
    assert calls == []


# ── open → retitle → close ───────────────────────────────────────────────────────────────────────────────
def test_opened_writes_the_row_and_stamps_the_record(fresh_db):
    rec = _rec(title="piso", surface="lista", trace_id="tr1")
    uid = T.opened(rec, {"origin": "voz"})
    assert rec.uid == uid
    row = ts.task_get(uid)
    assert row["goal"] == "búscame piso en Gràcia" and row["title"] == "piso"
    assert row["state"] == "pending" and row["visible"] is True and row["surface"] == "lista"


def test_an_internal_escalation_gets_a_row_but_not_the_list(fresh_db):
    """Worth auditing, never worth interrupting him with."""
    uid = T.opened(_rec(kind="memory", goal="consolidar"), {"src": "memory_maint"})
    assert ts.task_get(uid) is not None
    assert ts.tasks_where(states=("pending", "running")) == []


def test_the_late_name_reaches_the_row(fresh_db):
    rec = _rec(title="haz lo del otro día")
    T.opened(rec, {})
    rec.title = "hora con el dentista"                 # V2-530 composes it seconds later
    T.retitled(rec)
    assert ts.task_get(rec.uid)["title"] == "hora con el dentista"
    assert [r["id"] for r in ts.task_search("dentista")] == [rec.uid]


def test_closing_stamps_the_outcome_and_the_hour(fresh_db):
    rec = _rec()
    T.opened(rec, {})
    rec.status, rec.ok, rec.result_summary = "done", True, "5 pisos en Gràcia"
    T.closed(rec)
    row = ts.task_get(rec.uid)
    assert row["state"] == "done" and row["outcome"] == "5 pisos en Gràcia"
    assert row["finished_at"] and row["finished_at"] > 0


def test_a_failure_is_not_a_success(fresh_db):
    rec = _rec()
    T.opened(rec, {})
    rec.status, rec.ok = "error", False
    T.closed(rec)
    assert ts.task_get(rec.uid)["state"] == "failed"


def test_a_relay_does_not_close_the_task(fresh_db):
    """The baton is in the air; the commission is not over and must not leave the live list."""
    rec = _rec()
    T.opened(rec, {})
    rec.status = "relevada"
    T.closed(rec)
    row = ts.task_get(rec.uid)
    assert row["state"] == "running" and not row["finished_at"]
    assert [r["id"] for r in ts.tasks_where()] == [rec.uid]


def test_a_relay_continues_the_SAME_task(fresh_db):
    """One errand that changed provider twice is ONE thing the operator asked for, not three."""
    first = _rec(task_id="1", title="piso en Gràcia")
    T.opened(first, {"origin": "voz"})
    first.status = "relevada"
    T.closed(first)
    # …the relay: a brand-new record, a brand-new session id, carrying the commission's uid (relay.py).
    relayed = _rec(task_id="2", goal="búscame piso en Gràcia\n\n[ARNÉS] esto quedó sin cumplir…")
    uid2 = T.opened(relayed, {"src": "context_handoff", "task_uid": first.uid})
    assert uid2 == first.uid
    assert len(ts.tasks_where(states=ts.LIVE_STATES + ts.DONE_STATES, visible_only=False)) == 1
    row = ts.task_get(uid2)
    assert row["title"] == "piso en Gràcia"                    # the ORIGINAL name, not the relay's brief
    assert "[ARNÉS]" not in row["goal"]                        # nor its rewritten goal
    assert row["visible"] is True                              # …and it does not turn internal on the way


def test_the_relayed_task_closes_once_at_the_end(fresh_db):
    first = _rec(task_id="1")
    T.opened(first, {})
    first.status = "relevada"
    T.closed(first)
    relayed = _rec(task_id="2")
    T.opened(relayed, {"src": "provider_failover", "task_uid": first.uid})
    relayed.status, relayed.ok, relayed.result_summary = "done", True, "reservado"
    T.closed(relayed)
    done = ts.tasks_where(states=ts.DONE_STATES)
    assert [r["id"] for r in done] == [first.uid]
    assert done[0]["outcome"] == "reservado"


def test_a_record_with_no_uid_closes_nothing(fresh_db):
    """A session created by hand in a test never opened a task; closing it must not invent one."""
    T.closed(_rec(status="done"))
    assert ts.tasks_where(states=ts.DONE_STATES, visible_only=False) == []
