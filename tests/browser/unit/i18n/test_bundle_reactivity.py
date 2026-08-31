"""Exposes the i18n reactivity contract to pytest/Test Observatory (see the .mjs file for the rationale)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_bundle_reactivity.mjs")


def test_t_rerenders_when_the_bundle_gains_keys() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the i18n reactivity contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
