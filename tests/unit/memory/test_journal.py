"""Tests de memory/journal.py (V2-005 · T71) — CRUD de la tabla journal (respaldo del scheduler)."""
import pytest

from memory import db as memdb
from memory import journal as memjournal


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_add_and_get_roundtrip(fresh_db):
    jid = memjournal.add("llamar al médico", detail={"kind": "scheduled", "next_run": 123})
    assert isinstance(jid, int) and jid > 0
    row = memjournal.get(jid)
    assert row["title"] == "llamar al médico"
    assert row["status"] == "pending"
    assert row["detail"]["kind"] == "scheduled" and row["detail"]["next_run"] == 123


def test_list_filters_by_status(fresh_db):
    a = memjournal.add("a")
    b = memjournal.add("b")
    memjournal.update(b, status="done")
    pend = memjournal.list_entries(status="pending")
    assert [e["id"] for e in pend] == [a]
    assert {e["id"] for e in memjournal.list_entries()} == {a, b}


def test_update_replaces_detail_and_bumps_updated(fresh_db):
    jid = memjournal.add("x", detail={"a": 1})
    memjournal.update(jid, detail={"b": 2}, status="in_progress")
    row = memjournal.get(jid)
    assert row["detail"] == {"b": 2}          # reemplazo entero
    assert row["status"] == "in_progress"


def test_remove(fresh_db):
    jid = memjournal.add("x")
    memjournal.remove(jid)
    assert memjournal.get(jid) is None


def test_bad_status_falls_back_to_pending(fresh_db):
    jid = memjournal.add("x", status="bogus")
    assert memjournal.get(jid)["status"] == "pending"
