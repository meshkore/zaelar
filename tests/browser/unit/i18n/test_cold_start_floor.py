"""Expone a pytest/Test Observatory el suelo del arranque en frío (ver el .mjs para el porqué)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_cold_start_floor.mjs")


def test_el_arranque_en_frio_no_ensena_claves() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the cold-start floor contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
