"""Exposes the V2-850 rule that a voiced reply always reaches the wall to pytest/Test Observatory (see the .mjs for the measurement)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_voiced_reply_always_reaches_the_wall.mjs")


def test_a_voiced_reply_always_reaches_the_wall() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the chat wall write contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
