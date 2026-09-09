"""Exposes the ambient-isolation contract to pytest/Test Observatory (see the .mjs for the measured session)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_room_is_not_the_operator.mjs")


def test_the_room_is_not_the_operator() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the ambient-isolation contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
