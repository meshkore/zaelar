"""The NEWEST spoken rules reach the prompt and the worker's dossier (V2-778 F3-24, 2026-10-01).

The rules are stored oldest first (`memory.api.add_user_rule` appends and keeps the last 12), and both readers
took the FIRST eight: with twelve rules stored, the four the operator said most recently — the ones most likely
to correct an earlier one — never reached the model. Both now take the last eight.
"""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mememb.reset(); memdb.reset_db(); memdb.get_db()
    yield
    memdb.reset_db(); mememb.reset()


def _twelve():
    for i in range(1, 13):
        memapi.add_user_rule(f"regla número {i:02d} del operador")


def test_the_prompt_carries_the_newest_rules():
    _twelve()
    block, _, _ = memapi.compose_state(mission_fallback="m")
    assert "regla número 12" in block, "the rule he said last never reached the model"
    assert "regla número 05" in block
    assert "regla número 01" not in block, "eight rules ride, and they are the most recent eight"


def test_the_worker_dossier_carries_the_newest_rules():
    from nucleo.memory_agent import dossier
    _twelve()
    st = memapi.state()
    got = memapi.rules_for("worker", st=st)
    assert len(got) == 12
    import inspect
    src = inspect.getsource(dossier)
    assert 'memory.rules_for("worker", st=st)[-8:]' in src, "the dossier takes the last eight, not the first"
