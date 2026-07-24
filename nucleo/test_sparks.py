"""Tests de nucleo/sparks.py (V2-005 · T73) — doble gate de las chispas (frecuencia + utilidad)."""
import pytest

from memory import db as memdb
from memory import journal as memjournal
from nucleo import sparks


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def test_gate_respects_daily_budget():
    now = [10_000_000.0]
    gate = sparks.SparkGate(daily_max=2, min_gap_s=0, prob=1.0, clock=lambda: now[0], rng=lambda: 0.0)
    assert gate.allow() and (gate.record() or True)
    assert gate.allow() and (gate.record() or True)
    assert gate.allow() is False           # presupuesto agotado
    assert gate.budget_left() == 0


def test_gate_resets_next_day():
    now = [10_000_000.0]
    gate = sparks.SparkGate(daily_max=1, min_gap_s=0, prob=1.0, clock=lambda: now[0], rng=lambda: 0.0)
    gate.record()
    assert gate.allow() is False
    now[0] += 86400                        # día siguiente
    assert gate.allow() is True


def test_gate_min_gap():
    now = [10_000_000.0]
    gate = sparks.SparkGate(daily_max=10, min_gap_s=1800, prob=1.0, clock=lambda: now[0], rng=lambda: 0.0)
    gate.record()
    now[0] += 600                          # < gap
    assert gate.allow() is False
    now[0] += 1300                          # > gap total
    assert gate.allow() is True


def test_gate_probability():
    gate = sparks.SparkGate(daily_max=10, min_gap_s=0, prob=0.05, clock=lambda: 0.0, rng=lambda: 0.5)
    assert gate.allow() is False           # 0.5 >= 0.05 → no dispara


def test_propose_none_when_nothing_pending(fresh_db):
    assert sparks.propose(now=10_000_000.0) is None


def test_propose_surfaces_stale_task(fresh_db):
    jid = memjournal.add("terminar el informe")
    # forzar la tarea a "vieja"
    memdb.get_db().execute("UPDATE journal SET updated=? WHERE id=?", (1000, jid))
    text = sparks.propose(now=1000 + 7 * 3600)
    assert text and "informe" in text


def test_propose_ignores_scheduled_and_fresh(fresh_db):
    memjournal.add("cita", detail={"kind": "scheduled"})   # programada → no es material de chispa
    memjournal.add("recién creada")                        # fresca → aún no
    assert sparks.propose(now=2000) is None
