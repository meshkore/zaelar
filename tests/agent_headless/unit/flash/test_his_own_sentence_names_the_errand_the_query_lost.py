"""His own sentence names the errand when the model's `reopen_task` query paraphrased the name out (2026-10-14).

The query is the MODEL's summary of what he said. When it comes back as «piso» over «el de Gràcia, el que te pedí»,
the one word that told the two flat hunts apart is gone, and resolving the summary alone asks him again. Both
channels hand the resolver his words as well: the voice lane passes the operator's text, the probe its turn text.
"""
import inspect

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.flash import task_recall as tr
from widgets import store


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def own_sheets(tmp_path, monkeypatch):
    d = tmp_path / "wdata"
    d.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", str(d))
    assert "widgets/_data" not in store.DATA_DIR, "this fixture is not isolating anything"
    return d


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: False)


def _two_flat_hunts():
    for tid, district, at in (("g", "Gràcia", 2000), ("s", "Sant Antoni", 1000)):
        ts.task_put({"id": tid, "title": f"Pisos de alquiler en {district}", "goal": f"piso de alquiler en {district}",
                     "state": "done", "visible": True, "created_at": at, "finished_at": at + 60})
        ts.artifact_put(tid, "result", {"title": f"Pisos en {district}", "items": [{"title": f"Piso en {district}"}]})


def test_the_summary_alone_asks_and_his_sentence_answers(fresh_db):
    _two_flat_hunts()
    assert tr.resolve("piso")["ok"] is False, "the summary alone names neither — the premise of this file"
    r = tr.resolve("piso", heard="El de Gràcia, el que te pedí hace unos días.")
    assert r["ok"] and r["task"]["id"] == "g"


def test_the_voice_verdict_carries_his_sentence_to_the_report(fresh_db, own_sheets):
    _two_flat_hunts()
    v = tr.voice_turn("piso", "El de Gràcia, el que te pedí hace unos días.")
    assert v["show"] == "results::g" and v["ask"] is None, v


def test_the_voice_lane_hands_the_resolver_his_words():
    """The wiring, read where it lives: without the operator's text the voice channel keeps the old defect."""
    from nucleo.flash import post_stream_lanes as lanes
    src = inspect.getsource(lanes.run_the_light_lanes)
    assert '_trecall.voice_turn, reopen_req["v"], operator_text or text, _brief)' in src
