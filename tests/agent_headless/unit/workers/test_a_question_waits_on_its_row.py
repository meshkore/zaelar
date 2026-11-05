"""V2-851 F1b §3 — a worker's question is DURABLE: the row waits, the retained act is an artefact, the screen sees an
`ask` event, the worker's process ends, and an answer by id (`POST /api/tasks/{id}/answer`) resumes THAT session.

On the frozen code the question lived in a RAM registry (`_ACTS`) and the worker's process polled for it in a loop;
a restart lost both, and the row read `running` while he was the one being waited for.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import tasks_store as ts
from nucleo.cli import worker_api, worker_api_asks, worker_api_resume


@pytest.fixture
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    worker_api._ACTS.clear()
    events, resumed = [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        events.append({"kind": kind, **(extra or {})}))
    monkeypatch.setattr(worker_api_resume, "resume_soon", lambda uid, e: resumed.append((uid, dict(e))) or 1)
    yield SimpleNamespace(events=events, resumed=resumed)
    worker_api._ACTS.clear()
    memdb.reset_db()
    mememb.reset()


def _rec(uid="b0-7", task_id="7", sid="sess-abc"):
    now = int(time.time())
    ts.task_put({"id": uid, "goal": "send Raquel the photos", "title": "Photos to Raquel", "state": "running",
                 "created_at": now - 60, "started_at": now - 60})
    return SimpleNamespace(task_id=task_id, uid=uid, native_sid=sid, waiting_on="", ask="", ask_corr="", parked=False)


def test_a_question_makes_the_row_wait_with_its_id(fresh):
    rec = _rec()
    ask_id = worker_api._register_ask(rec, "Which Raquel: Pérez or Ruiz?", options=["Raquel Pérez", "Raquel Ruiz"])
    row = ts.task_get("b0-7")
    assert (row["state"], row["waiting_for"], row["ask_id"], row["ask"]) == (
        "waiting", "user_answer", ask_id, "Which Raquel: Pérez or Ruiz?")
    assert rec.parked, "the session that asked ends: an answer resumes it by id"
    asks = [e for e in fresh.events if e["kind"] == "ask"]
    assert len(asks) == 1, "the `worker.ask` subscriber puts ONE question on screen"
    assert {k: asks[0][k] for k in ("task_id", "ask_id", "text", "session", "options")} == {
        "task_id": "b0-7", "ask_id": ask_id, "text": "Which Raquel: Pérez or Ruiz?", "session": "sess-abc",
        "options": ["Raquel Pérez", "Raquel Ruiz"]}
    assert "among" not in asks[0], "`among` is only an ASK_WHICH's"


def test_options_ride_only_when_the_asker_declared_them(fresh):
    worker_api._register_ask(_rec(), "Which day?")
    assert "options" not in [e for e in fresh.events if e["kind"] == "ask"][0]


def test_the_retained_act_is_on_the_row_not_only_in_ram(fresh):
    rec = _rec()
    act = {"action": "widget_data", "payload": {"widget_id": "mensajeria", "action": "send_to"}}
    ask_id = worker_api._register_ask(rec, "Send it?", action="widget_data", retained=act)
    worker_api._ACTS.clear()                                   # a restart empties the RAM cache
    art = ts.artifact_get("b0-7", worker_api_asks.ASK_SLOT)
    assert art["ask_id"] == ask_id and art["retained"] == act
    assert [a["ask_id"] for a in worker_api.open_asks()] == [ask_id]


def test_the_screen_answer_by_id_resolves_and_resumes_that_task(fresh):
    rec = _rec()
    ask_id = worker_api._register_ask(rec, "Which Raquel?")
    worker_api._ACTS.clear()                                   # after a restart: same path, no new row
    assert asyncio.run(worker_api.answer_task("b0-7", ask_id, "Raquel Pérez")) is True
    assert ts.task_get("b0-7")["state"] == "running" and not ts.task_get("b0-7")["waiting_for"]
    assert fresh.resumed and fresh.resumed[0][0] == "b0-7" and fresh.resumed[0][1]["answer"] == "Raquel Pérez"
    assert asyncio.run(worker_api.answer_task("b0-7", ask_id, "again")) is False, "an answered question is closed"


def test_a_wrong_ask_id_is_not_an_answer(fresh):
    worker_api._register_ask(_rec(), "Which Raquel?")
    assert asyncio.run(worker_api.answer_task("b0-7", "another", "Raquel Pérez")) is False
    assert ts.task_get("b0-7")["state"] == "waiting" and not fresh.resumed


def test_the_answer_route_says_200_when_open_and_409_when_not(fresh):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server import tasks_api
    app = FastAPI()
    app.include_router(tasks_api.router)
    c = TestClient(app)
    ask_id = worker_api._register_ask(_rec(), "Which Raquel?")
    r = c.post("/api/tasks/b0-7/answer", json={"ask_id": ask_id, "text": "Pérez"})
    assert (r.status_code, r.json()) == (200, {"ok": True})
    assert c.post("/api/tasks/b0-7/answer", json={"ask_id": ask_id, "text": "Pérez"}).status_code == 409


# ── a yes to a retained act: the confirmation recogniser, never a substring list (§15c) ────────────────────
def _retained(monkeypatch):
    ran = []

    async def _exec(action, payload, rec):
        ran.append(action)
        return {"ok": True}
    monkeypatch.setattr(worker_api, "_exec_allow", _exec)
    rec = _rec()
    act = {"action": "widget_data", "payload": {"to": "683139819"}}
    return ran, worker_api._register_ask(rec, "¿Se lo envío a Raquel?", action="widget_data", retained=act)


def test_asi_no_never_runs_the_retained_act(fresh, monkeypatch):
    """«así no» CONTAINS «si»: the dead `_is_yes` read it as a yes and EXECUTED the act (§15c)."""
    ran, ask_id = _retained(monkeypatch)
    assert asyncio.run(worker_api.answer(ask_id, "así no")) is True
    assert ran == []


def test_his_plain_yes_runs_it_once(fresh, monkeypatch):
    ran, ask_id = _retained(monkeypatch)
    asyncio.run(worker_api.answer(ask_id, "sí, envíalo"))
    assert ran == ["widget_data"]
    assert fresh.resumed[0][1]["result"] == {"ok": True}, "the resumed session is told the act ran"


def test_the_substring_yes_is_dead(fresh):
    """Disarm: the nine-word substring reader is gone and nothing reads a yes by substring."""
    assert not hasattr(worker_api, "_is_yes") and not hasattr(worker_api_asks, "_is_yes")
    assert worker_api._says_yes("¿Se lo envío?", "así no") is False
    assert worker_api._says_yes("¿Se lo envío?", "okupa la sala") is False


# ── the session ends after asking, and its row learns its session at spawn ─────────────────────────────────
def test_a_parked_session_runs_no_ending(fresh, monkeypatch):
    from nucleo.workers import session_finish as sf
    rec = _rec()
    worker_api._register_ask(rec, "Which Raquel?")
    rec.status = "running"
    assert sf.parked(rec)
    rec.status = "cancelled"
    assert not sf.parked(rec), "a stop is an ending, asked or not"


def test_the_row_learns_its_session_id_and_cwd_at_spawn(fresh):
    from nucleo.workers import session_events as se
    rec = _rec(sid="sess-xyz")
    se._row_learns_its_session(rec, "/tmp/zaelar-task-b0-7")
    row = ts.task_get("b0-7")
    assert (row["session_id"], row["cwd"]) == ("sess-xyz", "/tmp/zaelar-task-b0-7")


def test_an_answer_resumes_the_stored_session_in_the_stored_cwd(fresh):
    _rec()
    ts.task_patch("b0-7", session_id="sess-xyz", cwd="/tmp/w", phase="choosing the recipient", ask="Which Raquel?",
                  waiting_for="user_answer")
    ctx = worker_api_resume.context_for(ts.task_get("b0-7"), {"question": "Which Raquel?", "answer": "Pérez"})
    assert ctx["task_uid"] == "b0-7", "the SAME row continues — no new row for the answer"
    assert (ctx["resume"]["native_sid"], ctx["resume"]["cwd"]) == ("sess-xyz", "/tmp/w")
    rb = ctx["resume"]["rebrief"]
    assert "choosing the recipient" in rb and "Which Raquel?" in rb and "Pérez" in rb, "re-briefed from the ROW"


def test_the_dispatcher_resumes_any_kind_by_id_when_answered():
    """Disarm: `--resume` was web-only; an answer resumes every kind, in the stored cwd."""
    import inspect
    from nucleo.dispatch import session_steps
    src = inspect.getsource(session_steps.build_what_it_runs_with)
    assert 'if (kind == "web" and trusted) or _answered' in src and 'resume["cwd"]' in src


# ── «how is it going» reads the ROW, not a session ───────────────────────────────────────────────────────────
def test_the_prompt_says_what_a_task_waits_for_from_its_row(fresh):
    from memory._prompt import compose
    worker_api._register_ask(_rec(), "Which Raquel?")
    lines = compose._processes({"sessions": []})
    assert lines and "Photos to Raquel" in lines[0] and "Which Raquel?" in lines[0] and "ESPERA" in lines[0]
