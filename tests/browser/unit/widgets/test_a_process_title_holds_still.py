"""Exposes the process-title contract to pytest (V2-608 F7). The reason is in the .mjs, which MOUNTS the real
store and the real SSE handler and replays the life the operator watched."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_process_title_holds_still.mjs")


def test_a_process_title_holds_still() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to mount the store and the SSE handler")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_row_renders_the_three_layers() -> None:
    """The contract with the card (same spirit as the clusters-tab test): the stable name, the activity under
    it, and the state/elapsed line. If the classes or the fields drift, the .mjs above stays green while the
    operator sees one line again — this is the seam between the store's truth and his eyes."""
    chatwall = (Path(__file__).resolve().parents[4] / "frontend" / "app" / "components" / "ChatWall.js") \
        .read_text(encoding="utf-8")
    assert 'task.title' in chatwall and '"cw-proc-goal" }, title' in chatwall, "the goal line must be the TITLE"
    assert 'cw-proc-note' in chatwall, "the live activity has its own line"
    assert 'note !== title' in chatwall, "a note that repeats the title is the same text twice"
    assert 'chat.procElapsed' in chatwall and 'chat.waitingYou' in chatwall, "state + elapsed on the meta line"
    styles = (Path(__file__).resolve().parents[4] / "frontend" / "app" / "styles.css").read_text(encoding="utf-8")
    assert ".cw-proc-note" in styles, "the note line has no CSS — it would render unstyled or not at all"
