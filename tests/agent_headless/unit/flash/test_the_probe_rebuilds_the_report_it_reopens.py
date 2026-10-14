"""When the probe EXECUTES a reopened errand, the report comes back on a sheet and the card is shown (2026-10-14).

`flat-hunt-recall-the-report` ended with `n_items=0` and `n_sheets=0` over a task that still held its report: the
probe reported `canvas:show:results` and rebuilt nothing — «a headless channel would never see» it, said the
comment, but the use-case harness reads exactly that sheet and that show. Now the executing probe runs the voice
turn's own verdict (`task_recall.voice_turn`): sheet rebuilt from `task_artifacts`, card presented through the one
door (`canvas_visibility.present`). A dry run (the routing bench) still decides and writes nothing.
"""
import asyncio

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.flash import probe_decide as PD
from nucleo.flash import router_guards as RG
from widgets import store
from widgets.results import data as sheetdata
from widgets.results import sheet_names


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


@pytest.fixture
def shows(monkeypatch):
    import voice.observer as obs
    got = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, *a, **k: got.append((kind, label, k.get("extra") or {})))
    return got


class _Sess:
    def __init__(self, executes: bool):
        self.window, self.last_action, self.executes = [], "", executes


def _turn(executes: bool) -> dict:
    calls = [{"name": "reopen_task", "args": {"query": "piso Gràcia"}}]
    return asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=None, _vault_gate=None, ingest=None,
                                          names={"reopen_task"}, sess=_Sess(executes), tags=[],
                                          text="El de Gràcia, el que te pedí.", tool_calls=calls))


def _seed():
    ts.task_put({"id": "g", "title": "Pisos de alquiler en Gràcia", "goal": "piso en Gràcia", "state": "done",
                 "visible": True, "created_at": 2000, "finished_at": 2600})
    ts.task_put({"id": "s", "title": "Pisos de alquiler en Sant Antoni", "goal": "piso en Sant Antoni",
                 "state": "done", "visible": True, "created_at": 1000, "finished_at": 1600})
    for tid in ("g", "s"):
        ts.artifact_put(tid, "result", {"title": tid, "items": [{"title": f"{tid} {n}"} for n in range(3)]})
        ts.artifact_put(tid, "considered", {"considered": 5, "kept": 3,
                                            "rows": [{"title": f"{tid} x{n}", "why": "too dear"} for n in range(2)]})


def test_the_executing_probe_puts_the_report_back_and_shows_it(fresh_db, own_sheets, shows):
    _seed()
    assert not store.exists(sheet_names.sheet_key("g")), "the premise: no sheet on disk, only the task"
    blk = _turn(executes=True)
    assert blk["action"] == "canvas:show:results::g", blk
    back = sheetdata.view_data("g")
    assert [i["title"] for i in back["items"]] == ["g 0", "g 1", "g 2"]
    assert len(back["rejected"]) == 2 and back["rejected"][0]["why"], "the discarded pile came back with its reasons"
    assert ("widget", "show") in [(k, lbl) for k, lbl, x in shows if x.get("id") == "results::g"], shows


def test_a_dry_run_decides_and_writes_nothing(fresh_db, own_sheets, shows):
    _seed()
    blk = _turn(executes=False)
    assert blk["action"] == "canvas:show:results"
    assert not store.exists(sheet_names.sheet_key("g")), "a dry run rebuilt a sheet"
    assert not [s for s in shows if s[1] == "show"]
