"""Expose the Agenda JavaScript security contract to pytest and the observatory."""

from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).with_name("test_xss.mjs")


def test_agenda_renders_untrusted_values_as_text() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the Agenda JavaScript contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
