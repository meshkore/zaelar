"""A finished report he corrects is never a mute turn (three-tasks-at-once EN, 2026-10-15).

«btw for the car report — Renault isn't sold here, I need US models» over a report that had FINISHED: the model
called `reopen_task`, the report lived on the document sheet (V2-644, no `result` artifact), the results-sheet
rebuild said «no results», and nothing was shown nor asked — the mute backstop answered «Sorry, I lost that». Two
mechanisms, both channels through `task_recall.voice_turn`:

  · a report errand reopens on the DOCUMENT sheet that still holds it;
  · a reopen with nothing to show or ask, under a verdict already paid that the order needs a worker, escalates
    with his words (the verdict completes an empty act, CRIT-K2) — never a mute turn.
"""
import asyncio
import threading

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.flash import probe_decide as PD
from nucleo.flash import router_guards as RG
from widgets import store

TEXT = "btw for the car report — Renault isn't sold here, I need US models, pricing and real-world range."


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    d = tmp_path / "wdata"
    d.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", str(d))
    import nucleo.jev as jev
    import voice.observer as obs
    monkeypatch.setattr(jev, "enabled", lambda: False)
    monkeypatch.setattr(obs, "emit", lambda *a, **k: None)
    ts.task_put({"id": "car", "title": "Report on electric cars for city driving", "goal": "a report on city EVs",
                 "surface": "informe", "state": "done", "visible": True, "created_at": 1000, "finished_at": 1600})
    yield
    memdb.reset_db()


def _brief(route: str) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [], "_call_id": "t",
            "result": {"escalate_or_inline": {"choice": route, "confidence": 1.0},
                       "request_type": {"choice": "order", "confidence": 1.0}}}


class _Sess:
    window, last_action, executes = [], "", True


def _turn(brief) -> dict:
    calls = [{"name": "reopen_task", "args": {"query": "electric cars for city driving report"}}]
    return asyncio.run(PD.name_the_action(_hard=None, _router=RG, _tbrief=brief, _vault_gate=None, ingest=None,
                                          names={"reopen_task"}, sess=_Sess(), tags=[], text=TEXT, tool_calls=calls))


def test_a_report_errand_reopens_on_the_document_that_holds_it(world):
    from widgets.documento import data as doc
    db = doc._load()
    db.update(title="Electric Cars for City Driving — 2026", body="# Electric cars\n\nRenault 5…",
              task_title="Report on electric cars for city driving")
    store.save(doc.WIDGET_ID, db)
    assert _turn(None)["action"] == "canvas:show:documento"


def test_nothing_to_show_under_a_worker_verdict_escalates_his_words(world):
    assert _turn(_brief("escalate"))["action"] == "escalate"


def test_nothing_to_show_without_that_verdict_still_asks_or_says_so(world):
    assert _turn(_brief("handle_inline"))["action"] == "clarify"
