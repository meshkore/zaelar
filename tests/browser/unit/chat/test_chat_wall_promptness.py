"""Expone a pytest/Test Observatory el contrato de PRONTITUD del muro de chat (ver el .mjs para el porqué)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_chat_wall_promptness.mjs")


def test_the_chat_wall_shows_the_reply_without_waiting_for_the_voice() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the chat wall promptness contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
