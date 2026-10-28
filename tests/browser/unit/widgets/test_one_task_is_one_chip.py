"""Exposes the one-task-one-chip contract to pytest (demo 2026-10-22). The reason is in the .mjs, which MOUNTS the
real store and SSE handler; the server half — the board row carries the session id — is asserted here."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_one_task_is_one_chip.mjs")


def test_one_task_is_one_chip() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to mount the store and the SSE handler")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_board_row_names_the_session_its_events_carry(monkeypatch) -> None:
    from nucleo import dispatch
    from nucleo.circuit import ledger as tasks
    from memory import tasks_store
    monkeypatch.setattr(tasks_store, "tasks_where", lambda **k: [{"id": "48ac70-1", "title": "monitors"}])
    monkeypatch.setattr(dispatch, "active_sessions", lambda: [{"id": "1", "uid": "48ac70-1", "phase": "reading"}])
    rows = tasks.board("live")
    assert rows and rows[0]["session"] == "1" and rows[0]["id"] == "48ac70-1"
