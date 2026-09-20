"""Tests for memory/tasks_store.py (V2-728) — the durable record of a user task.

What these hold in place is the reason the table exists: a commission the operator handed over has to be
findable AFTER the process that ran it is gone, by what it was ABOUT, with its result still attached.
"""
import pytest

from memory import db as memdb
from memory import tasks_store as ts


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _task(tid, goal, **kw):
    row = {"id": tid, "goal": goal, "title": kw.pop("title", ""), "created_at": kw.pop("created_at", 1000)}
    row.update(kw)
    return row


def test_put_and_get_roundtrip(fresh_db):
    ts.task_put(_task("t1", "búscame piso en Gràcia", title="piso en Gràcia", surface="lista"))
    row = ts.task_get("t1")
    assert row["goal"] == "búscame piso en Gràcia"
    assert row["title"] == "piso en Gràcia"
    assert row["state"] == "pending" and row["mode"] == "now" and row["visible"] is True
    assert row["surface"] == "lista"


def test_put_is_an_upsert_not_a_second_row(fresh_db):
    """The dispatcher creates and the worker closes, and neither has to know which one it is."""
    ts.task_put(_task("t1", "reserva mesa"))
    ts.task_put(_task("t1", "reserva mesa", state="done", outcome="mesa para 4 el sábado", finished_at=2000))
    assert len(ts.tasks_where(states=ts.DONE_STATES)) == 1
    assert ts.task_get("t1")["outcome"] == "mesa para 4 el sábado"


def test_patch_touches_only_the_named_columns(fresh_db):
    ts.task_put(_task("t1", "reserva mesa", title="mesa para 4"))
    ts.task_patch("t1", state="running", started_at=1500)
    row = ts.task_get("t1")
    assert row["state"] == "running" and row["started_at"] == 1500
    assert row["title"] == "mesa para 4"          # untouched


def test_patch_ignores_an_unknown_column(fresh_db):
    """A field name is never interpolated into the SQL — an unknown one is dropped, not executed."""
    ts.task_put(_task("t1", "x"))
    ts.task_patch("t1", state="running", **{"goal=1; DROP TABLE tasks--": "boom"})
    assert ts.task_get("t1")["state"] == "running"


def test_live_and_done_are_different_lists(fresh_db):
    ts.task_put(_task("t1", "en curso", state="running"))
    ts.task_put(_task("t2", "acabada", state="done", finished_at=2000))
    ts.task_put(_task("t3", "cancelada", state="cancelled", finished_at=2100))
    assert [r["id"] for r in ts.tasks_where()] == ["t1"]
    assert {r["id"] for r in ts.tasks_where(states=ts.DONE_STATES)} == {"t2", "t3"}


def test_the_invisible_ones_are_out_unless_asked_for(fresh_db):
    """The admission gate: the list is the OPERATOR's commissions; `⚙ todo` is what reveals the rest."""
    ts.task_put(_task("t1", "búscame piso", state="running"))
    ts.task_put(_task("t2", "consolidando memoria", state="running", visible=False, kind="memory"))
    assert [r["id"] for r in ts.tasks_where()] == ["t1"]
    assert {r["id"] for r in ts.tasks_where(visible_only=False)} == {"t1", "t2"}


def test_due_reads_only_what_is_overdue_and_timed(fresh_db):
    ts.task_put(_task("t1", "aviso", mode="scheduled", due_at=900))
    ts.task_put(_task("t2", "aviso futuro", mode="scheduled", due_at=5000))
    ts.task_put(_task("t3", "semanal", mode="recurring", due_at=800))
    ts.task_put(_task("t4", "ahora", mode="now"))
    ts.task_put(_task("t5", "ya disparada", mode="scheduled", due_at=100, state="done"))
    assert [r["id"] for r in ts.tasks_due(now=1000)] == ["t3", "t1"]     # oldest due first


def test_search_finds_by_what_the_task_was_ABOUT(fresh_db):
    ts.task_put(_task("t1", "búscame piso de alquiler en Gracia", title="piso en Gràcia", created_at=1000))
    ts.task_put(_task("t2", "resérvame mesa en un japonés", title="mesa japonés", created_at=2000))
    hits = ts.task_search("lo del piso que te dije")
    assert [r["id"] for r in hits] == ["t1"]


