"""When the typed channel EXECUTES a reopened errand, the report comes back on a sheet and the card is shown
(2026-10-14).

`flat-hunt-recall-the-report` ended with `n_items=0` and `n_sheets=0` over a task that still held its report: the
text channel reported `canvas:show:results` and rebuilt nothing — «a headless channel would never see» it, said the
comment, but the use-case harness reads exactly that sheet and that show. The typed channel now runs the voice turn
itself (`nucleo.cli.turn.run_turn`), whose verdict is `task_recall.voice_turn`: sheet rebuilt from
`task_artifacts`, card presented through the one door (`canvas_visibility.present`). A dry run (the routing bench)
still decides and writes nothing.
"""
import asyncio

from tests.brain import harness as H

TEXT = "El de Gràcia, el que te pedí."


def _seed():
    from memory import tasks_store as ts
    ts.task_put({"id": "g", "title": "Pisos de alquiler en Gràcia", "goal": "piso en Gràcia", "state": "done",
                 "visible": True, "created_at": 2000, "finished_at": 2600})
    ts.task_put({"id": "s", "title": "Pisos de alquiler en Sant Antoni", "goal": "piso en Sant Antoni",
                 "state": "done", "visible": True, "created_at": 1000, "finished_at": 1600})
    for tid in ("g", "s"):
        ts.artifact_put(tid, "result", {"title": tid, "items": [{"title": f"{tid} {n}"} for n in range(3)]})
        ts.artifact_put(tid, "considered", {"considered": 5, "kept": 3,
                                            "rows": [{"title": f"{tid} x{n}", "why": "too dear"} for n in range(2)]})


def _turn(execute: bool, check) -> dict:
    case = {"id": "reopen", "lang": "es", "phrase": TEXT, "source": "test", "screen": {"open": []}, "expect": "talk",
            "model": {"tools": [{"name": "reopen_task", "args": {"query": "piso Gràcia"}}]}}
    with H.Isolated("es") as iso:
        iso.seed(case)
        _seed()
        from nucleo.cli import turn
        from voice import observer
        observer._dedup.clear()     # the observer collapses an identical show emitted <150 ms after the last test's
        try:
            res = asyncio.run(turn.run_turn(TEXT, sid="reopen", ingest=False, execute=execute))
        finally:
            turn.reset("reopen")
        check(res)
        return res


def test_the_executing_probe_puts_the_report_back_and_shows_it():
    def check(res):
        from widgets import store
        from widgets.results import data as sheetdata
        from widgets.results import sheet_names
        assert res["action"] == "canvas:show:results::g", res
        assert store.exists(sheet_names.sheet_key("g")), "the sheet was not rebuilt"
        back = sheetdata.view_data("g")
        assert [i["title"] for i in back["items"]] == ["g 0", "g 1", "g 2"]
        assert len(back["rejected"]) == 2 and back["rejected"][0]["why"], \
            "the discarded pile came back with its reasons"
        assert {"action": "show", "extra": {"id": "results::g"}} in res["tags"], res["tags"]
    _turn(True, check)


def test_a_dry_run_decides_and_writes_nothing():
    def check(res):
        from widgets import store
        from widgets.results import sheet_names
        assert res["action"].startswith("canvas:show:results"), res
        assert not store.exists(sheet_names.sheet_key("g")), "a dry run rebuilt a sheet"
    _turn(False, check)
