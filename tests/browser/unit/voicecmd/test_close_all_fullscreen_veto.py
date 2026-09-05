"""Exposes the client close-all fullscreen veto (V2-601 T-07) to pytest/Test Observatory (see the .mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_close_all_fullscreen_veto.mjs")


def test_a_fullscreen_mention_never_closes_the_canvas() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the voiceCommands veto contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
