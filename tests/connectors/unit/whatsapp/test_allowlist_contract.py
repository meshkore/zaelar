"""Expose the WhatsApp Node test suite to pytest and the observatory."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).with_name("allowlist.test.mjs")


def test_whatsapp_allowlist_contract() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the WhatsApp allowlist contract")
    result = subprocess.run([node, "--test", str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
