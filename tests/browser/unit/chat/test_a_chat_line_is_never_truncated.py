"""Exposes the V2-852 T12 rule that a chat line is never truncated to pytest/Test Observatory (see the .mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_chat_line_is_never_truncated.mjs")


def test_a_chat_line_is_never_truncated() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the chat wall write contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
