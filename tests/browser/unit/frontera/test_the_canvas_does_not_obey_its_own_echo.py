"""Exposes the canvas echo filter to pytest (V2-261). The reason is in the .mjs, which MOUNTS the handler."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_canvas_does_not_obey_its_own_echo.mjs")


def test_the_canvas_never_obeys_its_own_report() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to mount the SSE handler")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
