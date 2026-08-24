"""Expone a pytest/Test Observatory el contrato de PANTALLA de la rejilla de cosecha (el porqué, en el .mjs)."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_harvest_grid.mjs")


def test_the_harvest_grid_knows_when_to_keep_quiet() -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the harvest grid contract")
    result = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
