"""Exposes the orb's listening claim to pytest/Test Observatory (see the .mjs for the operator's report)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_the_orb_only_glows_when_something_listens.mjs")


def test_the_orb_only_glows_when_something_listens() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the orb listening contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
