"""A task MATTER goes to its task, never into the notes mailbox (V2-851 F4, §8; the F0 annex's 28 F4 sites).

`nucleo.events.task_event.told`: a question for him makes the task's row WAIT for his answer with the question; the
matter is one `task` event in the flow; it is said once out of turn with the task's identity (or a notice key) unless
`speak=False`. The sites the annex marked F4 call it; `brain_notes.push` is left only where F5 or F2d owns it — the
count below can only go down (the disarm: a site that pushes a note again turns `test_the_mailbox_only_shrinks` red).
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.circuit import ledger
from nucleo.events import task_event

ENGINE = Path(__file__).resolve().parents[3]
#: `brain_notes.push` sites left in product code after F5a (the module itself is gone): susurro ×4, op_receipt,
#: op_pending, data_ops — all in the files the parallel F5b branch owns, which takes them to 0.
MAX_PUSHES = 7


@pytest.fixture
def row(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    now = int(time.time())
    ledger.store().task_put({"id": "errand:e1", "goal": "meet Laura", "state": "running", "created_at": now})
    said = []
    monkeypatch.setattr(task_event, "_soon", lambda coro: (said.append(coro), coro.close()))
    task_event.drain()
    yield said
    memdb.reset_db()
    mememb.reset()


def test_a_question_makes_its_row_wait_with_the_question(row):
    task_event.told("[SISTEMA] Laura proposes Thursday 15:00 — yes?", task_id="errand:e1", ask=True)
    r = ledger.store().task_get("errand:e1")
    assert r["state"] == "waiting" and r["waiting_for"] == ledger.USER_ANSWER and "Laura" in r["ask"]
    assert task_event.drain() == ["Laura proposes Thursday 15:00 — yes?"] and len(row) == 1


def test_a_matter_without_a_row_is_keyed_and_a_silent_one_is_only_recorded(row):
    task_event.told("Could not send the Telegram to Ana.", key="telegram:1")
    task_event.told("The card 'gym' was built.", key="widget_gen:gym:ok", speak=False)
    assert len(task_event.drain()) == 2 and len(row) == 1, "speak=False is recorded in the flow, never said"


def test_the_mailbox_only_shrinks():
    # no `\b` here: git's POSIX ERE on macOS has none, and this grep matched nothing at all (V2-851 F5 found it)
    files = subprocess.run(["git", "grep", "-lE", r"(brain_notes|_bnotes|_bn)\.push\(", "--", "*.py"], cwd=ENGINE,
                           capture_output=True, text=True).stdout.split()
    files = [f for f in files if not f.startswith("tests/")]
    n = sum(len([ln for ln in (ENGINE / f).read_text(encoding="utf-8").splitlines()
                 if __import__("re").search(r"\b(brain_notes|_bnotes|_bn)\.push\(", ln)]) for f in files)
    assert n <= MAX_PUSHES, f"{n} brain_notes.push sites (ceiling {MAX_PUSHES}): a task matter goes to its task"
