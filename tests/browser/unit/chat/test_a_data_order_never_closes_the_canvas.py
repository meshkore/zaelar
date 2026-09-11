"""Exposes the client-side close-ALL contract to pytest (see the .mjs for the measured session)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_data_order_never_closes_the_canvas.mjs")


def test_a_data_order_never_closes_the_canvas() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the canvas fast-lane contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
