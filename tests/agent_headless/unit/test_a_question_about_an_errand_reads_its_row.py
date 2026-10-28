"""«¿Has terminado X?» over an errand that FAILED names the failure, read from its row (V2-825 F1, refactor2710-02b).

The question about an errand is answered from the durable ledger, never from the conversation: the prompt's recent
state reads the row — what it was, its state, its verdict and what came of it — so the reply can say it failed and
why instead of «sigo con ello». The row is the only source here on purpose: drop it and nothing is there to read.

Disarm: drop the row (the second test) → the line is gone; empty `ledger.recent` (the third) → nothing reads around it.
"""
from __future__ import annotations

import time

import pytest

from memory import db as memdb


@pytest.fixture
def ledger_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "active_sessions", lambda *a, **k: [])
    monkeypatch.setattr(dispatch, "recently_ended_sessions", lambda *a, **k: [])
    from nucleo.circuit import ledger
    yield ledger.store()
    memdb.reset_db()


def _failed_row(st) -> None:
    now = int(time.time())
    st.task_put({"id": "u-hotel", "title": "Hotel en Sevilla para el viernes", "goal": "un hotel en Sevilla",
                 "kind": "generic", "mode": "now", "state": "failed", "verdict": "unmet", "visible": True,
                 "origin": "voz", "created_at": now - 600, "started_at": now - 600, "finished_at": now - 60,
                 "outcome": "no quedaba ninguna habitación por debajo de 120 €"})
    st.task_patch("u-hotel", verdict="unmet")       # the verdict the circuit settles (`circuit.settle`)


def test_the_failed_errand_is_named_with_its_failure(ledger_db):
    from nucleo.turn.prompt import live_history
    _failed_row(ledger_db)
    lines = " ".join(live_history.recent_lines())
    assert "Hotel en Sevilla" in lines and "FALLÓ" in lines and "no se cumplió" in lines, lines
    assert "120 €" in lines, "what came of it travels with the row"


def test_without_its_row_there_is_nothing_to_answer_from(ledger_db):
    from nucleo.turn.prompt import live_history
    assert "Hotel en Sevilla" not in " ".join(live_history.recent_lines())


def test_the_task_block_reads_the_rows_through_the_one_reader(ledger_db, monkeypatch):
    """`ledger.recent` is the one reader: with it empty, the row in the store is not named — nothing reads around it."""
    from nucleo.circuit import ledger
    from nucleo.turn.prompt import live_history
    _failed_row(ledger_db)
    monkeypatch.setattr(ledger, "recent", lambda **_kw: [])
    assert "Hotel en Sevilla" not in " ".join(live_history.recent_lines())
