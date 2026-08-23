"""Shown-and-ignored is CONDUCT; never-shown is PLUMBING. Without reading the prompt they look identical.

Measured on 2026-08-20, and the cost was concrete: a round was reported as "narrated normality over a blocked
state", the memory agent spent a full investigation proving the datum had been written and returned, the engine
agent had to read the code to say where it arrived — and three of the harness's findings were retracted, all of
the same shape (asserting something nobody had measured). All of it was reasoning about one artifact none of us
had read: the prompt the model actually got.

It is durable and one query away. Every `turn.completed` row carries the whole `system_prompt` plus the window
size. `/api/observability/events` cannot serve them (that route is pinned to `topic = 'observer'`), so this
reads the sandbox's own DB — a database the harness created, never the operator's.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import judge as J, verify as V

_NAV = ("NAVEGADOR — YA EN CURSO (1): «Reservar entradas» — en entradas.com, 2 pasos dados · "
        "último: ⛔ el sitio bloqueó el acceso (te tomó por un robot) — no puedo seguir yo solo desde aquí")
_CALM = ("NAVEGADOR — YA EN CURSO (1): «Reservar entradas» — en entradas.com, 2 pasos dados · "
         "último: 🌐 abrió https://www.entradas.com/")


def _db(tmp_path, turns: list[tuple[float, str, int]]):
    p = tmp_path / "sandbox.db"
    con = sqlite3.connect(p)
    con.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts_ms INTEGER, topic TEXT, "
                "payload TEXT)")
    for ts, nav, win in turns:
        payload = json.dumps({"system_prompt": f"── QUIÉN ERES ──\nzaelar\n{nav}\nfin", "window_msgs": win})
        con.execute("INSERT INTO events (ts_ms, topic, payload) VALUES (?,?,?)",
                    (int(ts * 1000), "turn.completed", payload))
    con.execute("INSERT INTO events (ts_ms, topic, payload) VALUES (?,?,?)",
                (1, "observer", json.dumps({"cat": "flash"})))
    con.commit()
    con.close()
    return p


def test_it_reads_what_the_model_was_shown(tmp_path):
    rows = V.prompt_context(_db(tmp_path, [(100.0, _CALM, 3), (200.0, _NAV, 5)]))
    assert [r["turn"] for r in rows] == [0, 1]
    assert [r["window_msgs"] for r in rows] == [3, 5]
    assert rows[0]["alert"] is False, "una fase normal no puede contar como muro"
    assert rows[1]["alert"] is True
    assert "bloqueó el acceso" in rows[1]["shown_state"]


def test_only_THIS_scenarios_turns(tmp_path):
    """A batch shares one engine, so the previous case's turn rows sit in the same table. Without the scope, a
    case would be judged on a wall another case hit."""
    db = _db(tmp_path, [(100.0, _NAV, 3), (500.0, _CALM, 3)])
    rows = V.prompt_context(db, since=300.0)
    assert len(rows) == 1 and rows[0]["alert"] is False


def test_a_missing_database_never_costs_the_round(tmp_path):
    """Fail-soft on purpose: this is evidence that makes a verdict better, never a reason to lose one."""
    assert V.prompt_context(tmp_path / "nope.db") == []
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a database")
    assert V.prompt_context(bad) == []


def test_the_judge_is_told_it_was_SHOWN_and_who_owns_that():
    txt = J.mechanism_facts({"prompt_context": [
        {"turn": 4, "window_msgs": 9, "shown_state": "⛔ el sitio bloqueó el acceso", "alert": True}]})
    assert "LO QUE EL AGENTE TENÍA DELANTE" in txt
    assert "turno 4" in txt and "bloqueó el acceso" in txt
    assert "fallo GRAVE de resultado" in txt
    assert "no lo describas como «no le llegó la información»" in txt


def test_and_told_the_OPPOSITE_when_it_was_never_shown():
    """The half that stops the false-finding class: with no wall in the prompt, "it hid the block" is not an
    available finding. Without this the block would only ever accuse."""
    txt = J.mechanism_facts({"prompt_context": [
        {"turn": 0, "window_msgs": 1, "shown_state": "", "alert": False}]})
    assert "En NINGÚN turno" in txt
    assert "NO puedes" in txt and "no la tuvo delante" in txt
    assert "el defecto es de quien tenía que ponérselo" in txt


def test_a_run_that_could_not_read_it_says_NOTHING():
    """Sensitivity: no prompt read must not turn into a claim in either direction."""
    txt = J.mechanism_facts({"families_observed": ["flash"]})
    assert "TENÍA DELANTE" not in txt


def test_the_runner_puts_it_in_the_report(monkeypatch, tmp_path):
    """The classic failure of this repo: the fact exists and never reaches the place where it is used."""
    from tests.use_cases.e2e.agent import run as R
    from tests.use_cases.e2e.agent import scenarios as SC

    import time
    seen = {}
    # Stamped just after "now": the runner scopes the read to turns from the scenario's start onwards, so a row
    # dated before it would be (correctly) filtered out and this test would pass for the wrong reason.
    monkeypatch.setattr(R.config, "SANDBOX_DB", str(_db(tmp_path, [(time.time() + 5, _NAV, 3)])))
    monkeypatch.setattr(R.probe_client, "say", lambda t, s, **k: {"reply": "vale", "trace": "t"})
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "session_events", lambda sid: [])
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.probe_client, "widget_rows", lambda wid, key: [])
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.judgemod, "judge",
                        lambda scn, run: seen.setdefault("mech", run["mechanism_report"]) or {})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "m")

    class _D:
        def __init__(self, scn, persona_name=""): self.done = True
        def opening(self): return "hola"
        def hears(self, t): self.done = True
    monkeypatch.setattr(R.drivermod, "Driver", _D)

    R._run_scenario(SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p",
                                       opening_line="o", success_checks="s", turns=1))
    pc = seen["mech"].get("prompt_context")
    assert pc and pc[0]["alert"] is True, "lo leído no llega al informe que ve el juez"


_FAILED = ('TAREAS DE FONDO — YA ACABADAS: «Reservar una noche de hotel» FALLÓ; «otra cosa» OK')


def test_a_FAILED_background_task_in_the_prompt_counts_as_shown(tmp_path):
    """The other half of the day's dominant defect, and the half that was invisible until this line was read.

    Measured in `book-hotel-night-known__es`: from turn 2 onwards the prompt said the background task had
    FAILED, and eight consecutive turns still answered "sigo con ello, te aviso". No wall, no question — a dead
    task, stated, ignored. Delivery was not the problem there; obedience was.
    """
    rows = V.prompt_context(_db(tmp_path, [(100.0, _FAILED, 5)]))
    assert rows[0]["alert"] is True
    assert "FALLÓ" in rows[0]["failed_task_line"]
    assert rows[0]["shown_state"] == "", "no había muro: no se puede inventar uno"


def test_a_background_task_that_simply_FINISHED_is_not_an_alert(tmp_path):
    """Sensitivity: `YA ACABADAS` without `FALLÓ` is good news. Flagging it would make the block cry wolf on
    every successful round, and a warning that always fires stops being read."""
    ok = 'TAREAS DE FONDO — YA ACABADAS: «Reservar una noche de hotel» OK'
    rows = V.prompt_context(_db(tmp_path, [(100.0, ok, 5)]))
    assert rows[0]["alert"] is False
    assert rows[0]["failed_task_line"] == ""


def test_the_judge_is_told_about_the_failed_task_too():
    txt = J.mechanism_facts({"prompt_context": [
        {"turn": 3, "window_msgs": 7, "shown_state": "", "failed_task_line": _FAILED, "alert": True}]})
    assert "una tarea que FALLÓ" in txt
    assert "turno 3" in txt and "FALLÓ" in txt
    assert "fallo GRAVE de resultado" in txt