def test_search_ignores_accents_in_either_direction(fresh_db):
    """He says «Gracia», the title says «Gràcia» — and the other way round. Both have to land."""
    ts.task_put(_task("t1", "piso en Gràcia", title="Gràcia"))
    assert [r["id"] for r in ts.task_search("gracia")] == ["t1"]
    ts.task_put(_task("t2", "cena en Alcala", title="Alcala", created_at=2000))
    assert [r["id"] for r in ts.task_search("Alcalá")] == ["t2"]


def test_search_is_a_paraphrase_not_a_quotation(fresh_db):
    """Requiring every word finds nothing far more often than it should; ranking is what narrows it."""
    ts.task_put(_task("t1", "búscame un piso de alquiler en el barrio de Gracia", title="piso Gracia"))
    assert [r["id"] for r in ts.task_search("el alquiler del piso")] == ["t1"]


def test_search_never_offers_back_an_internal_task(fresh_db):
    ts.task_put(_task("t1", "consolidando la memoria del piso", visible=False, kind="memory"))
    assert ts.task_search("piso") == []


def test_search_returns_the_newest_first_and_caps_at_the_limit(fresh_db):
    for n in range(8):
        ts.task_put(_task(f"t{n}", f"búscame piso número {n}", created_at=1000 + n))
    hits = ts.task_search("piso", limit=5)
    assert len(hits) == 5
    assert [r["id"] for r in hits] == ["t7", "t6", "t5", "t4", "t3"]


def test_retitling_a_task_reindexes_it(fresh_db):
    """The name arrives late (V2-530 composes it asynchronously); the index has to follow it."""
    ts.task_put(_task("t1", "haz lo del otro día", title="sin nombre"))
    assert ts.task_search("dentista") == []
    ts.task_patch("t1", title="hora con el dentista")
    assert [r["id"] for r in ts.task_search("dentista")] == ["t1"]


def test_the_result_outlives_the_sheet(fresh_db):
    """The point of `task_artifacts`: the widget sheet is a view, the payload is the task's."""
    ts.task_put(_task("t1", "búscame piso en Gràcia", state="done", finished_at=2000))
    ts.artifact_put("t1", "result", {"items": [{"n": i} for i in range(5)]})
    ts.artifact_put("t1", "considered", {"items": [{"n": i} for i in range(50)]})
    ts.artifact_put("t1", "criteria", {"rooms": 2, "max": 1200})
    got = ts.artifacts_of("t1")
    assert len(got["result"]["items"]) == 5
    assert len(got["considered"]["items"]) == 50
    assert got["criteria"]["max"] == 1200


def test_writing_one_artifact_slot_leaves_the_others_alone(fresh_db):
    ts.task_put(_task("t1", "x"))
    ts.artifact_put("t1", "result", {"a": 1})
    ts.artifact_put("t1", "considered", {"b": 2})
    ts.artifact_put("t1", "result", {"a": 99})
    assert ts.artifact_get("t1", "result") == {"a": 99}
    assert ts.artifact_get("t1", "considered") == {"b": 2}


def test_a_task_survives_the_process_that_ran_it(fresh_db, tmp_path, monkeypatch):
    """The whole reason this is a table: `dispatch._SESSIONS` is a RAM dict, and a restart empties it."""
    ts.task_put(_task("t1", "búscame piso en Gràcia", title="piso", state="done", finished_at=2000))
    ts.artifact_put("t1", "result", {"items": [1, 2, 3]})
    memdb.reset_db()                                   # the process dies
    memdb.get_db()                                     # …and a new one opens the same file
    assert ts.task_get("t1")["title"] == "piso"
    assert ts.artifact_get("t1", "result") == {"items": [1, 2, 3]}
    assert [r["id"] for r in ts.task_search("piso")] == ["t1"]


def test_forget_takes_the_artifacts_and_the_index_with_it(fresh_db):
    ts.task_put(_task("t1", "búscame piso"))
    ts.artifact_put("t1", "result", {"a": 1})
    ts.task_forget("t1")
    assert ts.task_get("t1") is None
    assert ts.artifacts_of("t1") == {}
    assert ts.task_search("piso") == []
