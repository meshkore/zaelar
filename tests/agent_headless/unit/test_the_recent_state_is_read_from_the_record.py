"""V2-776 M2 · the prompt's recent state is read from the RECORD, always (nodes 2.196, 2.197, 3.112).

Manual session 7850de3f (2026-09-30): the INIT list finished at 11:19; at 12:43 the agent said «it's all still
running in the background». The record knew. `record_lines` quoted ONE row and only when RAM was silent. Now the
last requests of the last hours — inline, worker, list, errand — are one line each: facts, no instruction.
"""
import contextvars
import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import request_row as rq
from nucleo.flash import task_block as tb


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db()
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [])
    monkeypatch.setattr(dispatch, "recently_ended_sessions", lambda now=None, limit=3: [])
    yield
    memdb.reset_db()


def _inline(text, widget, action, verdict, outcome=""):
    uid = contextvars.copy_context().run(lambda: (rq.begin(text), rq.opened(widget, action))[1])
    rq.settle(uid, verdict, outcome)
    return uid


def test_the_finished_list_and_the_inline_requests_are_facts_in_the_prompt():
    now = time.time()
    ts.task_put({"id": "lista:1", "title": "26 × Assistant identity", "goal": "DEMO INITIALIZATION", "kind": "list",
                 "state": "done", "outcome": "26/26 · I've finished your list", "created_at": int(now - 3900),
                 "finished_at": int(now - 3700)})
    ts.task_put({"id": "lista:1#01", "title": "name", "goal": "Your name is Johnny", "kind": "identity",
                 "state": "done", "parent_id": "lista:1", "finished_at": int(now - 3800)})
    _inline("show me a red ferrari f40", "imagenes", "show", "met", "12 fotos")
    _inline("play the second one", "youtube", "play_result", "unmet", "No hay resultados de búsqueda")
    [line] = tb.recent_lines(now=now + 5)
    assert "26 × Assistant identity» · HECHA · hace 61 min" in line
    assert "«show me a red ferrari f40» · HECHA (comprobado en pantalla)" in line
    assert "«play the second one» · FALLÓ (no se cumplió)" in line
    assert "Your name is Johnny" not in line, "a list's steps are how it was done, not requests of their own"
    assert line.index("play the second one") < line.index("Assistant identity"), "newest first"
    for rule in ("NUNCA", "NO ", "DILO", "debes"):
        assert rule not in line, f"facts only — «{rule}» is an instruction"


def test_six_lines_at_most_and_bounded_in_size():
    now = time.time()
    for i in range(10):
        _inline(f"request number {i} " + "x" * 80, "agenda", "add_meeting", "met", "y" * 120)
    [line] = tb.recent_lines(now=now + 5)
    assert line.count(" | ") <= tb.RECENT_MAX - 1 and len(line) <= tb.RECENT_MAX_CHARS + 200


def test_a_waiting_request_quotes_its_question():
    now = time.time()
    ts.task_put({"id": "w1", "title": "Book a table at Botín", "goal": "book", "kind": "web", "state": "waiting",
                 "created_at": int(now - 60), "started_at": int(now - 60)})
    ts.task_patch("w1", progress={"ask": "For how many people?"})
    [line] = tb.recent_lines(now=now)
    assert "ESPERA TU RESPUESTA" in line and "te preguntó: «For how many people?»" in line


def test_old_rows_and_a_running_worker_are_left_to_their_own_blocks(monkeypatch):
    now = time.time()
    ts.task_put({"id": "old", "title": "yesterday", "goal": "g", "kind": "web", "state": "done",
                 "finished_at": int(now - 7 * 3600)})
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [{"uid": "live1", "status": "running"}])
    ts.task_put({"id": "live1", "title": "monitors", "goal": "g", "kind": "web", "state": "running",
                 "created_at": int(now - 30)})
    assert tb.recent_lines(now=now) == []


def test_a_new_process_reads_what_the_last_one_did():
    """3.112 — nothing in RAM: the rows alone make the block (a restart, an hour of silence)."""
    _inline("move the call to four", "agenda", "move_meeting", "met")
    memdb.reset_db(); memdb.get_db()        # a fresh connection over the same file, as after a restart
    [line] = tb.recent_lines()
    assert "move the call to four" in line
