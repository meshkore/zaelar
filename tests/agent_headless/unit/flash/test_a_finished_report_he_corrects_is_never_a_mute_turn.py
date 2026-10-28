"""A finished report he corrects is never a mute turn (three-tasks-at-once EN, 2026-10-15).

«btw for the car report — Renault isn't sold here, I need US models» over a report that had FINISHED: the model
called `reopen_task`, the report lived on the document sheet (V2-644, no `result` artifact), the results-sheet
rebuild said «no results», and nothing was shown nor asked — the mute backstop answered «Sorry, I lost that». Two
mechanisms, through `task_recall.voice_turn`:

  · a report errand reopens on the DOCUMENT sheet that still holds it;
  · a reopen with nothing to show or ask, under a verdict already paid that the order needs a worker, escalates
    with his words (the verdict completes an empty act, CRIT-K2) — never a mute turn.

Driven through the typed channel (`nucleo.cli.turn.run_turn`), which runs the voice turn itself.
"""
import asyncio

from tests.brain import harness as H

TEXT = "btw for the car report — Renault isn't sold here, I need US models, pricing and real-world range."
CALL = {"name": "reopen_task", "args": {"query": "electric cars for city driving report"}}


def _turn(brief: dict | None, document: bool = False) -> dict:
    case = {"id": "car-report", "lang": "en", "phrase": TEXT, "source": "test", "screen": {"open": []},
            "expect": "talk", "model": {"tools": [CALL]}}
    if brief:
        case["brief"] = brief
    with H.Isolated("en") as iso:
        iso.seed(case)
        from memory import tasks_store as ts
        from widgets import store
        ts.task_put({"id": "car", "title": "Report on electric cars for city driving", "goal": "a report on city EVs",
                     "surface": "informe", "state": "done", "visible": True, "created_at": 1000, "finished_at": 1600})
        if document:
            from widgets.documento import data as doc
            db = doc._load()
            db.update(title="Electric Cars for City Driving — 2026", body="# Electric cars\n\nRenault 5…",
                      task_title="Report on electric cars for city driving")
            store.save(doc.WIDGET_ID, db)
        from nucleo.cli import turn
        try:
            return asyncio.run(turn.run_turn(TEXT, sid="car-report", ingest=False))
        finally:
            turn.reset("car-report")


def test_a_report_errand_reopens_on_the_document_that_holds_it():
    res = _turn(None, document=True)
    assert res["action"] == "canvas:show:documento", res


def test_nothing_to_show_under_a_worker_verdict_escalates_his_words():
    res = _turn({"escalate_or_inline": ("escalate", 1.0), "request_type": ("order", 1.0)})
    assert res["action"] == "escalate", res


def test_nothing_to_show_without_that_verdict_still_asks_or_says_so():
    res = _turn({"escalate_or_inline": ("handle_inline", 1.0), "request_type": ("order", 1.0)})
    assert res["action"] == "clarify", res
