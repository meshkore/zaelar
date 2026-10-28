"""«Did I give you a list yesterday?» is answered from the record, in the turn (2026-10-21).

Manual session 374a2ae2: the agent answered «no» to a 26-step list it had finished the day before — the prompt read
only the last 6 h of requests — then sent a worker that spent four minutes failing to find it. The days before the
recent window are now one line per request (`task_block.earlier_lines`), facts only.
"""
import time

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.turn.prompt import live_history


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db()
    yield
    memdb.reset_db()


def _list(lid, title, goal, ago, steps_done, steps):
    now = time.time()
    ts.task_put({"id": lid, "title": title, "goal": goal, "kind": "lista", "state": "done",
                 "created_at": int(now - ago), "finished_at": int(now - ago + 200)})
    for i in range(steps):
        ts.task_put({"id": f"{lid}#{i:02}", "title": f"s{i}", "goal": f"step {i}", "kind": "memory",
                     "state": "done" if i < steps_done else "failed", "parent_id": lid, "visible": 0,
                     "finished_at": int(now - ago + 100)})


@pytest.mark.parametrize("goal", ["DEMO INITIALIZATION", "Inicialización de la demo", "Weekly errands for the house"])
def test_a_list_from_yesterday_is_in_the_turn_with_its_steps(goal):
    _list("lista:y", "26 × Assistant name Johnny", goal, 26 * 3600, 25, 26)
    [line] = live_history.earlier_lines()
    assert "26 × Assistant name Johnny" in line and "una lista de 26 tareas" in line and "(25/26 hechas)" in line
    assert goal[:20] in line, "what it was, in his words — a composed title does not answer «the long prompt I sent»"
    import datetime as dt
    day = dt.datetime.fromtimestamp(time.time() - 26 * 3600)
    assert day.strftime("%A %Y-%m-%d") in line, "the line names its day — weekday AND date — so «yesterday» resolves"
    assert "step 3" not in line, "a list's steps are how it was done, not requests of their own"


def test_the_recent_window_and_the_old_ones_are_left_out():
    now = time.time()
    ts.task_put({"id": "recent", "title": "an hour ago", "goal": "g", "kind": "web", "state": "done",
                 "created_at": int(now - 3600), "finished_at": int(now - 3500)})
    ts.task_put({"id": "ancient", "title": "two weeks ago", "goal": "g", "kind": "web", "state": "done",
                 "created_at": int(now - 14 * 86400), "finished_at": int(now - 14 * 86400)})
    ts.task_put({"id": "inl", "title": "an agenda add", "goal": "g", "kind": "inline", "state": "done",
                 "created_at": int(now - 30 * 3600), "finished_at": int(now - 30 * 3600)})
    [line] = live_history.earlier_lines(now=now)
    assert line.endswith(": ninguna."), "the recent block says the first, the week ends before the second"


def test_an_empty_week_is_said_with_its_range():
    """«What did you do yesterday?» with nothing on record is a fact — «nothing on Tuesday the 20th» — not a
    blank the model fills with a guess or a worker."""
    import datetime as dt
    now = time.time()
    [line] = live_history.earlier_lines(now=now)
    assert dt.datetime.fromtimestamp(now - live_history.EARLIER_WINDOW_S).strftime("%Y-%m-%d") in line and "ninguna" in line


def test_bounded_and_facts_only():
    for i in range(12):
        _list(f"lista:{i}", f"list number {i} " + "x" * 60, "g", 8 * 3600 + i * 3600, 1, 1)
    [line] = live_history.earlier_lines()
    assert line.count(" | ") <= live_history.EARLIER_MAX - 1 and len(line) <= live_history.EARLIER_MAX_CHARS + 200
    for rule in ("NUNCA", "NO ", "DILO", "debes"):
        assert rule not in line, f"facts only — «{rule}» is an instruction"


def test_the_turn_prompt_carries_it(monkeypatch):
    from nucleo.turn.prompt import live_history
    from nucleo.turn.prompt import live_state
    monkeypatch.setattr(live_history, "earlier_lines", lambda: ["EARLIER-MARK"])
    assert "EARLIER-MARK" in live_state.live_state(), "the block is built and never reaches the turn"
