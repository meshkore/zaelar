"""The processes panel's record of a running process is READ from the live registry, never stored (V2-822).

`GET /api/tasks/<id>/process` → `nucleo.process_view.of`: the plan the worker declared and how much is done, its
narration, the browser it drives and the harvest — the same readings the sheets use (`sheets.browser_for`,
`sheets.harvest_for`) — keyed by the session id the SSE events name OR the durable row id, and `alive: False` once
the errand is not live. Disarm: `of` ignoring the `uid` key → red.
"""
from __future__ import annotations

import types

from fastapi.testclient import TestClient

from nucleo import process_view


def _rec(**over):
    base = dict(task_id="7", uid="row-7", title="Tu estilo", goal="g", surface="informe", status="running",
                phase="Analizando", plan=["Leer", "Analizar", "Escribir"], done=1,
                phases=[{"t": 1.0, "s": "Leyendo enviados"}, {"t": 2.0, "s": "Analizando"}], nav_task="",
                waiting_on="", ask="")
    base.update(over)
    return types.SimpleNamespace(**base)


def test_the_record_is_the_live_errand_by_either_id(monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "_SESSIONS", {"7": _rec()})
    for key in ("7", "row-7"):
        rec = process_view.of(key)
        assert rec["alive"] is True and rec["id"] == "7" and rec["uid"] == "row-7"
        assert rec["plan"] == ["Leer", "Analizar", "Escribir"] and rec["done"] == 1
        assert rec["phases"] == ["Leyendo enviados", "Analizando"]
        assert rec["browser"] == {} and rec["harvest"] == {}, "no tab driven: nothing invented"


def test_a_finished_or_unknown_errand_is_not_alive(monkeypatch):
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "_SESSIONS", {"7": _rec(status="done")})
    assert process_view.of("7") == {"alive": False}
    assert process_view.of("nope") == {"alive": False} and process_view.of("") == {"alive": False}


def test_the_route_answers_the_record(monkeypatch):
    from fastapi import FastAPI

    from nucleo import dispatch
    from server import tasks_api
    monkeypatch.setattr(dispatch, "_SESSIONS", {"7": _rec()})
    app = FastAPI(); app.include_router(tasks_api.router)
    body = TestClient(app).get("/api/tasks/row-7/process").json()
    assert body["alive"] is True and body["done"] == 1
