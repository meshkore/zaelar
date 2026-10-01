"""A stored spoken rule says, on its event, which surface it was filed under (V2-778 F3-25, 2026-10-01).

The scope classifier (`nucleo/flash/rule_scope.py`) decides whether a rule rides in the voice prompt, the worker's
dossier or a widget's row, and its misroutes were unreadable: «confirma con el restaurante» filed as `voice` simply
never reached the worker, and nothing on the timeline said where it had gone. The event now carries the scope.
"""
import asyncio

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


def test_a_rule_row_event_carries_every_scope(monkeypatch):
    from nucleo.batch import runner
    from voice import observer
    seen = []
    monkeypatch.setattr(observer, "emit", lambda *a, **k: seen.append((a, k)))
    res = asyncio.run(runner._store_rule("No me confirmes las órdenes. Nunca compres en Wish."))
    assert res.get("ok") is not False, res
    ev = [k for a, k in seen if len(a) > 1 and "user rule guardada" in a[1]]
    assert ev, "no rule event"
    assert ev[0]["extra"]["scopes"] == ["voice", "general"], ev[0]["extra"]
